"""
gamma_maker_defense_ethusdc_v3.py in one window (2022-01-02 .. 2026-09-30), unchanged, with a log of every rescale:
the balance and LP distribution BEFORE the ladder is removed, the signal (F, F', divergence flag, the four virtual
accounts) it was judged on, and the book after the rebuild. The v3 file is not edited: its strategy class is
subclassed here and swapped in through the module, and the Pool workers are forked so they see the swap.

Output: <run folder>/rescales_<report>.jsonl, one JSON object per rescale (plus the initial build as kind "initial");
<run folder>/judgements_<report>.jsonl, the book and signal of every daily 00:00 judgement (acted on or not, so the
days demeter held are cases too); and the usual v3 result files next to them. Run from samples/strategy-example on the Rust-backed engine (rust/README.md):
    ../../rust/.venv/bin/python gamma_maker_defense_ethusdc_v3_rescale_log.py
"""
import json
import multiprocessing
from datetime import date, datetime
from decimal import Decimal

import gamma_maker_defense_ethusdc_v3 as v3

WINDOW = (datetime(2022, 1, 2, 0, 0, 0), date(2022, 1, 2), date(2026, 9, 30), "", [])


def _f(x) -> float | None:
    return None if x is None else float(x)


def _nan_none(x) -> float | None:
    return None if x is None or x != x else float(x)


