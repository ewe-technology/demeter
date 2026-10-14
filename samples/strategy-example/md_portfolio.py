"""
Portfolio books (2026-10-14, asked for directly, descriptive, no verdict): half the book in H45's BTC half (version C's
BTC half with full g_down, three slices at 00/08/16 UTC) and half in one maker-defense ETH/USDC version.

  P1  0.5 x BTC half g + 0.5 x maker-defense v1
  P2  0.5 x BTC half g + 0.5 x maker-defense v2
  P3  0.5 x BTC half g + 0.5 x maker-defense v3

The halves start on 2022-01-01 00:00 with $50k each and are never rebalanced against each other (as H34 / H45).
Period 2022-01-01 .. 2026-08-31 (the last day of binance_ethusdt_1d.csv).

The maker-defense halves are continuous books through maker_defense_h38.py's harness: 0x88e6 hourly bars, Binance
signal at 00 UTC, the pool fee inside Demeter, price impact and gas subtracted afterwards (each version's own extra
swap charges off), so all three versions pay the same costs:
  v1  gamma_maker_defense_ethusdc_v1.py from origin/maker-defense, unchanged
  v2  gamma_maker_defense_ethusdc_v3.py with DIVERGENCE_RULE = False (its docstring: that is v2); standard mode as v3,
      not v2's compound default
  v3  gamma_maker_defense_ethusdc_v3.py as H38's lp_100k
Each version runs at $100k (the standalone book) and at $50k (the half in the portfolio; gas is a fixed amount per
action, so it weighs twice as much at $50k). v3 at $100k is re-run here and must match H38's nav_lp_100k.csv.

The BTC half is the "BTC half g" column of result/defensive-eth/nav_h45.csv (a $50k half).

Run from samples/strategy-example on the strategy host (it has the H38 hourly cache and the H45 nav file):
  PYTHONPATH=../.. python md_portfolio.py --runs --workers 2    # the maker-defense books, skips finished ones
  PYTHONPATH=../.. python md_portfolio.py --combine
  PYTHONPATH=../.. python md_portfolio.py --page                # page.json for the PnL page
"""
import argparse
import multiprocessing
import os

import pandas as pd

import candidate_vs_c as cvc
import gamma_maker_defense_ethusdc_v1 as v1mod
import maker_defense_h38 as h

RESULT_DIR = "result/md-portfolio"
H38_DIR = "result/maker-defense-h38"
H45_NAV = "result/defensive-eth/nav_h45.csv"
LO, HI = "2022-01-01", "2026-09-01"  # HI is exclusive: through 2026-08-31 23:00
VERSIONS = ("v1", "v2", "v3")
BOOKS = (100_000, 50_000)

v3mod = h.v3
h.hourly_path = lambda pool: f"{H38_DIR}/hourly_{pool}.pkl"  # the cache H38 built

# the same patches maker_defense_h38 applies to v3: one cost model, settle on the last hourly bar, keep the actuator
v1mod.SWAP_COST_RATE = None
v1mod.SLIPPAGE_MODEL = None
v1mod.AtTimeTrigger = h._at_bar
v1mod.Actuator = h.Capture
_v1_frame = v1mod.binance_daily_frame


def _v1_binance_frame(dsd, ded):
    """v1 has no divergence rule; run_one reports F' and the flag days, so give it F' = F and no flag."""
    frame = _v1_frame(dsd, ded)
    return frame.assign(diverged=0, Fp=frame["F"])


v1mod.binance_daily_frame = _v1_binance_frame


def run_name(version: str, book: int) -> str:
    return f"{version}_{book // 1000}k"


def run_version(job: tuple[str, int]) -> dict:
    version, book = job
    if version == "v1":
        h.v3 = v1mod  # run_one reads its strategy module through this name
    else:
        v3mod.DIVERGENCE_RULE = version == "v3"
    return h.run_safe(h.Run(run_name(version, book), initial=book))


def runs(workers: int):
    os.makedirs(RESULT_DIR, exist_ok=True)
    h.RESULT_DIR = RESULT_DIR
    jobs = [(v, b) for v in VERSIONS for b in BOOKS
            if not os.path.exists(f"{RESULT_DIR}/run_{run_name(v, b)}.csv")]
    print(f"{len(jobs)} runs: {jobs}", flush=True)
    with multiprocessing.get_context("fork").Pool(workers, maxtasksperchild=1) as pool:
        rows = pool.map(run_version, jobs, chunksize=1)
    for r in rows:
        print(r, flush=True)


def md_nav(version: str, book: int) -> pd.Series:
    nav = pd.read_csv(f"{RESULT_DIR}/nav_{run_name(version, book)}.csv", index_col=0, parse_dates=True)["net"]
    return nav / book


