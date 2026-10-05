"""
How much of a pool's fees one centred LP position collects as it grows, from the minute data over
2025-01-01 ~ 2025-11-09 (reports/spot_yield_and_basket.md): the D version's wstETH/WETH and WBTC/cbBTC at +/- 0.5%,
and the old LP version's ETH/USDC +/- 20% and WBTC/WETH +/- 10% for comparison.

Every minute: pool fees = volume x fee rate, and our share = our liquidity / (the pool's active liquidity + ours), with
our position always centred on that minute's price. Fees only: no impermanent loss, no wstETH ratio drift, and the
same assumption as Demeter that all of a minute's volume trades inside our range, so the levels are high. The point
is how the yield falls as the position grows.

Run from samples/strategy-example:
  PYTHONPATH=../.. python lp_capacity.py
"""
import os

import numpy as np
import pandas as pd

from tri_btc_eth_gate import ETH_POOL, RATIO_POOL
from yield_layer import CBBTC_POOL, RESULT_DIR, WSTETH_POOL, read_minutes

LO, HI = "2025-01-01", "2025-11-09 23:59"
# pool: (name, fee rate, range half-width, decimals of token1, rough USD per token1 over the window).
# Raw prices (token1 raw per token0 raw) keep every pool in raw units, whatever the decimals of token0.
POOLS = {
    WSTETH_POOL: ("wstETH/WETH", 0.0001, 0.005, 18, 3_300.0),
    CBBTC_POOL: ("WBTC/cbBTC", 0.0001, 0.005, 8, 100_000.0),
    ETH_POOL: ("ETH/USDC", 0.0005, 0.20, 18, 3_300.0),  # token0 USDC, token1 WETH
    RATIO_POOL: ("WBTC/WETH", 0.0005, 0.10, 18, 3_300.0),  # token0 WBTC, token1 WETH
}
SIZES_USD = (10_000, 100_000, 1_000_000, 10_000_000)


def liquidity_per_token1(p: np.ndarray, width: float) -> np.ndarray:
    """Raw liquidity of one raw unit of token1 value in a +/- width range centred on raw price p (token1 per token0)."""
    pa, pb = p * (1 - width), p * (1 + width)
    return 1 / (2 * np.sqrt(p) - p / np.sqrt(pb) - np.sqrt(pa))


if __name__ == "__main__":
    os.makedirs(RESULT_DIR, exist_ok=True)
    rows = []
    for address, (name, fee, width, decimals, usd) in POOLS.items():
        df = read_minutes(address, ("timestamp", "closeTick", "inAmount0", "inAmount1", "currentLiquidity")).loc[LO:HI]
        df = df.dropna(subset=["closeTick", "currentLiquidity"])
        p = 1.0001 ** df["closeTick"].to_numpy()  # raw token1 per raw token0
        fees1 = (df["inAmount0"].to_numpy() * p + df["inAmount1"].to_numpy()) * fee  # raw token1
        pool_l = df["currentLiquidity"].to_numpy()
        days = (df.index[-1] - df.index[0]).total_seconds() / 86400
        volume_usd = (fees1 / fee).sum() / 10 ** decimals * usd
        print(f"{name}: {days:.0f} days, volume ~${volume_usd / days / 1e6:.1f}M a day, "
              f"all LP fees ~${fees1.sum() / 10 ** decimals * usd / days:,.0f} a day")
        for size in SIZES_USD:
            value1 = size / usd * 10 ** decimals  # raw token1
            ours = value1 * liquidity_per_token1(p, width)
            share = ours / (pool_l + ours)
            earned = (fees1 * share).sum() / 10 ** decimals * usd
            rows.append({"pool": name, "width": width, "size $": size, "fee yield a year": earned / size * 365 / days,
                         "average share": share.mean()})
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/capacity.csv", index=False)
    print(table.to_string(index=False, formatters={"size $": "{:,.0f}".format, "fee yield a year": "{:.2%}".format,
                                                   "average share": "{:.2%}".format}))
