"""
Daily decision log for gamma_maker_defense_ethusdc_v1.py, as a fixture for the Node port (ewe-amm-strategy).

Logging only. The decision logic is v1's own code, imported unchanged: DayLogStrategy subclasses v1's strategy and
only wraps first_lp / rescale_work / follow_work to read state before and after each call. run_test picks the class
up from v1's module globals, so the subclass is swapped in there, and the pool workers are forked so they inherit it.

Runs the accepted 2022 single year (same settings as v1's defaults: ig17s-price, +-20% price bands, EMA_SHARE 70/50,
DEPLOY_SIGNAL, Binance signal, swap 0.1%, no slippage, daily judgement, start 2022-01-02 00:00) and writes one row per
decision minute to v1_daylog_2022.csv.

Run from samples/strategy-example:  ../../rust/.venv/bin/python gamma_maker_defense_ethusdc_v1_daylog.py
Note: process_for_date also rewrites the accepted run's result folder ...-20220102-20221231 (same numbers).
"""
import multiprocessing
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict

import pandas as pd

import gamma_maker_defense_ethusdc_v1 as v1
from math_const import ZERO

OUT_CSV = Path(__file__).with_name("v1_daylog_2022.csv")
LOG_YEAR = 2022


def account_states(close: pd.Series) -> pd.DataFrame:
    """Per day, every virtual account's state after stepping that day's close: the same loop as v1.daily_ema_frame,
    which keeps only F. Columns <field>_<span>, plus F recomputed (checked against the frame v1 used)."""
    emas = {n: close.ewm(span=n, adjust=False).mean() for n in v1.EMA_SPANS}
    accounts = [v1.VirtualAccount(n) for n in v1.EMA_SPANS]
    rows = []
    for day, c in close.items():
        row = {}
        for a in accounts:
            a.step(float(c), float(emas[a.span][day]))
            for field in ("armed", "deployed", "stage", "centre", "low", "confirm"):
                row[f"{field}_{a.span}"] = getattr(a, field)
        row["F_recomputed"] = sum(a.deployed for a in accounts) / len(accounts)
        rows.append(row)
    return pd.DataFrame(rows, index=close.index)


