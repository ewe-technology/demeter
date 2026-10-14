"""
H43 and H44 of reports/plan_2026-10-14_out_of_sample.md (registered in 72f83dd, before this code ran): spot books on
Binance daily closes, 2018-01-01 .. 2021-12-31, before the data every other test used.

  H43  c_spot     BTC EMA100 gate on: BTC and ETH 50/50 (back to 50/50 at each switch on), off: USDC
       hold_5050  BTC and ETH 50/50 bought at the start, never touched (the control)
  H44  fp_spot    H38's spot rules on v3's F' (fprime_spot.FPRules), ETH only
       btc_gate   BTC EMA100 gate on: all ETH, off: USDC
       eth_gate   ETH EMA100 gate, listed

The book is valued at each daily close; the decision for day d uses the close of d-1 and trades at that close.
Costs as version C's spot (cost_matrix.py): 10 bps of the BTC traded, 11 bps of the ETH traded, paid from the book
at the trade; no gas, no interest on USDC.

Run from samples/strategy-example (no pool data, no Demeter):
  PYTHONPATH=../.. python oos_daily.py --test    # 2022 .. 2025 on the same code, to set against H40's hourly books
  PYTHONPATH=../.. python oos_daily.py
"""
import argparse
import os
from datetime import date

import numpy as np
import pandas as pd

import fprime_spot as fs

v3 = fs.v3
RESULT_DIR = "result/oos-daily"
START, END = date(2018, 1, 1), date(2021, 12, 31)
WINDOW_STARTS = [date(y, m, 1) for y in (2018, 2019, 2020) for m in (1, 4, 7, 10)] + [date(2021, 1, 1)]
BPS = {"btc": 0.0010, "eth": 0.0011}
_CLOSES = {}


def closes() -> pd.DataFrame:
    if not _CLOSES:
        out = {}
        for coin in ("btc", "eth"):
            c = pd.read_csv(f"binance_{coin}usdt_1d.csv", parse_dates=["date"]).set_index("date")["close"]
            out[coin] = c.astype(float)
        _CLOSES["x"] = pd.DataFrame(out).dropna()
    return _CLOSES["x"]


def gate(close: pd.Series) -> pd.Series:
    """The state decided at the close of d (above its EMA100), held over the next day: pool_lp_batch.gate's rule,
    indexed by the decision day instead of the day it applies to."""
    return close > close.ewm(span=100, adjust=False).mean()


class GateMix:
    """On: the given weights (set at each switch on), off: all USDC."""

    def __init__(self, on: pd.Series, weights: dict):
        self.on, self.weights, self.state = on, weights, None

    def decide(self, d, px, hold, cash):
        on = bool(self.on.loc[d])
        if on == self.state:
            return None
        self.state = on
        return dict(self.weights) if on else {k: 0.0 for k in self.weights}


class FPDaily:
    """fprime_spot.FPRules on daily closes; returns the day's orders as (kind, ETH share), done in order."""

    def __init__(self, daily: pd.DataFrame):
        self.rules = fs.FPRules(daily)
        self.started = False

    def decide(self, d, px, hold, cash):
        ts = pd.Timestamp(d) + pd.Timedelta(days=1)  # the close of d is known at d+1 00:00
        if not self.started:
            self.started = True
            return self.rules.first(ts)
        return self.rules.decide(ts, px["eth"], hold.get("eth", 0.0), cash) or None


def book(rules, start: date, end: date, coins=("btc", "eth"), initial: float = 100_000) -> tuple[pd.Series, int, float]:
    px_all = closes()
    days = px_all.loc[pd.Timestamp(start) - pd.Timedelta(days=1):pd.Timestamp(end)].index
    hold = {c: 0.0 for c in coins}
    cash, trades, paid = float(initial), 0, 0.0
    values = []

    def trade_to(px, weights):
        nonlocal cash, trades, paid
        value = cash + sum(hold[c] * px[c] for c in coins)
        for c, w in weights.items():
            delta = w * value - hold[c] * px[c]
            if abs(delta) < 1e-6:
                continue
            fee = abs(delta) * BPS[c]
            hold[c] += delta / px[c]
            cash -= delta + fee
            trades += 1
            paid += fee

    for d in days:
        px = px_all.loc[d]
        order = rules.decide(d, px, hold, cash)
        if isinstance(order, dict):
            trade_to(px, order)
        elif order:
            for kind, share in order:
                trade_to(px, {"eth": share})
                rules.rules.executed(kind, share, px["eth"])
        values.append(cash + sum(hold[c] * px[c] for c in coins))
    return pd.Series(values, index=days), trades, paid / initial


def hold_book(weights: dict, start: date, end: date, initial: float = 100_000) -> pd.Series:
    px = closes().loc[pd.Timestamp(start) - pd.Timedelta(days=1):pd.Timestamp(end)]
    units = {c: w * initial * (1 - BPS[c]) / px[c].iloc[0] for c, w in weights.items()}
    return sum(units[c] * px[c] for c in units)


