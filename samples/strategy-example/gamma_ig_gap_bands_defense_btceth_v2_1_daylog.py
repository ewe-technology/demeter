"""
gamma_ig_gap_bands_defense_btceth_v2_1.py over one window, unchanged, with a log of every daily 00:00 judgement: the
signal it was judged on (G, R, EMA100(R), strong, F), the book before (principal wallet, LP value and range, the shares
the rebuild rules compare), the claim (spec section 5), what it did, the book after a rebuild, and in compound mode the
monthly reinvestment. The v2.1 file is not edited: its strategy class is subclassed here and swapped in through the
module, and the run is done in this process (no Pool).

Pool: Ethereum mainnet WBTC/WETH 0.05% (token0 = WBTC) by default, as the v2 day log and the spec's fee calibration;
"base" = Base WETH/cbBTC (data from 2024-09-13). The signal is v2.1's Binance frame from 2017-08-17 either way.

Output in result/btceth-v2_1-daylog-<pool>-<mode>-<start>-<end>/:
  daylog.jsonl       one object per 00:00 judgement (plus kind "start" for the first build)
  signal_frame.csv   v2.1's signal frame (judged day D, G, R, R_ema, strong, F, per-account state), round-trip exact floats
  daily_*.csv / rebuilds_*.csv   v2.1's own logs
Run from samples/strategy-example on the Rust-backed engine (rust/README.md):
    ../../rust/.venv/bin/python gamma_ig_gap_bands_defense_btceth_v2_1_daylog.py [start end [standard|compound [mainnet|base]]]
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

import gamma_ig_gap_bands_defense_btceth_v2_1 as v21
from market_v2 import UniLpMarketV2
from math_const import ZERO
from remix_dao_utils import RemixDAOParams
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy

WINDOW = (datetime(2022, 1, 2), date(2022, 1, 2), date(2022, 12, 31))   # 1/1 join priced at the 1/1 close, like v2.1


def _f(x) -> float | None:
    return None if x is None else float(x)


class DayLogStrategy(v21.EthBtcMglStrategy):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_log: list[dict] = []
        self._seen_book = None
        self._claims: list[dict] = []
        self._reinvest: dict | None = None

    # v2.1's daily_work reads the principal through _book right after the daily claim; keep what it saw first (a rebuild
    # and a reinvestment read it again)
    def _book(self, p, u):
        b = super()._book(p, u)
        if self._seen_book is None:
            self._seen_book = b
        return b

    def claim(self, p, u, force=False):
        before = (self.reward_btc, self.gross_reward_eth, self.perf_fee_eth, self.reward_swap_cost_eth)
        done = super().claim(p, u, force)
        if done:
            self._claims.append({"force": force, "grossEth": _f(self.gross_reward_eth - before[1]),
                                 "perfFeeEth": _f(self.perf_fee_eth - before[2]),
                                 "swapCostEth": _f(self.reward_swap_cost_eth - before[3]),
                                 "netBtc": _f(self.reward_btc - before[0])})
        return done

    def reinvest(self, row_data, cur):
        pending = self.reward_btc
        super().reinvest(row_data, cur)
        p, _ = self._prices(row_data)
        self._reinvest = {"btc": _f(pending), "eth": _f(pending * p), "shares": {k: _f(v) for k, v in cur.items()}}

    def book(self, p: Decimal, u: Decimal) -> dict:
        lp_market = self._lp_market()
        pos = None
        if self.positions and self.positions[0] in lp_market.positions:
            key = self.positions[0]
            btc, eth = lp_market._convert_pair(*lp_market.get_position_amount(key))
            pos = {"tickLower": key[0], "tickUpper": key[1], "liquidity": str(lp_market.positions[key].liquidity),
                   "btc": _f(btc), "eth": _f(eth), "value": _f(btc * p + eth)}
        btc, eth, usdc = self._wallet()
        return {"free": {"btc": _f(btc), "eth": _f(eth), "usdc": _f(usdc)}, "lp": pos,
                "rewardBtc": _f(self.reward_btc)}

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
                             "rebuild": {"newRange": r["new_range"], "centreTick": r["centre_tick"],
                                         "swapCostEth": r["swap_cost_eth"]},
                             "after": self.book(p, u)})

    def daily_work(self, row_data):
        if self.starting_tick is None or self.out_of_fund_date is not None:
            return super().daily_work(row_data)
        p, u = self._prices(row_data)
        lp_market = self._lp_market()
        before_range = (self.positions[0][0], self.positions[0][1]) if self.positions else None
        before_reward = self.reward_btc
        n_daily, n_rebuild = len(self.daily_log), len(self.rebuild_log)
        self._seen_book, self._claims, self._reinvest = None, [], None
        super().daily_work(row_data)
        if len(self.daily_log) == n_daily:   # skipped (no close)
            self.day_log.append({"kind": "skip", "ts": f"{row_data.timestamp:%Y-%m-%d %H:%M}"})
            return
        d = self.daily_log[-1]
        value, _ = self._seen_book
        entry = {
            "kind": "judge", "ts": f"{row_data.timestamp:%Y-%m-%d %H:%M}", "p": _f(p), "u": _f(u),
            "tick": lp_market.price_to_raw_tick(p), "signal": self.signal_row(row_data.timestamp),
            "before": {"range": before_range, "rewardBtc": _f(before_reward)},
            "claims": self._claims,   # the daily one (force false) and, with a rebuild, the forced one
            "cur": {k: d[f"cur_{k}"] for k in ("lp", "eth", "btc", "usdc")}, "principal": _f(value),
            "why": d["rebuild"],
        }
        if len(self.rebuild_log) > n_rebuild:
            r = self.rebuild_log[-1]
            entry["rebuild"] = {"newRange": r["new_range"], "centreTick": r["centre_tick"],
                                "swapCostEth": r["swap_cost_eth"]}
        if self._reinvest:
            entry["reinvest"] = self._reinvest
        if "rebuild" in entry or self._reinvest:
            entry["after"] = self.book(p, u)
        self.day_log.append(entry)

    def finalize(self):
        super().finalize()
        with open(f"{self.params.folder}/daylog.jsonl", "w") as fh:
            for e in self.day_log:
                fh.write(json.dumps(e, default=str) + "\n")
        print(f"daylog: {len(self.day_log)} entries -> {self.params.folder}/daylog.jsonl")


def run(csd: datetime, dsd: date, ded: date, mode: str = v21.MODE_STANDARD, pool: str = "mainnet"):
    """v2.1's process_for_date for one mode and pool, run in this process."""
    demeter.Formats.global_num_format = ".4g"
    eth, btc = TokenInfo(name="eth", decimal=18), TokenInfo(name="btc", decimal=8)
    base_token, quote_token, init_quote = btc, eth, Decimal(1)
    btc_token0, contract_address, chain_name = v21.POOLS[pool]
    token0, token1 = (btc, eth) if btc_token0 else (eth, btc)
    fee = 0.05
    contract_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    tick_spacing = int(fee * 200)
    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init_quote, quote_token=quote_token,
                      base_token=base_token, chain_name=chain_name, contract_address=contract_address,
                      swap_fee=False, init_quote_usdc=ZERO)
    bull = RemixDAOParams(tick_spread_upper=60, tick_spread_lower=60, tick_upper_boundary_offset=0,
                          tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                          rescale_tick_lower_boundary_offset=0, init_tick_spread=120, tick_spacing=tick_spacing,
                          tick_gap_lower=1, tick_gap_upper=1)
    folder = f"result/btceth-v2_1-daylog-{pool}-{mode}-{dsd:%Y%m%d}-{ded:%Y%m%d}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    def load(pool_info, address, start, end, chain):
        m = UniLpMarketV2(MarketInfo("data"), pool_info)
        m.data_path = f"../real-data/{address}"
        m.load_data(chain, address, start, end)
        return m

    market = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, dsd, ded, chain_name)
    usdc_market = load(UniV3Pool(v21.USDC, eth, fee, v21.USDC), contract_usdc, dsd, ded, ChainType.ethereum.name)
    daily = v21.binance_signal_frame(ded)
    daily.to_csv(f"{folder}/signal_frame.csv", index_label="date", float_format="%.17g")

    tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
                    report_name=f"{init_quote}{quote_token.name}_{mode}", cal_start_datetime=csd,
                    data_start_date=dsd, data_end_date=ded, folder=folder, rescale_frequency=RescaleFrequency.daily)
    v21.EthBtcMglStrategy = DayLogStrategy   # run_test builds the module's class
    metrics = v21.run_test(bull, tp, gp, market.data, usdc_market.data, daily, mode)
    print({k: float(metrics[k]) for k in v21.EXTRA_COLUMNS})


if __name__ == "__main__":
    v21._self_check()
    if len(sys.argv) >= 3:   # optional: <start YYYY-MM-DD> <end YYYY-MM-DD> [standard|compound] [mainnet|base]
        s, e = (date.fromisoformat(a) for a in sys.argv[1:3])
        run(datetime(s.year, s.month, s.day), s, e, *sys.argv[3:5])
    else:
        run(*WINDOW)
