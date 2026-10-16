"""
Every number of the 2026-10-14 portfolio report (md, report page, PnL ledger, deck) in one file, report.json:
eleven books under two gas cases, with controls, yearly returns and drawdowns, the yearly split of each portfolio,
and the move / gate switch / gas counts.

  BTC 現貨 g_down        H45's BTC half: BTC EMA100 gate, WBTC while on, full g_down ladder while off, 3 slices, $50k
  WBTC/cbBTC g_down      the same with the on-hours in WBTC/cbBTC 0.01% LP +/- 0.5% from 2024-10-13 (overlay, H17)
  v1, v2, v3             maker-defense ETH/USDC, $100k (and $50k, the half in a portfolio)
  BTC 現貨 g_down + vN   0.5 x BTC half + 0.5 x vN ($50k), never rebalanced
  WBTC/cbBTC g_down + vN the same with the cbBTC BTC half
Gas cases: "yearly" (GAS_GWEI 40 / 30 / 15 / 3 for 2022 / 2023 / 2024 / 2025+), "flat3" (3 gwei every year) and
"nogas" (0 gwei: pool fee and price impact only, asked for on 2026-10-16).

Inputs: md_portfolio.py, md_portfolio_gas.py (--gwei 3 and --gwei 0) and md_portfolio_cbbtc.py's results (run those first).
Run from samples/strategy-example on the strategy host:
  PYTHONPATH=../.. python md_portfolio_report.py
"""
import json

import numpy as np
import pandas as pd

import candidate_vs_c as cvc
import md_portfolio as mp
import md_portfolio_cbbtc as mc
import md_portfolio_gas as mg
import pool_lp_batch as batch
import yield_layer as yl
from spot_btc_eth_gate import load_prices, stats

OUT = f"{mp.RESULT_DIR}/report.json"
GWEI = {"yearly": lambda y: mg.YEARLY.get(y, mg.YEARLY[2025]), "flat3": lambda y: 3.0, "nogas": lambda y: 0.0}
BTC_DIR = {"yearly": batch.RESULT_DIR, "flat3": mg.btc_dir(3), "nogas": mg.btc_dir(0)}


def years() -> list[str]:
    return [y0[:4] for y0, _ in cvc.years(mp.LO, mp.HI)]


def year_end(y: str) -> str:
    return min(f"{int(y) + 1}-01-01", mp.HI)


def book_stats(s: pd.Series) -> dict:
    st = stats(s, mp.LO, mp.HI)
    per = {y: stats(s, f"{y}-01-01", year_end(y)) for y in years()}
    daily = s[s.index.hour == 0]
    return {"total": float(st["total"]), "cagr": float(st["annual"]), "maxDD": float(st["maxDD"]),
            "dd_at": str((s / s.cummax() - 1).idxmin()),
            "years": {y: {"ret": float(per[y]["total"]), "mdd": float(per[y]["maxDD"])} for y in years()},
            "year_end": {y: float(s[s.index < year_end(y)].iloc[-1]) for y in years()},
            "daily": {"t": [str(t.date()) for t in daily.index], "v": [round(float(x), 5) for x in daily]}}


def split(parts: dict[str, pd.Series]) -> dict:
    return mp.yearly_split(parts, years())


