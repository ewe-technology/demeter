"""
H1 of reports/single_pool_loop.md: does the fee / LVR ratio of an always-centred LP differ enough between pools that
some pool clears 1.5 in every year?

Same reference position as single_pool_edge.py (always centred at +/-10%, never out of range, re-centres for free),
over every BTC/ETH, BTC/stable and ETH/stable pool already on the backtest host, one calendar year at a time
(2026 to 09-30). Two sizes:

  small   our share of the minute's fees is fee_rate x flow / L_pool                (as in single_pool_edge.py)
  $100k   our own liquidity joins the denominator: fee_rate x flow / (L_pool + L_own),
          L_own = $100k in token1 raw / value of one unit of L (re-sized every minute with the day's USD price)

The loss (LVR) does not depend on size. The ETH price for WETH-quoted pools comes from 88e6 (daily close).

Verdict, fixed before the run (commit of this file):
  a year counts if the pool has data from Jan 1 and >= 180 days that carry trades (2026 ends 09-30);
  a pool passes if it has >= 2 counting full calendar years (2022-2025), and in every counting year (2026 included)
  the $100k fee / loss >= 1.5 and the $100k edge > 0.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  python pool_screen.py
"""
import glob
import os

import numpy as np
import pandas as pd

RESULT_DIR = "result/pool-screen"
YEARS = range(2022, 2027)
LAST_DAY = pd.Timestamp("2026-09-30")
K = 1.10
CAPITAL = 100_000
MIN_PER_YEAR = 365 * 24 * 60
MIN_TRADE_DAYS = 180
PASS_RATIO = 1.5

# name: (address, fee rate, token1 decimals, token1 is WETH). Token order and fee read on chain 2026-10-07.
POOLS = {
    "eth/usdc 5 mainnet": ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.0005, 18, True),  # USDC / WETH
    "eth/usdc 5 arbitrum": ("0xC6962004f452bE9203591991D15f6b388e09E8D0", 0.0005, 6, False),  # WETH / USDC
    "wbtc/usdc 30 mainnet": ("0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35", 0.003, 6, False),
    "wbtc/usdt 30 mainnet": ("0x9Db9e0e53058C89e5B94e29621a205198648425B", 0.003, 6, False),
    "wbtc/usdt 5 mainnet": ("0x56534741CD8B152df6d48AdF7ac51f75169A83b2", 0.0005, 6, False),
    "wbtc/usdc 5 arbitrum": ("0x0E4831319A50228B9e450861297aB92dee15B44F", 0.0005, 6, False),
    "wbtc/weth 5 mainnet": ("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.0005, 18, True),
    "wbtc/weth 5 arbitrum": ("0x2f5e87C9312fa29aed5c179E456625D79015299c", 0.0005, 18, True),
}


def files_of(address: str) -> list[str]:
    files = glob.glob(f"../real-data/{address}/*.minute.csv")
    return sorted(f for f in files if int(os.path.basename(f)[-21:-17]) in YEARS)


def load_minutes(address: str) -> tuple[pd.DataFrame, pd.Series]:
    """Minute bars on a full grid (ticks and liquidity carried over gaps, no flow), plus trade days per year."""
    cols = ["timestamp", "closeTick", "inAmount0", "inAmount1", "currentLiquidity"]
    df = pd.concat((pd.read_csv(f, usecols=cols) for f in files_of(address)), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["closeTick", "currentLiquidity"]).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated()]
    df = df[df.index < LAST_DAY + pd.Timedelta(days=1)]
    trade_days = pd.Series(df.index.normalize().unique()).dt.year.value_counts().sort_index()
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1min"))
    df[["closeTick", "currentLiquidity"]] = df[["closeTick", "currentLiquidity"]].ffill()
    df[["inAmount0", "inAmount1"]] = df[["inAmount0", "inAmount1"]].fillna(0.0)
    return df.astype(float), trade_days


