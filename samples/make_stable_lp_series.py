"""
EXP-052 (v6.39): daily net return of $1 LP'd in the mainnet Uniswap v3 USDC/USDT pool, for v6's idle USDC.

Position: one range [-W, +W) ticks around the peg (tick 0), never moved, reference size REF_USD (its own share of
the pool's in-range liquidity dilutes its fee take). Per minute with the close tick inside the range it earns
fee x swap volume x L / (L_pool + L); outside the range it earns nothing. The position is marked to market in USDC
at each day's last close tick (token0 = USDC, token1 = USDT in both pools, both 6 decimals, price = 1.0001^tick
USDT per USDC). Pool by date: USDC/USDT 0.05% `0x7858...` before 2021-11-15 (the 0.01% pool did not exist yet),
USDC/USDT 0.01% `0x3416...` from 2021-11-15 (the deeper pool since then).

usage: python make_stable_lp_series.py   (reads stable-data/, writes stable_lp_daily.csv)
"""
import glob
import os
from datetime import date

import numpy as np
import pandas as pd

W = 10                      # half-width in ticks (±0.1%): the pair's normal peg wander, fixed in the pre-registration
REF_USD = 100_000.0
POOLS = [("0x7858e59e0c01ea06df3af3d20ac7b0003275d4bf", 0.0005, date(2021, 5, 5), date(2021, 11, 14)),
         ("0x3416cf6c708da44db2624d63ea0aaef7113527c6", 0.0001, date(2021, 11, 15), date(2026, 9, 17))]
HERE = os.path.dirname(os.path.abspath(__file__))
SQ = lambda t: 1.0001 ** (np.asarray(t, dtype=float) / 2)
SQA, SQB = SQ(-W), SQ(W)
L_PER_RAW = 1.0 / (2 * (1 - 1.0001 ** (-W / 2)))   # liquidity per raw unit of value at the peg (V = 2L(1 - sqrt(pa)))
L_REF = REF_USD * 1e6 * L_PER_RAW


def value(tick) -> np.ndarray:
    """USDC value (raw) of the reference position at `tick` (clamped to the range)."""
    s = np.clip(SQ(tick), SQA, SQB)
    x = L_REF * (1 / s - 1 / SQB)
    y = L_REF * (s - SQA)
    return x + y / (s * s)


def day_stats(path: str, fee: float) -> tuple[float, float, float] | None:
    m = pd.read_csv(path)
    if m.empty:
        return None
    t = m["closeTick"].astype(float)
    p = 1.0001 ** t
    vol = m["inAmount0"].astype(float) + m["inAmount1"].astype(float) / p
    liq = m["currentLiquidity"].astype(float)
    inside = (t >= -W) & (t < W)
    earned = (fee * vol * L_REF / (liq + L_REF)).where(inside, 0.0).sum()
    return earned / 1e6, float(t.iloc[-1]), float(inside.mean())


def main():
    rows = []
    for pool, fee, first, last in POOLS:
        for f in sorted(glob.glob(os.path.join(HERE, "stable-data", pool, f"ethereum-{pool}-*.minute.csv"))):
            d = date.fromisoformat(f[-21:-11])
            if not first <= d <= last:
                continue
            s = day_stats(f, fee)
            if s is not None:
                rows.append({"date": d, "pool": pool[:6], "fee_usd": s[0], "close_tick": s[1], "in_range_share": s[2]})
    df = pd.DataFrame(rows).set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)
    full = pd.date_range(df.index[0], df.index[-1], freq="D")
    df = df.reindex(full)
    df["fee_usd"] = df["fee_usd"].fillna(0.0)
    df["close_tick"] = df["close_tick"].ffill()
    v = value(df["close_tick"].to_numpy())
    mark = np.r_[0.0, v[1:] / v[:-1] - 1]
    df["fee_ret"] = df["fee_usd"] / REF_USD
    df["mark_ret"] = mark
    df["ret"] = df["fee_ret"] + df["mark_ret"]
    df.index.name = "date"
    out = os.path.join(HERE, "stable_lp_daily.csv")
    df[["pool", "fee_ret", "mark_ret", "ret", "in_range_share", "close_tick"]].to_csv(out)
    yearly = df.groupby(df.index.year).agg(fee_apr=("fee_ret", "sum"), mark=("mark_ret", "sum"), days=("ret", "size"))
    print(yearly.to_string())
    print("written", out, len(df), "days")


if __name__ == "__main__":
    main()
