"""
Test 2 of preregistration.py: is the gate's BTC price, derived as ETH/USDC x WBTC/WETH, close enough to a direct
BTC/stablecoin price, or should the gate read the direct one?

Both prices come straight from the minute files, as the last trade at or before each 00:00 UTC (the moment the gate
reads), so the two differ only in source, never in timing. The direct price of a calendar year is the pool of
preregistration.BTC_STABLE_POOLS with the highest median daily volume that year.

Decided by preregistration.price_source_verdict on the share of days whose closes differ by more than CLOSE_GAP.
Also reported, not used to decide: the days the EMA100 gate is in a different state, and the base rule (A, exchange,
10 bps, one tranche at 00:00) run on each gate, traded at the same derived hourly prices.

Run from samples/strategy-example (the spot price cache of spot_btc_eth_gate.py must exist):
  PYTHONPATH=../.. python gate_price_source.py
"""
import glob
import os

import numpy as np
import pandas as pd

import preregistration as prereg
import spot_robustness as sr
from sleeve_sim import simulate
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import ETH_POOL, RATIO_POOL

RESULT_DIR = "result/gate-price"
DATA_DIR = "../real-data"
SPAN = prereg.EMA_SPAN
PERIODS = {"2022-2025": ("2022-01-01", "2026-01-01"), "holdout 2026": prereg.HOLDOUT}


def read_pool(address: str, decimals0: int, decimals1: int) -> pd.DataFrame:
    """Traded minutes: price = token1 per token0, and the amounts swapped in of both tokens."""
    # pool folders keep the checksum case of the address, which the lists in preregistration.py may not
    folder = next(d for d in os.listdir(DATA_DIR) if d.lower() == address.lower())
    files = sorted(glob.glob(f"{DATA_DIR}/{folder}/*.minute.csv"))
    cols = ["timestamp", "closeTick", "inAmount0", "inAmount1"]
    df = pd.concat((pd.read_csv(f, usecols=cols) for f in files), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in cols[1:]:  # 18-decimal amounts overflow int64 and load as str
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df = df.set_index("timestamp").sort_index()
    df["price"] = 1.0001 ** df["closeTick"] * 10.0 ** (decimals0 - decimals1)
    df["in0"], df["in1"] = df["inAmount0"] / 10 ** decimals0, df["inAmount1"] / 10 ** decimals1
    return df[(df["in0"] > 0) | (df["in1"] > 0)]


def at_midnight(price: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """The last traded price at or before each 00:00 (a close of minute m is known from m + 1 on)."""
    known = price.copy()
    known.index = known.index + pd.Timedelta(minutes=1)
    return known.reindex(days.union(known.index)).ffill().reindex(days)


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    eth = read_pool(ETH_POOL, 6, 18)  # USDC / WETH: WETH per USDC
    ratio = read_pool(RATIO_POOL, 8, 18)  # WBTC / WETH: WETH per WBTC
    days = pd.date_range("2021-05-06", "2026-09-30", freq="D")
    derived = (at_midnight(ratio["price"], days) / at_midnight(eth["price"], days)).rename("derived")

    # the spot cache's 00:00 BTC price is what the backtests used; the derived close here should match it
    prices, _, _ = load_prices()
    cache = sr.closes(prices)["btc"]
    check = (derived.reindex(cache.index) / cache - 1).abs().dropna()
    print(f"derived vs spot cache at 00:00: median |gap| {check.median():.4%}, p99 {check.quantile(0.99):.4%}")

    direct_by_pool, volume = {}, {}
    for name, address in prereg.BTC_STABLE_POOLS.items():
        df = read_pool(address, 8, 6)  # WBTC is token0 in all three: stablecoin per WBTC
        direct_by_pool[name] = at_midnight(df["price"], days)
        volume[name] = (df["in1"] + df["in0"] * df["price"]).resample("D").sum().reindex(days, fill_value=0.0)
    volume = pd.DataFrame(volume)
    chosen = volume.groupby(volume.index.year).median().idxmax(axis=1)
    direct = pd.Series(np.nan, index=days, name="direct")
    for year, name in chosen.items():
        mask = days.year == year
        direct[mask] = direct_by_pool[name][mask]

    both = pd.concat([derived, direct], axis=1).dropna()
    gap = (both["derived"] / both["direct"] - 1).abs()
    gate = {k: both[k] > both[k].ewm(span=SPAN, adjust=False).mean() for k in ("derived", "direct")}
    differ = gate["derived"] != gate["direct"]

    rows = []
    for year, idx in both.groupby(both.index.year).groups.items():
        rows.append({"year": year, "direct pool": chosen[year],
                     "median daily volume $M": volume.loc[volume.index.year == year, chosen[year]].median() / 1e6,
                     "days": len(idx), f"days |gap| > {prereg.CLOSE_GAP:.1%}": int((gap[idx] > prereg.CLOSE_GAP).sum()),
                     "median |gap| %": 100 * gap[idx].median(), "max |gap| %": 100 * gap[idx].max(),
                     "gate differs days": int(differ[idx].sum())})
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/by_year.csv", index=False)
    pd.concat([both, gap.rename("gap"), gate["derived"].rename("gate derived"), gate["direct"].rename("gate direct")],
              axis=1).to_csv(f"{RESULT_DIR}/daily.csv")
    pd.set_option("display.width", 250)
    print("\n" + table.round(3).to_string(index=False))

    print("\nreported, not deciding: the base rule on each gate (A, exchange, 10 bps, 00:00), same trade prices")
    values = pd.DataFrame({"eth": prices["eth"], "btc": prices["btc"], "cash": 1.0}, index=prices.index)
    nav_rows = []
    for k in ("derived", "direct"):
        on = gate[k].astype(float)
        w = pd.DataFrame({"eth": 0.5 * on, "btc": 0.5 * on}).reindex(prices.index).ffill().fillna(0.0)
        for label, (lo, hi) in PERIODS.items():
            nav, trades, _ = simulate(w, values, start=lo, cost_bps=10)
            nav = nav[nav.index < hi]
            st = sr.stats(nav, lo, hi)
            nav_rows.append({"gate": k, "period": label, "total": st["total"], "maxDD": st["maxDD"], "trades": trades})
    navs = pd.DataFrame(nav_rows)
    navs.to_csv(f"{RESULT_DIR}/base_rule.csv", index=False)
    print(navs.to_string(index=False, formatters={"total": "{:+.1%}".format, "maxDD": "{:+.1%}".format}))

    verdict = prereg.price_source_verdict(both["derived"], both["direct"])
    print(f"\n== preregistered verdict: {verdict} "
          f"({(gap > prereg.CLOSE_GAP).mean():.2%} of days differ by more than {prereg.CLOSE_GAP:.1%}, "
          f"limit {prereg.MAX_GAP_DAYS:.0%}) ==")
    print("GATE_PRICE_DONE")


if __name__ == "__main__":
    main()
