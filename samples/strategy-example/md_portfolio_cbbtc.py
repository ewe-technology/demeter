"""
md_portfolio.py's books with the BTC half's on-hours in WBTC/cbBTC 0.01% LP +/- 0.5% (0xe8f7) instead of WBTC, as
H17 (pool_lp_combo.py): an overlay, not a Demeter run. Asked for on 2026-10-14, descriptive.

Each of the BTC half's three slices (00 / 08 / 16 UTC, $50k / 3) is multiplied by H17's value multiple: while the
slice's own gate is on (gate_99ac_ema100[_hHH], switching at the slice's hour), its value follows the LP index
(yield_layer's sleeve_cbbtc_lp0.005_to2026.csv, in BTC) instead of BTC; off, the multiple stays. The LP is used only
from 2024-10-13, the first clean day of 0xe8f7; before that the slice holds WBTC as before. Costs as H17, a share of
the slice's capital: enter 580k gas + 1 bp, exit 400k gas + 1 bp, 850k gas for each re-centre while on.

Two gas cases, each applied to the BTC half, the overlay and the maker-defense half alike:
  yearly  GAS_GWEI (40 / 30 / 15 / 3 for 2022 / 2023 / 2024 / 2025+), md_portfolio.py's books
  flat    3 gwei every year, md_portfolio_gas.py's books

Run from samples/strategy-example on the strategy host, after md_portfolio.py and md_portfolio_gas.py:
  PYTHONPATH=../.. python md_portfolio_cbbtc.py
"""
import os

import numpy as np
import pandas as pd

import candidate_vs_c as cvc
import md_portfolio as mp
import md_portfolio_gas as mg
import pool_lp_batch as batch
import yield_layer as yl
from sleeve_sim import GAS_EVENT_UNITS
from spot_btc_eth_gate import stats

LP_FROM = pd.Timestamp("2024-10-13")
BPS = 1e-4  # one conversion, in or out (pool_lp_combo.OVERLAY_BPS)
SLICE = 100_000 / 2 / 3
OUT = f"{mp.RESULT_DIR}/cbbtc"


def multiple(on: np.ndarray, hours: pd.DatetimeIndex, level: pd.Series, events: pd.DatetimeIndex, gwei_of,
             eth_usd: pd.Series) -> pd.Series:
    """pool_lp_combo.overlay with an hourly gate and a gas price by year."""
    level = level.reindex(hours.union(level.index)).ffill().reindex(hours)
    on = on & (hours >= LP_FROM) & level.notna().to_numpy()
    held = np.r_[False, on[:-1]]
    step = np.where(held, (level / level.shift(1)).fillna(1.0).to_numpy(), 1.0)
    cost = np.zeros(len(hours))

    def usd(units: int, t: pd.Timestamp) -> float:
        return units * gwei_of(t.year) * 1e-9 * float(eth_usd.asof(t.normalize()))

    for i in np.flatnonzero(on != np.r_[False, on[:-1]]):
        t = hours[i]
        cost[i] += usd(GAS_EVENT_UNITS["enter" if on[i] else "exit"], t) / SLICE + BPS
    for t in events:
        i = hours.searchsorted(t)
        if 0 < i < len(hours) and hours[i] == t and on[i] and on[i - 1]:
            cost[i] += usd(GAS_EVENT_UNITS["recentre"], t) / SLICE
    return pd.Series(np.cumprod(step * (1 - cost)), index=hours)


def btc_half_cb(rdir: str, idx: pd.DatetimeIndex, gwei_of, eth_usd, level, events) -> tuple[pd.Series, dict]:
    parts, info = [], {}
    for h in cvc.SLICES[3]:
        c = cvc.demeter_cfg(100_000, 3, h)
        net = pd.read_csv(f"{rdir}/nav_99ac_{c.name}_ema{c.ema}_{cvc.START}.csv", index_col=0, parse_dates=True)["net"]
        net = (net.resample("1h").last().ffill() / c.initial).reindex(idx, method="ffill")
        gate = pd.read_csv(f"{batch.RESULT_DIR}/gate_99ac_ema100{f'_h{h:02d}' if h else ''}.csv", index_col=0,
                           parse_dates=True)["gate"].astype(bool)
        on = gate.reindex(idx, method="ffill").fillna(False).to_numpy()
        m = multiple(on, idx, level, events, gwei_of, eth_usd)
        parts.append(net * m)
        lp_on = on & (idx >= LP_FROM)
        info[f"h{h:02d}"] = {"multiple_end": float(m.iloc[-1]), "lp_hours": int(lp_on.sum()),
                             "entries": int((lp_on & ~np.r_[False, lp_on[:-1]]).sum())}
    return pd.concat(parts, axis=1).mean(axis=1), info


def main():
    os.makedirs(OUT, exist_ok=True)
    level, events = yl.load_sleeve("cbbtc_lp0.005", yl.HOLDOUT_TAG)
    level = level["nav"]
    eth_usd = batch.eth_daily()
    base = pd.read_csv(f"{mp.RESULT_DIR}/navs.csv", index_col=0, parse_dates=True)
    flat = pd.read_csv(f"{mg.OUT}/navs_gwei3.csv", index_col=0, parse_dates=True)
    idx = base.index
    cases = {"yearly": (batch.RESULT_DIR, lambda y: mg.YEARLY.get(y, mg.YEARLY[2025]), base),
             "3 gwei": (mg.btc_dir(3), lambda y: 3.0, flat)}
    years = [y0[:4] for y0, _ in cvc.years(mp.LO, mp.HI)]
    rows, infos = [], {}
    for case, (rdir, gwei_of, navs) in cases.items():
        btc_plain = mg.btc_half(rdir, idx)
        assert float((btc_plain - navs["BTC half g ($50k)"]).abs().max()) < 1e-9, case
        btc_cb, infos[case] = btc_half_cb(rdir, idx, gwei_of, eth_usd, level, events)
        books = {"BTC half g": btc_plain, "BTC half g + cbBTC LP": btc_cb}
        for i, v in enumerate(mp.VERSIONS, 1):
            md = navs[f"md {v} ($50k)"]
            books[f"P{i} (md {v})"] = 0.5 * btc_plain + 0.5 * md
            books[f"P{i} + cbBTC LP"] = 0.5 * btc_cb + 0.5 * md
        for k, s in books.items():
            st = stats(s, mp.LO, mp.HI)
            per = {y: stats(s, f"{y}-01-01", min(f"{int(y) + 1}-01-01", mp.HI)) for y in years}
            rows.append({"gas": case, "book": k, "total": st["total"], "maxDD": st["maxDD"],
                         **{y: per[y]["total"] for y in years}, **{f"dd{y}": per[y]["maxDD"] for y in years}})
    t = pd.DataFrame(rows)
    t.to_csv(f"{OUT}/combine.csv", index=False)
    pd.Series({f"{c} {h}": v for c, d in infos.items() for h, v in d.items()}).to_json(f"{OUT}/slices.json", indent=1)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(f"cbBTC LP index {level.index[0]} .. {level.index[-1]}, {len(events)} re-centres")
    print(t[["gas", "book", "total", "maxDD", *years]].to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    for c, d in infos.items():
        print(c, d)


if __name__ == "__main__":
    main()