class DayLogStrategy(v1.RemixDaoDcaWeekStratStrategy):
    """v1's strategy plus a decision log. Nothing here changes a balance, a position or a decision."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_rows: Dict[datetime, dict] = {}
        self.centre_tick: int | None = None      # centre tick of the current ladder (rounded rebuild tick)
        self.centre_pool_price: Decimal | None = None   # pool price at the minute the current ladder was built
        self.accounts = None
        if self.daily_ema is not None:
            self.accounts = account_states(self.daily_ema["close"])
            diff = (self.accounts["F_recomputed"] - self.daily_ema["F"]).abs().max()
            assert diff == 0, f"recomputed F differs from v1's daily frame by {diff}"

    # ---- helpers -----------------------------------------------------------------------------------------
    def _market(self):
        return self.broker.markets[self.utils.market_key]

    def _row(self, row_data) -> dict:
        ts = row_data.timestamp
        if ts not in self.day_rows:
            self.day_rows[ts] = {"ts": ts.strftime("%Y-%m-%d %H:%M"), "action": "none", "reason": ""}
        return self.day_rows[ts]

    def _signal_fields(self, row: dict, ts: datetime) -> None:
        if self.daily_ema is None or "kline_date" in row:
            return
        day, d = v1.daily_row_for(self.daily_ema, ts)
        row.update({"kline_date": day.strftime("%Y-%m-%d"), "close": float(d["close"]), "ema100": float(d["ema"]),
                    "F": float(d["F"]),
                    "share_rule": float(v1.SHARE_ABOVE_EMA if d["close"] > d["ema"] else v1.SHARE_BELOW_EMA)})
        for col, val in self.accounts.loc[day].items():
            if col != "F_recomputed":
                row[col] = val

    def _range_fields(self, row: dict, prefix: str) -> None:
        """Ladder edges as ticks and as ETH prices. token0 = USDC here, so the LOWER tick is the HIGHER ETH price."""
        lp_market = self._market()
        if self.positions:
            lo_tick, hi_tick = self.positions[0][0], self.positions[-1][1]
            p_lo, p_hi = lp_market.tick_to_price(lo_tick), lp_market.tick_to_price(hi_tick)
            row.update({f"{prefix}range_tick_lo": lo_tick, f"{prefix}range_tick_hi": hi_tick,
                        f"{prefix}range_lower_price": float(min(p_lo, p_hi)),
                        f"{prefix}range_upper_price": float(max(p_lo, p_hi)),
                        f"{prefix}band_count": len(self.positions)})
        else:
            row.update({f"{prefix}range_tick_lo": None, f"{prefix}range_tick_hi": None,
                        f"{prefix}range_lower_price": None, f"{prefix}range_upper_price": None,
                        f"{prefix}band_count": 0})
        row[f"{prefix}centre_tick"] = self.centre_tick
        row[f"{prefix}centre_tick_price"] = (float(lp_market.tick_to_price(self.centre_tick))
                                             if self.centre_tick is not None else None)
        row[f"{prefix}centre_pool_price"] = float(self.centre_pool_price) if self.centre_pool_price is not None else None

    def _book_fields(self, row: dict, prefix: str, row_data) -> None:
        """lp_value / free balances / equity / current, computed exactly as v1's follow_work does."""
        lp_market = self._market()
        price = row_data.prices[self.gp.base_token.name]
        lp_value = lp_market.get_market_balance().net_value if len(lp_market.positions) > 0 else ZERO
        free_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.total_base_fee
        free_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee
        equity = lp_value + free_base * price + free_quote
        row.update({f"{prefix}lp_value": float(lp_value), f"{prefix}free_base": float(free_base),
                    f"{prefix}free_quote": float(free_quote), f"{prefix}total_base_fee": float(self.total_base_fee),
                    f"{prefix}total_quote_fee": float(self.total_quote_fee), f"{prefix}equity": float(equity),
                    f"{prefix}current": float(lp_value / equity) if equity > ZERO else None})

    def _after_build(self, row: dict, row_data, centre_raw_tick: int) -> None:
        """State right after a (re)build: the new ladder, F / share used, value and token amounts placed."""
        lp_market = self._market()
        self.centre_tick = self.utils.round_tick(centre_raw_tick, self.utils.params.tick_spacing)  # calculate_range's
        self.centre_pool_price = row_data.prices[self.gp.base_token.name]
        bal = lp_market.get_market_balance() if lp_market.positions else None
        row.update({"after_F_used": float(self.deployed_at_build),
                    "after_share_used": float(self.last_share) if self.last_share is not None else None,
                    "after_reserve_quote": float(self.reserve_quote),
                    "after_ladder_value": float(bal.net_value) if bal else 0.0,
                    "after_eth_in_ladder": float(bal.base_in_position) if bal else 0.0,
                    "after_usdc_in_ladder": float(bal.quote_in_position) if bal else 0.0})
        self._range_fields(row, "after_")
        self._book_fields(row, "after_", row_data)

    # ---- wrapped decision points -------------------------------------------------------------------------
    def first_lp(self, row_data):
        row = self._row(row_data)
        row["pool_price"] = float(row_data.prices[self.gp.base_token.name])
        self._signal_fields(row, row_data.timestamp)
        self._range_fields(row, "before_")
        super().first_lp(row_data)   # deposits init_quote first, so there is no meaningful "before" book
        row["action"], row["reason"] = "first_lp", "initial build at cal_start_datetime"
        self._after_build(row, row_data, self.starting_tick)

    def rescale_work(self, row_data):
        if self.force_rebuild:   # called from follow_work: that wrapper logs it
            return super().rescale_work(row_data)
        row = self._row(row_data)
        lp_market = self._market()
        price = row_data.prices[self.gp.base_token.name]
        row.setdefault("pool_price", float(price))
        self._signal_fields(row, row_data.timestamp)
        if "before_range_tick_lo" not in row:
            self._range_fields(row, "before_")
            self._book_fields(row, "before_", row_data)   # the book before this minute's decisions
        tick = lp_market.price_to_raw_tick(price)
        row["pool_tick"] = tick
        # same condition as check_rebalance, evaluated here without its print; n/a when no bands (rescale_work skips)
        if len(lp_market.positions) == 0 or self.out_of_fund_date is not None or not self.positions:
            row["out_of_range"] = None
        else:
            row["out_of_range"] = not (self.positions[0][0] <= tick < self.positions[-1][1])
        builds = len(self.export_actions)
        lo_tick = self.positions[0][0] if self.positions else None
        super().rescale_work(row_data)
        if len(self.export_actions) > builds:
            row["action"] = "range_rescale"
            row["reason"] = "ETH price above the ladder" if lo_tick is not None and tick < lo_tick else "ETH price below the ladder"
            self._after_build(row, row_data, self.last_rescale_tick)

    def follow_work(self, row_data):
        row = self._row(row_data)
        self._signal_fields(row, row_data.timestamp)
        row.setdefault("pool_price", float(row_data.prices[self.gp.base_token.name]))
        if "before_range_tick_lo" not in row:
            self._range_fields(row, "before_")
            self._book_fields(row, "before_", row_data)
        # the inputs follow_work is about to use; after a same-minute range rescale this is the rebuilt book
        self._book_fields(row, "", row_data)
        follows = self.follow_rebuild_count
        super().follow_work(row_data)
        if self.follow_rebuild_count > follows:
            target, cur = Decimal(str(row["F"])), Decimal(str(row["current"]))
            if abs(target - cur) >= v1.FOLLOW_THRESHOLD:
                why = f"|F - current| >= {v1.FOLLOW_THRESHOLD}"
            elif target == ZERO:
                why = f"F = 0 and current > {v1.FULL_TOLERANCE}"
            else:
                why = f"F >= {1 - v1.FULL_TOLERANCE} and current < {1 - v1.FULL_TOLERANCE}"
            row["action"] = "follow_rebuild" if row["action"] == "none" else f"{row['action']}+follow_rebuild"
            row["reason"] = why + (" (F used 0: no bands, all USDC)" if self.deployed_at_build == ZERO else "")
            self._after_build(row, row_data, self.last_rescale_tick)

    def finalize(self):
        super().finalize()
        df = pd.DataFrame([r for r in self.day_rows.values() if r["ts"].startswith(str(LOG_YEAR))])
        lead = ["ts", "kline_date", "close", "ema100", "share_rule", "F"]
        accounts = [f"{f}_{n}" for n in v1.EMA_SPANS for f in ("armed", "deployed", "stage", "centre", "low", "confirm")]
        book = ["pool_price", "pool_tick", "lp_value", "free_base", "free_quote", "total_base_fee", "total_quote_fee",
                "equity", "current"]
        before = [c for c in df.columns if c.startswith("before_")]
        mid = ["out_of_range", "action", "reason"]
        after = [c for c in df.columns if c.startswith("after_")]
        cols = [c for c in lead + accounts + book + before + mid + after if c in df.columns]
        df[cols].to_csv(OUT_CSV, index=False)
        print(f"day log: {len(df)} rows -> {OUT_CSV}")


if __name__ == "__main__":
    multiprocessing.set_start_method("fork")    # workers inherit the swapped-in class below
    v1._self_check()
    v1.RemixDaoDcaWeekStratStrategy = DayLogStrategy
    v1.process_for_date(datetime(2022, 1, 2, 0, 0, 0), date(2022, 1, 2), date(2022, 12, 31), "", [])