def btc_counts(case: str) -> dict:
    """Per year over the three slices: ladder re-placements, gate switches; gas over the whole run in USD."""
    out = {y: {"moves": 0, "switches": 0} for y in years()}
    gas = 0.0
    runs = pd.read_csv(f"{mg.btc_dir(3)}/runs.csv").set_index("version")
    for h in cvc.SLICES[3]:
        c = cvc.demeter_cfg(100_000, 3, h)
        ev = pd.read_csv(f"{BTC_DIR[case]}/events_99ac_{c.name}_ema{c.ema}_{cvc.START}.csv", parse_dates=["t"])
        ev = ev[(ev["t"] >= mp.LO) & (ev["t"] < mp.HI)]
        for y in years():
            e = ev[ev["t"].dt.year == int(y)]
            out[y]["moves"] += int((e["kind"] == "recentre").sum())
            out[y]["switches"] += int(e["kind"].isin(["on", "off"]).sum())
        flat_gas = float(runs.loc[c.name, "gas"])
        if case == "nogas":
            continue
        if case == "flat3":
            gas += flat_gas * c.initial
        else:  # costs are subtracted afterwards in USD, so the end gap of the two nav files is the gas gap
            end = {d: pd.read_csv(f"{d}/nav_99ac_{c.name}_ema{c.ema}_{cvc.START}.csv", index_col=0,
                                  parse_dates=True)["net"].iloc[-1] for d in BTC_DIR.values()}
            gas += flat_gas * c.initial + end[BTC_DIR["flat3"]] - end[BTC_DIR["yearly"]]
    return {"by_year": out, "gas_usd_run": gas}


def cb_counts(case: str, idx: pd.DatetimeIndex, level: pd.Series, eth_usd: pd.Series) -> dict:
    """LP entries and exits (each is a gate switch after 2024-10-13) and their gas in USD, over the three slices."""
    out = {y: {"lp_in": 0, "lp_out": 0} for y in years()}
    gas = 0.0
    avail = level.reindex(idx.union(level.index)).ffill().reindex(idx).notna().to_numpy()
    for h in cvc.SLICES[3]:
        gate = pd.read_csv(f"{batch.RESULT_DIR}/gate_99ac_ema100{f'_h{h:02d}' if h else ''}.csv", index_col=0,
                           parse_dates=True)["gate"].astype(bool)
        on = gate.reindex(idx, method="ffill").fillna(False).to_numpy() & (idx >= mc.LP_FROM) & avail
        for i in np.flatnonzero(on != np.r_[False, on[:-1]]):
            t = idx[i]
            out[str(t.year)]["lp_in" if on[i] else "lp_out"] += 1
            units = mc.GAS_EVENT_UNITS["enter" if on[i] else "exit"]
            gas += units * GWEI[case](t.year) * 1e-9 * float(eth_usd.asof(t.normalize()))
    return {"by_year": out, "gas_usd_run": gas}


def md_counts(version: str, book: int, eth_usd: pd.Series) -> dict:
    name = mp.run_name(version, book)
    act = pd.read_csv(f"{mp.RESULT_DIR}/actions_{name}.csv", parse_dates=["t"])
    run = pd.read_csv(f"{mp.RESULT_DIR}/run_{name}.csv").iloc[0]
    builds = act.loc[act["action"] == "AddLiquidityAction", "t"].drop_duplicates()
    by_year = {y: {"moves": int((builds.dt.year == int(y)).sum())} for y in years()}
    for case, f in GWEI.items():
        g = mg.md_gas(act, eth_usd, f)
        step = g.diff().fillna(g)
        for y in years():
            by_year[y][f"gas_{case}"] = float(step[step.index.year == int(y)].sum())
    return {"by_year": by_year, "builds": int(run["builds"]), "follow": int(run["follow_rebuilds"]),
            "upper": int(run["upper"]), "lower": int(run["lower"]), "impact_usd": float(run["impact"]) * book,
            "F_mean": float(run["F_mean"]), "diverged_days": int(run["diverged_days"])}