def combine():
    ref = pd.read_csv(f"{H38_DIR}/nav_lp_100k.csv", index_col=0, parse_dates=True)["net"]
    mine = pd.read_csv(f"{RESULT_DIR}/nav_v3_100k.csv", index_col=0, parse_dates=True)["net"]
    print(f"v3 100k here against H38 lp_100k: last {mine.iloc[-1]:.6f} / {ref.iloc[-1]:.6f}, "
          f"max abs diff {float((mine - ref.reindex(mine.index)).abs().max()):.2e}")
    btc = pd.read_csv(H45_NAV, index_col=0, parse_dates=True)["BTC half g"]
    btc = btc[(btc.index >= LO) & (btc.index < HI)]
    idx = btc.index
    out = {"BTC half g ($50k)": btc}
    for v in VERSIONS:
        out[f"md {v} ($100k)"] = md_nav(v, 100_000).reindex(idx).ffill()
    for v in VERSIONS:
        out[f"md {v} ($50k)"] = md_nav(v, 50_000).reindex(idx).ffill()
    for i, v in enumerate(VERSIONS, 1):
        out[f"P{i} = BTC g + md {v}"] = 0.5 * btc + 0.5 * out[f"md {v} ($50k)"]
    hold = pd.read_csv(f"{H38_DIR}/nav_lp_100k.csv", index_col=0, parse_dates=True)["price"].reindex(idx).ffill()
    out["hold ETH"] = hold / hold.iloc[0]
    navs = pd.DataFrame(out)
    assert not navs.isna().any().any(), navs.isna().sum()
    t = pd.DataFrame([{"book": k, **cvc.row(v, LO, HI)} for k, v in navs.items()])
    counts = []
    for v in VERSIONS:
        for b in BOOKS:
            r = pd.read_csv(f"{RESULT_DIR}/run_{run_name(v, b)}.csv").iloc[0]
            counts.append({"run": r["run"], "builds": r["builds"], "follow": r["follow_rebuilds"], "upper": r["upper"],
                           "lower": r["lower"], "fees": r["fees_collected"], "swap_fee": r["swap_fee"],
                           "impact": r["impact"], "gas": r["gas"], "F_mean": r["F_mean"],
                           "diverged_days": r["diverged_days"]})
    c = pd.DataFrame(counts)
    navs.to_csv(f"{RESULT_DIR}/navs.csv")
    t.to_csv(f"{RESULT_DIR}/combine.csv", index=False)
    c.to_csv(f"{RESULT_DIR}/counts.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(c.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


def yearly_split(parts: dict[str, pd.Series], years: list[str]) -> dict:
    """Each part's change over a calendar year, over the sum of the parts at the year's first bar (the parts add up
    to the book, so the components add up to the year's return)."""
    total = sum(parts.values())
    out = {}
    for y in years:
        seg = total[(total.index >= f"{y}-01-01") & (total.index < min(f"{int(y) + 1}-01-01", HI))]
        t0, t1 = seg.index[0], seg.index[-1]
        out[y] = {k: float((p.loc[t1] - p.loc[t0]) / total.loc[t0]) for k, p in parts.items()}
    return out


def page_data():
    """Numbers for the PnL page: yearly return and drawdown of every book, and the yearly split of each portfolio
    into the BTC half, the maker-defense half before costs, and its price impact + gas."""
    import json
    from spot_btc_eth_gate import load_prices, stats
    navs = pd.read_csv(f"{RESULT_DIR}/navs.csv", index_col=0, parse_dates=True)
    h45 = pd.read_csv(H45_NAV, index_col=0, parse_dates=True).reindex(navs.index)
    prices, _, _ = load_prices()
    btc_px = prices["btc"].reindex(navs.index).ffill()
    navs["hold BTC"] = btc_px / btc_px.iloc[0]
    navs["hold 50/50"] = 0.5 * navs["hold BTC"] + 0.5 * navs["hold ETH"]
    navs["C+g (H45)"] = h45["C+g"]
    navs["C+g+def (H45)"] = h45["C+g+def"]
    years = [y0[:4] for y0, _ in cvc.years(LO, HI)]
    series = {}
    for k, v in navs.items():
        assert not v.isna().any(), k
        st = stats(v, LO, HI)
        series[k] = {"total": float(st["total"]), "maxDD": float(st["maxDD"]),
                     "years": {y: {"ret": float(s["total"]), "mdd": float(s["maxDD"])}
                               for y in years for s in [stats(v, f"{y}-01-01", min(f"{int(y) + 1}-01-01", HI))]},
                     "year_end": {y: float(v[v.index < min(f"{int(y) + 1}-01-01", HI)].iloc[-1]) for y in years}}
    btc = navs["BTC half g ($50k)"]
    for i, v in enumerate(VERSIONS, 1):
        for book in BOOKS:
            f = pd.read_csv(f"{RESULT_DIR}/nav_{run_name(v, book)}.csv", index_col=0, parse_dates=True)
            f = f.reindex(navs.index).ffill()
            pre, cost = f["net_pre"] / book, (f["net"] - f["net_pre"]) / book
            if book == 100_000:
                series[f"md {v} ($100k)"]["attr"] = yearly_split({"md_pre": pre, "md_cost": cost}, years)
            else:
                series[f"P{i} = BTC g + md {v}"]["attr"] = yearly_split(
                    {"btc": 0.5 * btc, "md_pre": 0.5 * pre, "md_cost": 0.5 * cost}, years)
    counts = pd.read_csv(f"{RESULT_DIR}/counts.csv").set_index("run").to_dict("index")
    with open(f"{RESULT_DIR}/page.json", "w") as fh:
        json.dump({"years": years, "series": series, "counts": counts}, fh, indent=1)
    for k, s in series.items():
        print(f"{k:28s} total {s['total']:+.4f} maxDD {s['maxDD']:+.4f} "
              + " ".join(f"{y} {s['years'][y]['ret']:+.4f}/{s['years'][y]['mdd']:+.4f}" for y in years))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--runs", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--page", action="store_true")
    a.add_argument("--workers", type=int, default=2)
    a = a.parse_args()
    if a.runs:
        runs(a.workers)
    if a.combine:
        combine()
    if a.page:
        page_data()


if __name__ == "__main__":
    main()
