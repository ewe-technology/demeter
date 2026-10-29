"""
QUAN-1213: the fee denominator (market_status.data.currentLiquidity) adds only our own liquidity that earns a fee in
the current minute when UniLpMarket.fee_in_range_liquidity is on; off (default) adds all of it, as before.

Runs on either engine, from tests/: PYTHONPATH=.. ../.venv-lab/bin/python -m unittest uni_lp_fee_in_range_test (python)
or ../.venv-rs/bin/python -m unittest uni_lp_fee_in_range_test (Rust; from the repo root, python would import demeter/).
"""
import unittest
from decimal import Decimal

import pandas as pd

from demeter import Broker, MarketInfo, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool, UniswapMarketStatus

POOL_LIQ = 58280013108171131649
TICK = 200000


class FeeInRangeLiquidityTest(unittest.TestCase):
    def setUp(self):
        eth, usdc = TokenInfo(name="eth", decimal=18), TokenInfo(name="usdc", decimal=6)
        self.market = UniLpMarket(MarketInfo("lp"), UniV3Pool(usdc, eth, 0.05, usdc))
        broker = Broker()
        broker.add_market(self.market)
        self.set_tick(TICK)
        broker.set_balance(eth, 10)
        broker.set_balance(usdc, 100000)
        # in range, below the price (only token0 / quote), above the price (only base)
        self.inside = self.market.add_liquidity_by_tick(TICK - 1000, TICK + 1000, Decimal(1), Decimal(1000), tick=TICK)[0]
        self.below = self.market.add_liquidity_by_tick(TICK - 3000, TICK - 2000, Decimal(1), Decimal(1000), tick=TICK)[0]
        self.above = self.market.add_liquidity_by_tick(TICK + 2000, TICK + 3000, Decimal(1), Decimal(1000), tick=TICK)[0]

    def set_tick(self, tick):
        price = self.market.tick_to_price(tick)
        self.market.set_market_status(
            UniswapMarketStatus(
                timestamp=None,
                data=pd.Series(data=[10**18, 10**9, POOL_LIQ, tick, price],
                               index=["inAmount0", "inAmount1", "currentLiquidity", "closeTick", "price"]),
            ),
            price=None,
        )

    def liq(self, key):
        return int(self.market.positions[key].liquidity)

    def denominator(self):
        return int(self.market.market_status.data.currentLiquidity)

    def test_flag_is_off_by_default(self):
        self.assertFalse(self.market.fee_in_range_liquidity)

    def test_off_counts_all_own_liquidity(self):
        self.set_tick(TICK)
        self.assertEqual(self.denominator(), POOL_LIQ + self.liq(self.inside) + self.liq(self.below) + self.liq(self.above))

    def test_on_counts_only_in_range_liquidity(self):
        self.market.fee_in_range_liquidity = True
        self.set_tick(TICK)
        self.assertEqual(self.denominator(), POOL_LIQ + self.liq(self.inside))

    def test_on_counts_a_position_the_price_crossed_this_minute(self):
        # the price moves from TICK to TICK - 2500: it ends inside `below` and crossed `inside`'s lower part
        self.market.fee_in_range_liquidity = True
        self.set_tick(TICK - 2500)
        self.assertEqual(self.denominator(), POOL_LIQ + self.liq(self.inside) + self.liq(self.below))

    def test_on_skips_a_range_the_price_only_touched_at_its_edge(self):
        # TICK -> TICK + 2000: ends exactly on `above`'s lower tick, which update_fee pays no fee for (zero overlap)
        self.market.fee_in_range_liquidity = True
        self.set_tick(TICK + 1000)   # leave `inside` (upper tick is exclusive)
        self.set_tick(TICK + 2000)
        self.assertEqual(self.denominator(), POOL_LIQ)


if __name__ == "__main__":
    unittest.main()