def main():
    base = pd.read_csv(f"{mp.RESULT_DIR}/navs.csv", index_col=0, parse_dates=True)
    flat = pd.read_csv(f"{mg.OUT}/navs_gwei3.csv", index_col=0, parse_dates=True)
    nogas = pd.read_csv(f"{mg.OUT}/navs_gwei0.csv", index_col=0, parse_dates=True)
    idx = base.index
    eth_usd = batch.eth_daily()
    level, events = yl.load_sleeve("cbbtc_lp0.005", yl.HOLDOUT_TAG)
    level = level["nav"]
    prices, _, _ = load_prices()
    btc_px = prices["btc"].reindex(idx).ffill()
    h45 = pd.read_csv(mp.H45_NAV, index_col=0, parse_dates=True).reindex(idx)
    report = {"years": years(), "period": [mp.LO, "2026-08-31"], "cases": {}, "counts": {}}
    for case, navs in {"yearly": base, "flat3": flat, "nogas": nogas}.items():
        btc = mg.btc_half(BTC_DIR[case], idx)
        btc_cb, slices = mc.btc_half_cb(BTC_DIR[case], idx, GWEI[case], eth_usd, level, events)
        books, attr = {"btc": btc, "btccb": btc_cb}, {"btccb": split({"btc": btc, "cb": btc_cb - btc})}
        for v in mp.VERSIONS:
            pres = {}
            for b in mp.BOOKS:
                f = pd.read_csv(f"{mp.RESULT_DIR}/nav_{mp.run_name(v, b)}.csv", index_col=0, parse_dates=True)
                pres[b] = (f["net_pre"] / b).reindex(idx).ffill()
                key = v if b == 100_000 else f"{v}h"
                books[key] = navs[f"md {v} (${b // 1000}k)"]
                attr[key] = split({"md_pre": pres[b], "md_cost": books[key] - pres[b]})
            pre, nav50 = pres[50_000], books[f"{v}h"]
            books[f"p{v}"] = 0.5 * btc + 0.5 * nav50
            books[f"pc{v}"] = 0.5 * btc_cb + 0.5 * nav50
            attr[f"p{v}"] = split({"btc": 0.5 * btc, "md_pre": 0.5 * pre, "md_cost": 0.5 * (nav50 - pre)})
            attr[f"pc{v}"] = split({"btc": 0.5 * btc, "cb": 0.5 * (btc_cb - btc), "md_pre": 0.5 * pre,
                                    "md_cost": 0.5 * (nav50 - pre)})
        books["hold_btc"] = btc_px / btc_px.iloc[0]
        books["hold_eth"] = base["hold ETH"]
        books["hold_5050"] = 0.5 * books["hold_btc"] + 0.5 * books["hold_eth"]
        if case == "yearly":
            books["cg"], books["cgd"] = h45["C+g"], h45["C+g+def"]
        else:
            books["cg"], books["cgd"] = navs["C+g (H45)"], navs["C+g+def (H45)"]
        for k, s in books.items():
            assert not s.isna().any(), (case, k)
            for y, a in attr.get(k, {}).items():
                assert abs(sum(a.values()) - stats(s, f"{y}-01-01", year_end(y))["total"]) < 1e-9, (case, k, y)
        report["cases"][case] = {"books": {k: {**book_stats(s), **({"attr": attr[k]} if k in attr else {})}
                                           for k, s in books.items()},
                                 "cb_slices": slices}
        report["counts"][f"btc_{case}"] = btc_counts(case)
        report["counts"][f"cb_{case}"] = cb_counts(case, idx, level, eth_usd)
    for v in mp.VERSIONS:
        for b in mp.BOOKS:
            report["counts"][mp.run_name(v, b)] = md_counts(v, b, eth_usd)
    with open(OUT, "w") as fh:
        json.dump(report, fh)
    for case, c in report["cases"].items():
        print(case)
        for k, s in c["books"].items():
            print(f"  {k:10s} total {s['total']:+.4f} cagr {s['cagr']:+.4f} maxDD {s['maxDD']:+.4f} "
                  + " ".join(f"{y} {s['years'][y]['ret']:+.4f}/{s['years'][y]['mdd']:+.4f}" for y in years()))
    for k, c in report["counts"].items():
        print(k, json.dumps({kk: vv for kk, vv in c.items() if kk != "by_year"}), json.dumps(c["by_year"]))


if __name__ == "__main__":
    main()