class RescaleLogStrategy(v3.RemixDaoDcaWeekStratStrategy):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rescale_log: list[dict] = []
        self.judgement_log: list[dict] = []  # every daily 00:00 range check, acted on or not (the HOLD days)

    def book(self, lp_market, price: Decimal) -> dict:
        """Wallet, ladder bands and their split at `price` (the pool price the strategy acts on)."""
        bands, lp_eth, lp_usdc, pend_eth, pend_usdc = [], Decimal(0), Decimal(0), Decimal(0), Decimal(0)
        for pos in self.positions:
            if pos not in lp_market.positions:
                continue
            p = lp_market.positions[pos]
            eth, usdc = lp_market._convert_pair(*lp_market.get_position_amount(pos))
            fe, fu = lp_market._convert_pair(p.pending_amount0, p.pending_amount1)
            lo, hi = sorted((lp_market.tick_to_price(pos[0]), lp_market.tick_to_price(pos[1])))
            bands.append({"tickLower": pos[0], "tickUpper": pos[1], "priceLower": _f(lo), "priceUpper": _f(hi),
                          "liquidity": str(p.liquidity), "eth": _f(eth), "usdc": _f(usdc), "value": _f(eth * price + usdc)})
            lp_eth, lp_usdc, pend_eth, pend_usdc = lp_eth + eth, lp_usdc + usdc, pend_eth + fe, pend_usdc + fu
        bands.sort(key=lambda b: b["priceLower"])
        wallet_eth = self.broker.get_token_balance(self.gp.base_token)
        wallet_usdc = self.broker.get_token_balance(self.gp.quote_token)
        free_eth, free_usdc = wallet_eth - self.total_base_fee, wallet_usdc - self.held_quote_fee
        lp_value = lp_eth * price + lp_usdc
        equity = lp_value + free_eth * price + free_usdc
        return {
            "wallet": {"eth": _f(wallet_eth), "usdc": _f(wallet_usdc), "ethFeeHeld": _f(self.total_base_fee),
                       "usdcFeeHeld": _f(self.held_quote_fee)},
            "free": {"eth": _f(free_eth), "usdc": _f(free_usdc)},
            "lp": {"eth": _f(lp_eth), "usdc": _f(lp_usdc), "value": _f(lp_value),
                   "pendingEth": _f(pend_eth), "pendingUsdc": _f(pend_usdc), "pendingValue": _f(pend_eth * price + pend_usdc),
                   "range": {"lower": bands[0]["priceLower"], "upper": bands[-1]["priceUpper"]} if bands else None,
                   "bands": bands},
            "equity": _f(equity),
            "lpFraction": _f(lp_value / equity) if equity > 0 else None,
        }

    def signal(self, timestamp: datetime) -> dict:
        day, row = v3.daily_row_for(self.daily_ema, timestamp)
        return {"day": str(day.date()), "close": float(row["close"]), "ema100": float(row["ema"]), "d": float(row["d"]),
                "diverged": int(row["diverged"]), "F": float(row["F"]), "Fp": float(row["Fp"]),
                "accounts": {str(n): {"armed": int(row[f"armed{n}"]), "stage": int(row[f"stage{n}"]),
                                      "deployed": float(row[f"deployed{n}"]), "ema": float(row[f"ema{n}"]),
                                      "centre": _nan_none(row[f"centre{n}"]), "low": _nan_none(row[f"low{n}"])}
                             for n in v3.EMA_SPANS}}

    def decision(self, timestamp: datetime) -> dict:
        return {"target": _f(v3.target_fraction_for(self.daily_ema, timestamp)),
                "buildFraction": _f(self.deployed_at_build), "ethShare": _f(self.last_share),
                "reserveQuote": _f(self.reserve_quote)}

    def rescale_work(self, row_data):
        lp_market = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        tick = lp_market.price_to_raw_tick(price)
        kind = "follow" if self.force_rebuild else "range"
        brk = None
        if self.positions and self.positions[0][0] > tick:
            brk = "upper"
        elif self.positions and tick >= self.positions[-1][1]:
            brk = "lower"
        before = self.book(lp_market, price) if (self.positions or self.force_rebuild) else None
        if kind == "range" and self.starting_tick is not None and self.out_of_fund_date is None:
            # the daily trigger runs before follow_work at the same 00:00: this is the book the day is judged on
            book = before if before is not None else self.book(lp_market, price)
            s = self.signal(row_data.timestamp)
            self.judgement_log.append({
                "time": row_data.timestamp.strftime("%Y-%m-%d %H:%M"), "poolPrice": _f(price), "tick": tick,
                "signal": {k: s[k] for k in ("day", "close", "ema100", "d", "diverged", "F", "Fp")},
                "before": {"free": book["free"], "equity": book["equity"], "lpFraction": book["lpFraction"],
                           "lp": {k: book["lp"][k] for k in ("eth", "usdc", "value", "pendingValue", "range")}},
            })
        actions = len(self.export_actions)
        super().rescale_work(row_data)
        if len(self.export_actions) == actions:
            return  # no rescale this time (in range)
        ed = self.export_actions[-1]
        self.rescale_log.append({
            "kind": kind, "break": brk, "time": row_data.timestamp.strftime("%Y-%m-%d %H:%M"),
            "poolPrice": _f(price), "tick": tick, "signal": self.signal(row_data.timestamp),
            "before": before, "decision": self.decision(row_data.timestamp),
            "removed": {"eth": _f(ed.base_removed), "usdc": _f(ed.quote_removed),
                        "feeEth": _f(ed.base_fee), "feeUsdc": _f(ed.quote_fee)},
            "added": {"eth": _f(ed.base_added), "usdc": _f(ed.quote_added)},
            "after": self.book(lp_market, price),
        })

    def first_lp(self, row_data):
        super().first_lp(row_data)
        lp_market = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        self.rescale_log.append({
            "kind": "initial", "break": None, "time": row_data.timestamp.strftime("%Y-%m-%d %H:%M"),
            "poolPrice": _f(price), "tick": lp_market.price_to_raw_tick(price), "signal": self.signal(row_data.timestamp),
            "before": None, "decision": self.decision(row_data.timestamp), "after": self.book(lp_market, price),
        })

    def finalize(self):
        super().finalize()
        path = f"{self.params.folder}/rescales_{self.params.report_name}.jsonl"
        with open(path, "w") as out:
            for i, event in enumerate(self.rescale_log):
                out.write(json.dumps({"n": i, **event}) + "\n")
        print(f"rescale log: {len(self.rescale_log)} events -> {path}")
        path = f"{self.params.folder}/judgements_{self.params.report_name}.jsonl"
        with open(path, "w") as out:
            for event in self.judgement_log:
                out.write(json.dumps(event) + "\n")
        print(f"judgement log: {len(self.judgement_log)} days -> {path}")


if __name__ == "__main__":
    multiprocessing.set_start_method("fork")  # the Pool workers must inherit the class swap below
    v3.RemixDaoDcaWeekStratStrategy = RescaleLogStrategy
    v3.process_for_date(*WINDOW)
