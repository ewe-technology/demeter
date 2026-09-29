"""
Time one remix_dao_gamma configuration on whichever `demeter` is importable.

    cd samples/strategy-example
    # python engine
    PYTHONPATH=../.. ../../rust/.venv/bin/python ../../rust/golden/bench_gamma.py 2022-01-01 2022-03-31
    # rust engine
    ../../rust/.venv/bin/python ../../rust/golden/bench_gamma.py 2022-01-01 2022-03-31 [--no-legacy]
"""

import copy
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.getcwd())

import demeter  # noqa: E402
from demeter import TokenInfo, MarketInfo, ChainType  # noqa: E402
from demeter.data import CacheManager  # noqa: E402

CacheManager.load = staticmethod(lambda key: None)
CacheManager.save = staticmethod(lambda key, df: None)

import remix_dao_gamma as g  # noqa: E402
from remix_dao_utils import RemixDAOParams  # noqa: E402
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy, DcaTiming, DcaAddition  # noqa: E402

start, end = (date.fromisoformat(a) for a in sys.argv[1:3])
legacy = "--no-legacy" not in sys.argv
engine = "rust" if hasattr(demeter, "_rs") else "python"

if engine == "rust" and not legacy:
    _orig_init = demeter.Actuator.__init__

    def _init(self, *a, **k):
        _orig_init(self, *a, **k)
        self.legacy_quirks = False

    demeter.Actuator.__init__ = _init

usdc = TokenInfo(name="usdc", decimal=6)
eth = TokenInfo(name="eth", decimal=18)
contract = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
gp = GlobalParams(token0=usdc, token1=eth, fee=0.05, init_quote=Decimal(100000), quote_token=usdc, base_token=eth,
                  chain_name=ChainType.ethereum.name, contract_address=contract, swap_fee=False,
                  dca_usdc_amount=Decimal(10000), dca_add_if_non_empty=False, dca_add_timing=DcaTiming.none,
                  init_quote_usdc=Decimal(100000), dca_addon_price_percent=Decimal(0),
                  dca_addon_amount_percent=Decimal(0), dca_addition=DcaAddition.none)
params = RemixDAOParams(tick_spread_upper=410, tick_spread_lower=410, tick_upper_boundary_offset=0,
                        tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                        rescale_tick_lower_boundary_offset=0, init_tick_spread=410, tick_spacing=10,
                        tick_gap_lower=1, tick_gap_upper=1)
folder = f"/tmp/bench_gamma_{engine}"
os.makedirs(folder, exist_ok=True)

t0 = time.time()
market = g.UniLpMarketV2(MarketInfo("lp"), g.UniV3Pool(usdc, eth, 0.05, usdc))
market.data_path = f"../real-data/{contract}"
market.load_data(ChainType.ethereum.name, contract, start, end)
t_load = time.time() - t0

tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1, report_name="bench", indicator_length_hr=1,
                to_swap=False, aggressive=True, compound=False, rescale_frequency=RescaleFrequency.hourly,
                cal_start_datetime=datetime(start.year, start.month, start.day), data_start_date=start,
                data_end_date=end, folder=folder, initial_swap=True, flip_param_dates=[], start_with_bull_param=True,
                initial_type=1, starting_mark_price=Decimal(20))
import contextlib, io  # noqa: E401,E402

t1 = time.time()
with contextlib.redirect_stdout(io.StringIO()):
    m = g.run_test(copy.copy(params), copy.copy(params), tp, gp, market.data, market.data, shape="triangle",
                   ratio=Decimal("0.05"))
t_run = time.time() - t1
bars = len(market.data)
print(f"engine={engine} legacy={legacy} bars={bars} load={t_load:.2f}s run={t_run:.2f}s "
      f"({t_run / bars * 1e6:.1f} us/bar) rescales={m['rescale_count']} total_net_value={m['total_net_value']} "
      f"total_fee={m['total_fee']}")