def stats(v: pd.Series) -> dict:
    x = v / v.iloc[0]
    out = {"total": x.iloc[-1] - 1, "maxDD": float((x / x.cummax() - 1).min())}
    for y in sorted(set(x.index.year)):
        part, prev = x.loc[:f"{y}-12-31"], x.loc[:f"{y - 1}-12-31"]
        if part.index[-1].year == y and len(prev):
            out[str(y)] = part.iloc[-1] / prev.iloc[-1] - 1
    return out


def versions(start: date, end: date, fp_daily: pd.DataFrame) -> dict:
    c = closes()
    bg, eg = gate(c["btc"]), gate(c["eth"])
    out = {"c_spot": book(GateMix(bg, {"btc": 0.5, "eth": 0.5}), start, end),
           "hold_5050": (hold_book({"btc": 0.5, "eth": 0.5}, start, end), 2, 0.00105),
           "hold_btc": (hold_book({"btc": 1.0}, start, end), 1, 0.0010),
           "hold_eth": (hold_book({"eth": 1.0}, start, end), 1, 0.0011),
           "fp_spot": book(FPDaily(fp_daily), start, end, coins=("eth",)),
           "btc_gate": book(GateMix(bg, {"eth": 1.0}), start, end, coins=("eth",)),
           "eth_gate": book(GateMix(eg, {"eth": 1.0}), start, end, coins=("eth",))}
    return out


def run(start: date = START, end: date = END, windows=WINDOW_STARTS, tag: str = ""):
    os.makedirs(RESULT_DIR, exist_ok=True)
    fp_daily = v3.binance_daily_frame(start, end)
    first = fp_daily.loc[pd.Timestamp(start) - pd.Timedelta(days=1)]
    print(f"F' at the start ({(pd.Timestamp(start) - pd.Timedelta(days=1)).date()}): F {first['F']:.4f}, "
          f"F' {first['Fp']:.4f}, diverged {int(first['diverged'])}")
    fp_daily.loc[:pd.Timestamp("2018-03-31")].to_csv(f"{RESULT_DIR}/fp_warmup{tag}.csv")
    cont = versions(start, end, fp_daily)
    t = pd.DataFrame([{"book": k, "trades": n, "cost": cost, **stats(v)} for k, (v, n, cost) in cont.items()]).set_index("book")
    pd.DataFrame({k: v for k, (v, _, _) in cont.items()}).to_csv(f"{RESULT_DIR}/nav{tag}.csv")
    t.to_csv(f"{RESULT_DIR}/continuous{tag}.csv")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(f"continuous {start} .. {end}\n", t.to_string(float_format=lambda x: f"{x:+.4f}"))
    if not windows:
        return t
    wrows = []
    for s in windows:
        e = (pd.Timestamp(s) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()
        w = versions(s, e, fp_daily)
        wrows.append({"start": str(s), **{k: stats(v)["total"] for k, (v, _, _) in w.items()}})
    wt = pd.DataFrame(wrows).set_index("start")
    wt["c - hold"] = wt["c_spot"] - wt["hold_5050"]
    wt["fp - btc"] = wt["fp_spot"] - wt["btc_gate"]
    wt.to_csv(f"{RESULT_DIR}/windows{tag}.csv")
    print("windows\n", wt.to_string(float_format=lambda x: f"{x:+.4f}"))
    n = len(wt)
    need = int(np.ceil(0.75 * n))
    a = wt["c - hold"]
    ok43 = (a.median() > 0 and (a > 0).sum() >= need and t.loc["c_spot", "total"] > t.loc["hold_5050", "total"]
            and t.loc["c_spot", "maxDD"] - t.loc["hold_5050", "maxDD"] >= 0.10)
    print(f"H43: c - hold median {a.median():+.4f}, positive {(a > 0).sum()}/{n} (need {need}); continuous total "
          f"{t.loc['c_spot', 'total']:+.4f} vs {t.loc['hold_5050', 'total']:+.4f}, maxDD {t.loc['c_spot', 'maxDD']:+.4f} "
          f"vs {t.loc['hold_5050', 'maxDD']:+.4f} -> {'PASS' if ok43 else 'fail'}")
    b = wt["fp - btc"]
    ok44 = (b.median() > 0 and (b > 0).sum() >= need and t.loc["fp_spot", "total"] > t.loc["btc_gate", "total"]
            and t.loc["fp_spot", "maxDD"] - t.loc["btc_gate", "maxDD"] >= -0.02)
    print(f"H44: fp - btc median {b.median():+.4f}, positive {(b > 0).sum()}/{n} (need {need}); continuous total "
          f"{t.loc['fp_spot', 'total']:+.4f} vs {t.loc['btc_gate', 'total']:+.4f}, maxDD {t.loc['fp_spot', 'maxDD']:+.4f} "
          f"vs {t.loc['btc_gate', 'maxDD']:+.4f} -> {'PASS' if ok44 else 'fail'}")
    return t


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a = a.parse_args()
    if a.test:
        run(date(2022, 1, 1), date(2025, 12, 31), windows=[], tag="_test_2022")
        return
    run()


if __name__ == "__main__":
    main()
