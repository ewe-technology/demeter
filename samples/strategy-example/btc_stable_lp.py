"""
Test 3 of preregistration.py: does a BTC/stablecoin LP beat holding the same tokens on the days the BTC gate is open?
The same diagnostic as vol_lp_check.py, on the pools of preregistration.LP_TESTS: one position of +/- width the whole
time through Demeter (hourly bars), re-centred at 00:00 when out of range, and per day

  excess = LP return - return of holding, as spot, the token mix the position had at 00:00

which is that day's fees minus impermanent loss minus re-centring costs, against an exposure-matched spot. Judged by
preregistration.lp_verdict; no strategy is designed unless it passes. Volatility buckets are shown, not judged.

Run from samples/strategy-example (the spot price cache of spot_btc_eth_gate.py must exist):
  PYTHONPATH=../.. python btc_stable_lp.py               # the Ethereum pool
  PYTHONPATH=../.. python btc_stable_lp.py --chain arbitrum
"""
import argparse
import multiprocessing
import os
import re
from datetime import date, timedelta

import pandas as pd

import preregistration as prereg
import spot_robustness as sr
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import usdc, usdt, wbtc
from vol_lp_check import PoolSleeve, daily_excess, run, summarise
from yield_layer import DATA_DIR, pool_dir

RESULT_DIR = "result/btc-stable-lp"


def sleeves(chain: str) -> list[PoolSleeve]:
    out = []
    for test in prereg.LP_TESTS:
        if test.chain != chain:
            continue
        # warms up the 30-day volatility, but never before the pool's first file; days whose volatility cannot be
        # known yet are left out by daily_excess
        files = os.listdir(f"{DATA_DIR}/{pool_dir(test.pool)}")
        first = min(date.fromisoformat(re.search(r"(\d{4}-\d\d-\d\d)\.minute", f).group(1)) for f in files)
        start = max(date.fromisoformat(test.start) - timedelta(days=31), first)
        end = date.fromisoformat(test.end)
        # WBTC is token0 in both: USDT token1 on Ethereum, USDC token1 on Arbitrum, valued in that stablecoin
        stable, tag = (usdt, "wbtcusdt") if chain == "ethereum" else (usdc, "wbtcusdc_arb")
        for width in prereg.LP_WIDTHS:
            out.append(PoolSleeve(f"{tag}_lp{width:g}", pool_dir(test.pool), wbtc, stable, stable, start, end, width,
                                  prereg.LP_CAPITAL, chain=chain))
    return out


def main(chain: str):
    os.makedirs(RESULT_DIR, exist_ok=True)
    first_day = next(t.start for t in prereg.LP_TESTS if t.chain == chain)
    prices, _, _ = load_prices()
    w = sr.gate(prices)  # the base rule: BTC above its EMA100 at 00:00
    gate_on = (w["eth"] + w["btc"] > 0)
    gate_on.index = gate_on.index.normalize()
    gate_on = gate_on[~gate_on.index.duplicated()]
    jobs = sleeves(chain)
    with multiprocessing.Pool(len(jobs)) as pool:
        results = pool.map(run, jobs)
    days, buckets, years = [], [], []
    for (name, out, ranges, secs), s in zip(results, jobs):
        out.to_csv(f"{RESULT_DIR}/sleeve_{name}.csv")
        df = daily_excess(out, ranges, gate_on).loc[first_day:]
        df.to_csv(f"{RESULT_DIR}/daily_{name}.csv")
        print(f"{name}: {len(df)} days, {len(ranges)} placements, mean excess {df['excess'].mean() * 365:+.2%}/yr, "
              f"gate open {df['gate_on'].mean():.0%} of days, {secs:.0f}s")
        days.append(df.assign(width=s.width).rename(columns={"gate_on": "gate_open"}))
        b, y = summarise(name, df)
        buckets += b
        years += y
    buckets, years = pd.DataFrame(buckets), pd.DataFrame(years)
    buckets.to_csv(f"{RESULT_DIR}/buckets_{chain}.csv", index=False)
    years.to_csv(f"{RESULT_DIR}/years_{chain}.csv", index=False)
    pd.set_option("display.width", 250)
    fmt = {"vol from": "{:.0%}".format, "vol to": "{:.0%}".format, "excess annual": "{:+.1%}".format,
           "positive days": "{:.0%}".format}
    print("\n== by 30-day volatility bucket (1 = lowest), shown only ==")
    print(buckets.to_string(index=False, formatters=fmt))
    print("\n== by year ==")
    print(years[years["days"].str.endswith("every bucket")].to_string(index=False, formatters=fmt))
    passed = prereg.lp_verdict(pd.concat(days))
    print(f"\n== preregistered verdict ({chain}): {'pass, go on to a strategy' if passed else 'fail, the idea stops'} "
          f"(every width, every year with {prereg.LP_MIN_DAYS}+ gate-open days positive, at least two such years) ==")
    print("BTC_STABLE_LP_DONE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", default="ethereum", choices=sorted({t.chain for t in prereg.LP_TESTS}))
    main(parser.parse_args().chain)
