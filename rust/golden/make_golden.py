"""
Produce golden reference outputs from the ORIGINAL pure-python demeter engine.

Run from samples/strategy-example (the strategy uses relative imports and data paths):

    cd samples/strategy-example
    PYTHONPATH=../.. ../../rust/.venv/bin/python ../../rust/golden/make_golden.py

Outputs go to rust/golden/out/. The Rust port is checked against these files.
Nothing is written to ~/.demeter: the data cache is disabled while this runs.
"""

import json
import os
import random
import shutil
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

OUT = Path(os.environ.get("GOLDEN_OUT", Path(__file__).resolve().parent / "out"))
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, os.getcwd())

import demeter  # noqa: E402
from demeter.data import CacheManager  # noqa: E402
from demeter.core import actuator as actuator_module  # noqa: E402
from demeter.uniswap import helper, liquitidy_math, UniV3Pool, UniLpMarket  # noqa: E402
from demeter import TokenInfo, MarketInfo, ChainType  # noqa: E402

# ---------------------------------------------------------------- no cache
CacheManager.load = staticmethod(lambda key: None)
CacheManager.save = staticmethod(lambda key, df: None)


# ---------------------------------------------------------------- capture every account_status_df
_original_run = actuator_module.Actuator.run
_run_counter = {"n": 0}


def _run_and_dump(self, print_result: bool = True):
    _original_run(self, print_result)
    _run_counter["n"] += 1
    name = getattr(self, "golden_name", None) or f"run{_run_counter['n']}"
    self.account_status_df.to_csv(OUT / f"account_{name}.csv")
    actions = [
        {"t": a.timestamp.strftime("%Y-%m-%d %H:%M:%S"), "type": a.action_type.name, "text": str(vars(a))}
        for a in self.actions
    ]
    with open(OUT / f"actions_{name}.json", "w") as f:
        json.dump(actions, f, indent=0, default=str)


actuator_module.Actuator.run = _run_and_dump


def dec(x) -> str:
    return str(x)


# ---------------------------------------------------------------- 1. math vectors
def make_math_vectors():
    rnd = random.Random(42)
    ticks = sorted(
        set(
            [0, 1, -1, 2, -2, 10, -10, 887272, -887272, 887271, -887271, 194197, -194197, 200000, -276324, 276324]
            + [rnd.randint(-887272, 887272) for _ in range(300)]
            + [rnd.randint(-300000, 300000) for _ in range(300)]
        )
    )
    sqrt_at_tick = {str(t): str(liquitidy_math.get_sqrt_ratio_at_tick(t)) for t in ticks}

    decimal_pairs = [(6, 18), (18, 6), (8, 18), (18, 18), (6, 6), (8, 8)]
    tick_price = []
    for t in [x for x in ticks if abs(x) < 400000][:250]:
        for d0, d1 in decimal_pairs:
            for q in (True, False):
                tick_price.append([t, d0, d1, q, dec(helper.tick_to_base_unit_price(t, d0, d1, q))])

    price_tick = []
    prices = ["3000", "3712.12345", "0.0003", "1", "1.0001", "0.99985", "25000.5", "16.5", "0.0625", "123456.789"]
    for p in prices:
        for d0, d1 in decimal_pairs:
            for q in (True, False):
                try:
                    pd_ = Decimal(p)
                    tick = helper.base_unit_price_to_tick(pd_, d0, d1, q)
                    sqrt = helper.base_unit_price_to_sqrt_price_x96(pd_, d0, d1, q)
                    back = helper.sqrt_price_x96_to_base_unit_price(sqrt, d0, d1, q)
                    stt = helper.sqrt_price_x96_to_tick(sqrt)
                    price_tick.append([p, d0, d1, q, tick, str(sqrt), dec(back), stt])
                except Exception as e:  # out of range
                    price_tick.append([p, d0, d1, q, None, None, None, None])

    nearest = []
    for t in [-15, -10, -5, -4, -1, 0, 4, 5, 6, 15, 25, 35, 887272, -887272, 194195, -194205]:
        for s in [1, 10, 60, 200]:
            nearest.append([t, s, helper.nearest_usable_tick(t, s)])

    liq = []
    for (sp, lo, hi) in [(194197, 193000, 195000), (194197, 195000, 196000), (194197, 190000, 193000),
                         (-194197, -195000, -193000), (0, -100, 100), (201234, 200000, 202000), (60, -60, 60)]:
        sqrt = liquitidy_math.get_sqrt_ratio_at_tick(sp)
        for (a0, a1) in [("1000", "0.5"), ("100000", "10"), ("0.001", "0.000001"), ("0", "5"), ("5", "0"),
                         ("12345.678901", "3.14159265358979")]:
            for d0, d1 in [(6, 18), (18, 6), (18, 18)]:
                L = liquitidy_math.get_liquidity(sqrt, lo, hi, Decimal(a0), Decimal(a1), d0, d1)
                am0, am1 = liquitidy_math.get_amounts(sqrt, lo, hi, L, d0, d1)
                liq.append([sp, lo, hi, a0, a1, d0, d1, str(L), dec(am0), dec(am1)])

    with open(OUT / "math_vectors.json", "w") as f:
        json.dump(
            {"sqrt_at_tick": sqrt_at_tick, "tick_price": tick_price, "price_tick": price_tick, "nearest": nearest,
             "liquidity": liq},
            f,
        )
    print(f"math vectors: {len(sqrt_at_tick)} ticks, {len(tick_price)} tick->price, {len(price_tick)} price->tick, "
          f"{len(liq)} liquidity cases")


