"""
gamma_ig_gap_bands_defense_btceth_v2.py over one window, unchanged, with a log of every daily 00:00 judgement: the
signal it was judged on (G, R, EMA100(R), strong, F), the book before (wallet, LP position and its split, the shares
the follow rule compares), what it did, and the book after a rebuild. The v2 file is not edited: its strategy class is
subclassed here and swapped in through the module, and the run is done in this process (no Pool).

Pool: Ethereum mainnet WBTC/WETH 0.05% (token0 = WBTC), the pool v2 keeps commented out and the spec sheet calibrated
fees on; Base WETH/cbBTC has no data before 2024-09-13. Signal warm-up from pool_data.data_floor (2021-05-13), as v2.

Output in result/btceth-v2-daylog-<start>-<end>/:
  daylog.jsonl       one object per 00:00 judgement (plus kind "start" for the first build)
  signal_frame.csv   v2's signal_frame (judged day, G, R, R_ema, strong, F), floats written round-trip exact
Run from samples/strategy-example on the Rust-backed engine (rust/README.md):
    ../../rust/.venv/bin/python gamma_ig_gap_bands_defense_btceth_v2_daylog.py
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

import demeter
from demeter import ChainType, MarketInfo, TokenInfo
from demeter.uniswap import UniV3Pool

import gamma_ig_gap_bands_defense_btceth_v2 as v2
from market_v2 import UniLpMarketV2
from math_const import ZERO
from pool_data import data_floor
from remix_dao_utils import RemixDAOParams
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy

WINDOW = (datetime(2022, 1, 1), date(2022, 1, 1), date(2022, 12, 31))   # spec sheet 5.1: Jan 1, 365 days


def _f(x) -> float | None:
    return None if x is None else float(x)


class DayLogStrategy(v2.EthBtcDefenseStrategy):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_log: list[dict] = []
        self._seen_wallet = self._seen_lp = None

    # v2's daily_work reads the book right after collecting fees through these two; keep what it saw first (a rebuild
    # reads the wallet again after removing the LP and after swapping)
    def _wallet(self):
        w = super()._wallet()
        if self._seen_wallet is None:
            self._seen_wallet = w
        return w

    def _lp_value(self):
        v = super()._lp_value()
        if self._seen_lp is None:
            self._seen_lp = v
        return v

    def book(self, p: Decimal, u: Decimal) -> dict:
        lp_market = self._lp_market()
        pos = None
        if self.positions and self.positions[0] in lp_market.positions:
            key = self.positions[0]
            btc, eth = lp_market._convert_pair(*lp_market.get_position_amount(key))
            pos = {"tickLower": key[0], "tickUpper": key[1], "liquidity": str(lp_market.positions[key].liquidity),
                   "btc": _f(btc), "eth": _f(eth), "value": _f(btc * p + eth)}
        btc, eth, usdc = super()._wallet()
        return {"free": {"btc": _f(btc), "eth": _f(eth), "usdc": _f(usdc)}, "lp": pos,
                "feeHeld": {"btc": _f(self.total_base_fee), "eth": _f(self.total_quote_fee)}}

    def signal_row(self, timestamp: datetime) -> dict:
        day = pd.Timestamp(timestamp - timedelta(days=1)).normalize()
        row = self.daily.loc[day]
        return {"date": f"{day:%Y-%m-%d}", "G": float(row["G"]), "R": float(row["R"]), "R_ema": float(row["R_ema"]),
                "strong": bool(row["strong"]), "F": float(row["F"])}

    def first_lp(self, row_data):
        super().first_lp(row_data)
        p, u = self._prices(row_data)
        r = self.rebuild_log[-1]
        self.day_log.append({"kind": "start", "ts": f"{row_data.timestamp:%Y-%m-%d %H:%M}", "p": _f(p), "u": _f(u),
                             "tick": self._lp_market().price_to_raw_tick(p), "signal": self.signal_row(row_data.timestamp),
                             "rebuild": {"newRange": r["new_range"], "swapCostEth": r["swap_cost_eth"]},
                             "after": self.book(p, u)})

    def daily_work(self, row_data):
        if self.starting_tick is None or self.out_of_fund_date is not None:
            return super().daily_work(row_data)
        p, u = self._prices(row_data)
        lp_market = self._lp_market()
        before_range = (self.positions[0][0], self.positions[0][1]) if self.positions else None
        n_daily, n_rebuild = len(self.daily_log), len(self.rebuild_log)
        self._seen_wallet = self._seen_lp = None
        super().daily_work(row_data)
        if len(self.daily_log) == n_daily:   # skipped (no close)
            self.day_log.append({"kind": "skip", "ts": f"{row_data.timestamp:%Y-%m-%d %H:%M}"})
            return
        d = self.daily_log[-1]
        btc, eth, usdc = self._seen_wallet
        entry = {
            "kind": "judge", "ts": f"{row_data.timestamp:%Y-%m-%d %H:%M}", "p": _f(p), "u": _f(u),
            "tick": lp_market.price_to_raw_tick(p), "signal": self.signal_row(row_data.timestamp),
            "before": {"free": {"btc": _f(btc), "eth": _f(eth), "usdc": _f(usdc)}, "lpValue": _f(self._seen_lp),
                       "range": before_range},
            "cur": {k: d[f"cur_{k}"] for k in ("lp", "eth", "btc", "usdc")}, "equity": d["equity_eth"],
            "why": d["rebuild"],
        }
        if len(self.rebuild_log) > n_rebuild:
            r = self.rebuild_log[-1]
            entry["rebuild"] = {"newRange": r["new_range"], "swapCostEth": r["swap_cost_eth"]}
            entry["after"] = self.book(p, u)
        self.day_log.append(entry)

    def finalize(self):
        super().finalize()
        with open(f"{self.params.folder}/daylog.jsonl", "w") as fh:
            for e in self.day_log:
                fh.write(json.dumps(e, default=str) + "\n")
        print(f"daylog: {len(self.day_log)} entries -> {self.params.folder}/daylog.jsonl")


def run(csd: datetime, dsd: date, ded: date):
    """v2.process_for_date with the mainnet WBTC/WETH pool, one signal-mode run in this process."""
    demeter.Formats.global_num_format = ".4g"
    eth, btc = TokenInfo(name="eth", decimal=18), TokenInfo(name="btc", decimal=8)
    base_token, quote_token, init_quote = btc, eth, Decimal(1)
    token0, token1 = btc, eth
    contract_address, fee, chain_name = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, ChainType.ethereum.name
    contract_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    tick_spacing = int(fee * 200)
    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init_quote, quote_token=quote_token,
                      base_token=base_token, chain_name=chain_name, contract_address=contract_address,
                      swap_fee=False, init_quote_usdc=ZERO)
    bull = RemixDAOParams(tick_spread_upper=60, tick_spread_lower=60, tick_upper_boundary_offset=0,
                          tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                          rescale_tick_lower_boundary_offset=0, init_tick_spread=120, tick_spacing=tick_spacing,
                          tick_gap_lower=1, tick_gap_upper=1)
    folder = f"result/btceth-v2-daylog-{dsd:%Y%m%d}-{ded:%Y%m%d}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    def load(pool, address, start, end, chain):
        m = UniLpMarketV2(MarketInfo("data"), pool)
        m.data_path = f"../real-data/{address}"
        m.load_data(chain, address, start, end)
        return m

    market = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, dsd, ded, chain_name)
    usdc_market = load(UniV3Pool(v2.USDC, eth, fee, v2.USDC), contract_usdc, dsd, ded, ChainType.ethereum.name)
    floor = data_floor(contract_address, contract_usdc)
    warm_start, warm_end = max(dsd - timedelta(days=v2.EMA_WARMUP_DAYS), floor), dsd - timedelta(days=1)
    print(f"signal warm-up {warm_start} ~ {warm_end}: {(warm_end - warm_start).days + 1} days")
    warm = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, warm_start, warm_end, chain_name)
    warm_usdc = load(UniV3Pool(v2.USDC, eth, fee, v2.USDC), contract_usdc, warm_start, warm_end, ChainType.ethereum.name)
    daily = v2.signal_frame(pd.concat([warm.data.price, market.data.price]),
                            pd.concat([warm_usdc.data.price, usdc_market.data.price]))
    daily.to_csv(f"{folder}/signal_frame.csv", index_label="date")

    tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
                    report_name=f"{init_quote}{quote_token.name}_{v2.MODE_SIGNAL}", cal_start_datetime=csd,
                    data_start_date=dsd, data_end_date=ded, folder=folder, rescale_frequency=RescaleFrequency.daily)
    v2.EthBtcDefenseStrategy = DayLogStrategy   # run_test builds the module's class
    metrics = v2.run_test(bull, tp, gp, market.data, usdc_market.data, daily, v2.MODE_SIGNAL)
    print({k: float(metrics[k]) for k in v2.EXTRA_COLUMNS})


if __name__ == "__main__":
    v2._self_check()
    if len(sys.argv) == 3:   # optional: <start YYYY-MM-DD> <end YYYY-MM-DD>
        s, e = (date.fromisoformat(a) for a in sys.argv[1:])
        run(datetime(s.year, s.month, s.day), s, e)
    else:
        run(*WINDOW)