def edge_frame(df: pd.DataFrame, fee_rate: float, usd_per_raw1: np.ndarray) -> pd.DataFrame:
    sp = np.power(1.0001, df["closeTick"].to_numpy() / 2)
    sp0 = np.concatenate(([sp[0]], sp[:-1]))
    value = 2 * sp0 * (1 - K ** -0.5)  # token1 raw per unit of L
    flow = df["inAmount0"].to_numpy() * sp0 ** 2 + df["inAmount1"].to_numpy()
    liq = df["currentLiquidity"].to_numpy()
    own = CAPITAL / usd_per_raw1 / value
    return pd.DataFrame({
        "fee": fee_rate * flow / liq / value,
        "fee_100k": fee_rate * flow / (liq + own) / value,
        "loss": (sp - sp0) ** 2 / sp0 / value,
        "volume_usd": flow * usd_per_raw1,
    }, index=df.index)


def per_year(m: pd.Series) -> pd.Series:
    g = m.groupby(m.index.year)
    return g.sum() / (g.size() / MIN_PER_YEAR)


def screen(name: str, eth_usd: pd.Series) -> pd.DataFrame:
    address, fee_rate, dec1, token1_weth = POOLS[name]
    df, trade_days = load_minutes(address)
    usd_per_raw1 = np.full(len(df), 10.0 ** -dec1)
    if token1_weth:
        usd_per_raw1 *= eth_usd.reindex(df.index.normalize()).ffill().bfill().to_numpy()
    e = edge_frame(df, fee_rate, usd_per_raw1)
    t = pd.DataFrame({"fee": per_year(e["fee"]), "fee_100k": per_year(e["fee_100k"]), "loss": per_year(e["loss"])})
    t["edge"] = t["fee"] - t["loss"]
    t["edge_100k"] = t["fee_100k"] - t["loss"]
    t["ratio"] = t["fee"] / t["loss"]
    t["ratio_100k"] = t["fee_100k"] / t["loss"]
    t["volume_musd_day"] = e["volume_usd"].groupby(e.index.year).sum() / e.groupby(e.index.year).size() * 1440 / 1e6
    t["trade_days"] = trade_days.reindex(t.index).fillna(0).astype(int)
    t["full_year"] = [df.index[0].normalize() <= pd.Timestamp(f"{y}-01-01") for y in t.index]  # data on Jan 1
    t["counts"] = t["full_year"] & (t["trade_days"] >= MIN_TRADE_DAYS)
    t.insert(0, "pool", name)
    return t.rename_axis("year").reset_index()


def verdict(t: pd.DataFrame) -> str:
    c = t[t["counts"]]
    if (c["year"] < 2026).sum() < 2:
        return "too short"
    ok = (c["ratio_100k"] >= PASS_RATIO) & (c["edge_100k"] > 0)
    return "PASS" if ok.all() else f"fail ({', '.join(str(y) for y in c.loc[~ok, 'year'])})"


def main() -> None:
    os.makedirs(RESULT_DIR, exist_ok=True)
    tick = load_minutes(POOLS["eth/usdc 5 mainnet"][0])[0]["closeTick"].resample("1D").last()
    eth_usd = 1e12 / np.power(1.0001, tick)  # 88e6 price is WETH raw per USDC raw
    tables = []
    for name in POOLS:
        t = screen(name, eth_usd)
        tables.append(t)
        print(f"\n== {name}: {verdict(t)}", flush=True)
        print(t.drop(columns="pool").to_string(index=False, float_format=lambda x: f"{x:.3f}"), flush=True)
    pd.concat(tables, ignore_index=True).to_csv(f"{RESULT_DIR}/years.csv", index=False)
    pd.DataFrame({"pool": list(POOLS), "verdict": [verdict(t) for t in tables]}).to_csv(
        f"{RESULT_DIR}/verdict.csv", index=False)


if __name__ == "__main__":
    main()