# ---------------------------------------------------------------- 2. loaded market data
def make_market_data():
    usdc = TokenInfo(name="usdc", decimal=6)
    eth = TokenInfo(name="eth", decimal=18)
    pool = UniV3Pool(usdc, eth, 0.05, usdc)
    market = UniLpMarket(MarketInfo("lp"), pool)
    market.data_path = "../real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    market.load_data(ChainType.ethereum.name, "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", date(2022, 1, 1),
                     date(2022, 1, 3))
    market.data.to_csv(OUT / "market_data_eth_usdc_20220101_20220103.csv")
    print("market data:", market.data.shape)


# ---------------------------------------------------------------- 3. quick start sample
def run_quick_start():
    import importlib.util
    spec = importlib.util.spec_from_file_location("quick_start", "01_quick_start.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # module defines MyFirstStrategy; its __main__ block won't run
    usdc = TokenInfo(name="usdc", decimal=6)
    eth = TokenInfo(name="eth", decimal=18)
    pool = UniV3Pool(token0=usdc, token1=eth, fee=0.05, quote_token=usdc)
    market_key = MarketInfo("U2EthPool")
    market = UniLpMarket(market_key, pool)
    market.data_path = "../data"
    market.load_data(ChainType.polygon.name, "0x45dda9cb7c25131df268515131f647d726f50608", date(2023, 8, 15),
                     date(2023, 8, 15))
    actuator = demeter.Actuator()
    actuator.golden_name = "quick_start"
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, 10000)
    actuator.broker.set_balance(eth, 10)
    actuator.strategy = mod.MyFirstStrategy()
    actuator.set_price(market.get_price_from_data())
    actuator.run(False)


# ---------------------------------------------------------------- 4. remix_dao_gamma, one week
def run_gamma():
    import remix_dao_gamma as g
    import time as _time

    _time.sleep = lambda s: None  # skip the stagger delay
    csd, dsd, ded = datetime(2022, 1, 1), date(2022, 1, 1), date(2022, 1, 7)
    g.process_for_date(csd, dsd, ded, "", [])
    # copy the result folder the strategy wrote
    for folder in Path("result").glob("ISAO-gamma-*-20220101-20220107"):
        dst = OUT / "gamma_result"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(folder, dst)
        print("gamma results copied from", folder)


if __name__ == "__main__":
    which = sys.argv[1:] or ["math", "data", "quick", "gamma"]
    if "math" in which:
        make_math_vectors()
    if "data" in which:
        make_market_data()
    if "quick" in which:
        run_quick_start()
    if "gamma" in which:
        run_gamma()


# ---------------------------------------------------------------- 5. remix_dao_gamma, narrow range so rescales happen
def run_gamma_narrow():
    import copy as _copy
    import remix_dao_gamma as g
    from remix_dao_utils import RemixDAOParams
    from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy, DcaTiming, DcaAddition

    usdc = TokenInfo(name="usdc", decimal=6)
    eth = TokenInfo(name="eth", decimal=18)
    contract = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    csd, dsd, ded = datetime(2022, 1, 1), date(2022, 1, 1), date(2022, 1, 14)
    gp = GlobalParams(token0=usdc, token1=eth, fee=0.05, init_quote=Decimal(100000), quote_token=usdc,
                      base_token=eth, chain_name=ChainType.ethereum.name, contract_address=contract,
                      swap_fee=False, dca_usdc_amount=Decimal(10000), dca_add_if_non_empty=False,
                      dca_add_timing=DcaTiming.none, init_quote_usdc=Decimal(100000),
                      dca_addon_price_percent=Decimal(0), dca_addon_amount_percent=Decimal(0),
                      dca_addition=DcaAddition.none)
    params = RemixDAOParams(tick_spread_upper=410, tick_spread_lower=410, tick_upper_boundary_offset=0,
                            tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                            rescale_tick_lower_boundary_offset=0, init_tick_spread=410, tick_spacing=10,
                            tick_gap_lower=1, tick_gap_upper=1)
    folder = str(OUT / "gamma_narrow")
    Path(folder).mkdir(parents=True, exist_ok=True)
    market = g.UniLpMarketV2(MarketInfo("lp"), UniV3Pool(usdc, eth, 0.05, usdc))
    market.data_path = f"../real-data/{contract}"
    market.load_data(ChainType.ethereum.name, contract, dsd, ded)
    results = []
    for shape, ratio, freq in [("triangle", Decimal("0.05"), RescaleFrequency.hourly),
                               ("inverted_gaussian", Decimal("0.10"), RescaleFrequency.minute15)]:
        tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
                        report_name=f"narrow_{shape}_{g.ratio_label(ratio)}_{freq}", indicator_length_hr=1,
                        to_swap=False, aggressive=True, compound=False, rescale_frequency=freq,
                        cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
                        initial_swap=True, flip_param_dates=[], start_with_bull_param=True, initial_type=1,
                        starting_mark_price=Decimal(20))
        _orig = actuator_module.Actuator.__init__

        def _named_init(self, *a, _name=tp.report_name, **k):
            _orig(self, *a, **k)
            self.golden_name = _name

        actuator_module.Actuator.__init__ = _named_init
        m = g.run_test(_copy.copy(params), _copy.copy(params), tp, gp, market.data, market.data, shape=shape,
                       ratio=ratio)
        actuator_module.Actuator.__init__ = _orig
        results.append((tp.report_name, m))
    with open(OUT / "gamma_narrow" / "metrics.json", "w") as f:
        json.dump({k: {mk: (str(mv) if mv is not None else None) for mk, mv in v.items()} for k, v in results}, f,
                  indent=1)


if __name__ == "__main__" and "gamma_narrow" in sys.argv[1:]:
    run_gamma_narrow()
