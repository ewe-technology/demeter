"""
H13 of reports/single_pool_loop.md (registered 2026-10-08, after H4b, H8 and H11): how deep and how large the
gate-off buy ladder of g_down has to be. 0x99ac, BTC gate EMA100, 16 windows, costs as pool_lp_batch.py.

  gd_120   off: [p/1.20, p 1.01] with all the value          (g_down uses p/1.40)
  gd_160   off: [p/1.60, p 1.01] with all the value
  gd_half  off: [p/1.40, p 1.01] with half the value, the other half in USDC; every off placement (the switch and
           each re-centre) first sells any WBTC, then places half of the book
  g_spot100  the control, rerun here so every number comes from the same code

Verdict, fixed before the run (commit of this file): each version is judged against g_spot100 by H2's 1-3
(median > 0, >= 75% of windows > 0, median > 0 in both halves). The gain of g_down is "not one depth" if gd_120 and
gd_160 both pass. gd_half is listed next to g_down: a ladder half the size that keeps about half the gain
(between a third and two thirds of g_down's median) points at the ladder itself.

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_gdown.py --set h13 --workers 3
  PYTHONPATH=../.. python pool_lp_gdown.py --test        # gd_half over 2022-05-01 .. 06-15 (gate off)
"""
import sys
from decimal import Decimal

import pool_lp_batch as batch
from pool_lp_windows import GatedPool
from single_pool_backtest import KEY


class HalfGated(GatedPool):
    """GatedPool whose gate-off range (off == "half") holds half the book; the rest stays in the quote."""

    def go(self, on: bool, price: Decimal, t):
        cfg = self.cfg
        if on or cfg.off != "half":
            return super().go(on, price, t)
        if self.bounds is not None:
            self.remove()
        self.state, self.mode = on, "range"  # "range" keeps the hourly re-centre of GatedPool.on_bar
        self.k = (1 + cfg.off_width, 1 + (cfg.off_up or cfg.off_width))
        self.place(price, 0.0, "off", t)

    def place(self, price: Decimal, width: float, kind: str, t):
        cfg = self.cfg
        if self.state is not False or cfg.off != "half":
            return super().place(price, width, kind, t)
        m = self.markets[KEY]
        btc = self.broker.get_token_balance(cfg.base)
        if btc > 0:
            m.swap(btc, cfg.base, cfg.quote)
        lo, hi = price / Decimal(self.k[0]), price * Decimal(self.k[1])
        t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), self.broker.get_token_balance(cfg.quote) / 2)
        self.bounds = (lo, hi)
        self.events.append((t, kind))


g = dict(gated=True, on="spot")
batch.SETS["h13"] = [batch.cfg("99ac", "gd_120", off="range", off_width=0.20, off_up=0.01, **g),
                     batch.cfg("99ac", "gd_160", off="range", off_width=0.60, off_up=0.01, **g),
                     batch.cfg("99ac", "gd_half", off="half", off_width=0.40, off_up=0.01, **g),
                     batch.cfg("99ac", "g_spot100", **g)]
batch.CONTROL.update({"gd_120": "g_spot100", "gd_160": "g_spot100", "gd_half": "g_spot100"})
batch.GatedPool = HalfGated  # pool_lp_batch.run builds the gated strategy from this name; the workers fork after

if __name__ == "__main__":
    if "--test" in sys.argv:
        from datetime import date
        import pandas as pd
        batch.os.makedirs(batch.RESULT_DIR, exist_ok=True)
        print(pd.Series(batch.run(batch.SETS["h13"][2], date(2022, 5, 1), date(2022, 6, 15))).to_string())
    else:
        batch.main()
