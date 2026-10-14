"""
H40-H42 of reports/plan_2026-10-14_fprime_spot.md (registered in f91d7d0, before this code ran): maker-defense v3's
F' against the BTC EMA100 gate, both held as WETH spot on 0x88e6 with the rest in USDC.

  fp_spot   H38's spot rules (maker_defense_h38.spot_sim) at judgement hour h: below centre x 0.80 sell all, above
            centre x 1.20 move the centre (sell all while the divergence flag is on), then follow F' with v3's
            12.5% rule. F' from the Binance closes at h = 0 (H40, H42), from 0x88e6's hourly price at every h (H41).
  btc_gate  pool_lp_batch.gate("99ac", 100, h): on 100% ETH, off 100% USDC, trades only at a switch
  eth_gate  gate("88e6", 100, h), listed

Costs as H38's spot books: the pool fee in the fill, price impact (linear, 0x88e6's liquidity) and one swap's gas
subtracted afterwards. Hourly bars from H38's cache (first price of the hour). With delay = 1 the day's decisions use
the h:00 price and signal and trade at h+1:00; the first trade is not delayed.

Run from samples/strategy-example:
  PYTHONPATH=../.. python fprime_spot.py --test      # fp_spot at UTC 00 must reproduce H38's spot_100k
  PYTHONPATH=../.. python fprime_spot.py --gates     # the 48 gate files (99ac and 88e6, hours 0..23)
  PYTHONPATH=../.. python fprime_spot.py --runs
"""
import argparse
import os
from datetime import date

import numpy as np
import pandas as pd

import maker_defense_h38 as h38
import pool_lp_batch as batch

v3 = h38.v3
RESULT_DIR = "result/fprime-spot"
START, END = h38.CONT_START, h38.SIGNAL_END
POOL = h38.POOLS["88e6"]


class FPRules:
    """H38's spot rules on one F' frame; decide() returns the day's trades as (kind, target ETH share) in order."""

    def __init__(self, daily: pd.DataFrame):
        self.daily = daily
        self.centre = None
        self.prev = None

    def row(self, ts):
        return self.daily.loc[(ts - pd.Timedelta(days=1)).normalize()]

    def first(self, ts):
        target = float(self.row(ts)["Fp"])
        self.prev = target
        return [("first", target)]

    def decide(self, ts, px, coin, cash):
        r = self.row(ts)
        out = []
        if coin > 0 and self.centre is not None:
            if px < self.centre * v3.LOWER_STOP:
                out.append(("lower", 0.0))
                coin = 0.0
            elif px > self.centre * v3.UPPER_REBUILD:
                if int(r["diverged"]):
                    out.append(("upper_diverged", 0.0))
                    coin = 0.0
                else:
                    self.centre = px
        value = cash + coin * px
        current = coin * px / value if value > 0 else 0.0
        target = float(r["Fp"])
        due = (abs(target - current) >= float(v3.FOLLOW_THRESHOLD) or (target == 0 and current > 0)
               or (target >= float(v3.FOLLOW_FULL_F) and current < 1 - float(v3.FOLLOW_FULL_GAP)))
        if due:
            out.append(("follow" if target != self.prev else "drift", target))
        self.prev = target
        return out

    def executed(self, kind, target, px):
        if kind in ("lower", "upper_diverged"):
            self.centre = None
        else:
            self.centre = px if target > 0 else None


class GateRules:
    """On: all ETH, off: all USDC; a trade only when the gate switches."""

    def __init__(self, gate: pd.Series):
        self.gate = gate
        self.on = None

    def state(self, ts) -> bool:
        return bool(self.gate.asof(ts))

    def first(self, ts):
        self.on = self.state(ts)
        return [("first", 1.0 if self.on else 0.0)]

    def decide(self, ts, px, coin, cash):
        on = self.state(ts)
        if on == self.on:
            return []
        self.on = on
        return [("on" if on else "off", 1.0 if on else 0.0)]

    def executed(self, kind, target, px):
        pass


_HOURLY = {}


def hourly() -> pd.DataFrame:
    if "88e6" not in _HOURLY:
        _HOURLY["88e6"] = pd.read_pickle(h38.hourly_path("88e6"))
    return _HOURLY["88e6"]


def book(name: str, rules, start: date, end: date, hour: int = 0, delay: int = 0, initial: float = 100_000,
         save: bool = False) -> dict:
    data = hourly()
    t0 = pd.Timestamp(start) + pd.Timedelta(hours=hour)
    t1 = pd.Timestamp(end) + pd.Timedelta(hours=23)
    data = data[(data.index >= t0) & (data.index <= t1)]
    price = data["price"].astype(float)
    liq = data["currentLiquidity"].astype(float)
    eth_usd = batch.eth_daily()
    cash, coin = float(initial), 0.0
    trades, pending = [], None
    cash_path, coin_path = np.empty(len(price)), np.empty(len(price))

    def execute(ts, px, orders):
        nonlocal cash, coin
        for kind, share in orders:
            value = cash + coin * px
            delta = share * value - coin * px
            if abs(delta) < 1e-6:
                rules.executed(kind, share, px)
                continue
            fee = abs(delta) * 0.0005
            coin += delta / px
            cash -= delta + fee
            trades.append({"t": ts, "kind": kind, "notional": abs(delta), "swap_fee": fee,
                           "impact": h38.swap_impact(abs(delta), px, float(liq.asof(ts)), POOL),
                           "gas": h38.gas_usd("SwapAction", ts, POOL, eth_usd)})
            rules.executed(kind, share, px)

    for i, ts in enumerate(price.index):
        px = float(price.iloc[i])
        if i == 0:
            execute(ts, px, rules.first(ts))
        else:
            if pending is not None and ts >= pending[0]:
                execute(ts, px, pending[1])
                pending = None
            if ts.hour == hour:
                orders = rules.decide(ts, px, coin, cash)
                if orders:
                    if delay:
                        pending = (ts + pd.Timedelta(hours=delay), orders)
                    else:
                        execute(ts, px, orders)
        cash_path[i], coin_path[i] = cash, coin
    t = pd.DataFrame(trades, columns=["t", "kind", "notional", "swap_fee", "impact", "gas"])
    paid = (t["impact"] + t["gas"]).groupby(t["t"]).sum().cumsum() if len(t) else pd.Series(dtype=float)
    coin_s = pd.Series(coin_path, index=price.index)
    nav_pre = pd.Series(cash_path, index=price.index) + coin_s * price
    nav = nav_pre - (paid.reindex(price.index, method="ffill").fillna(0.0) if len(paid) else 0.0)
    x = nav / initial
    row = {"book": name, "start": str(start), "end": str(end), "hour": hour, "delay": delay,
           "net": x.iloc[-1] - 1, "maxDD": float((x / x.cummax() - 1).min()), "trades": len(t),
           "swap_fee": t["swap_fee"].sum() / initial, "impact": t["impact"].sum() / initial,
           "gas": t["gas"].sum() / initial, "eth_exposure": float((coin_s * price / nav_pre).mean())}
    for y in range(start.year, end.year + 1):
        part, prev = x.loc[:f"{y}-12-31 23:00"], x.loc[:f"{y - 1}-12-31 23:00"]
        if len(part) and part.index[-1].year == y:
            row[str(y)] = part.iloc[-1] / (prev.iloc[-1] if len(prev) else 1.0) - 1
    if save:
        pd.DataFrame({"net": nav, "net_pre": nav_pre, "price": price, "eth": coin_s}).to_csv(f"{RESULT_DIR}/nav_{name}.csv")
        t.to_csv(f"{RESULT_DIR}/trades_{name}.csv", index=False)
    return row


def checks(x: pd.Series) -> dict:
    """H2's three on window differences in start order."""
    x = x.sort_index()
    h = len(x) // 2
    return {"median": float(x.median()), "positive": int((x > 0).sum()), "n": len(x),
            "first_half": float(x.iloc[:h].median()), "second_half": float(x.iloc[h:].median()),
            "pass": bool(x.median() > 0 and (x > 0).sum() >= 12 and x.iloc[:h].median() > 0 and x.iloc[h:].median() > 0)}


def run_all():
    os.makedirs(RESULT_DIR, exist_ok=True)
    rows = []
    fp0 = v3.binance_daily_frame(START, END)
    btc0, eth0 = batch.gate("99ac", 100), batch.gate("88e6", 100)
    # H40 and H42: UTC 00, continuous and 16 windows, instant and one hour late
    for delay in (0, 1):
        tag = "" if delay == 0 else "_delay"
        # the first window starts on START too, so the continuous book is named, not told apart by its start
        books = [("cont", START, END)] + [(f"win_{s}", s, h38.window_end(s)) for s in h38.WINDOW_STARTS]
        for kind, s, e in books:
            for v, rules in (("fp_spot", FPRules(fp0)), ("btc_gate", GateRules(btc0)), ("eth_gate", GateRules(eth0))):
                if delay and v == "eth_gate":
                    continue
                rows.append({"version": v, "set": f"{kind}{tag}",
                             **book(f"{v}_{kind}{tag}", rules, s, e, delay=delay, save=(kind == "cont"))})
    print("UTC 00 done", flush=True)
    # H41: 24 judgement hours, continuous, F' from the pool price at every hour (00 included)
    for h in range(24):
        fp = h38.pool_signal(hourly(), h, END)
        btc, eth = batch.gate("99ac", 100, h), batch.gate("88e6", 100, h)
        for v, rules in (("fp_spot", FPRules(fp)), ("btc_gate", GateRules(btc)), ("eth_gate", GateRules(eth))):
            rows.append({"version": v, "set": f"hour_{h:02d}", **book(f"{v}_hour_{h:02d}", rules, START, END, hour=h)})
        print(f"hour {h:02d} done", flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/books.csv", index=False)
    report(t)


def report(t: pd.DataFrame):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    p = t.pivot_table(index="set", columns="version", values="net")
    dd = t.pivot_table(index="set", columns="version", values="maxDD")
    cont = t[t["set"] == "cont"].set_index("version")
    print("H40 continuous (UTC 00, Binance F')\n",
          cont[["net", "maxDD", "trades", "swap_fee", "impact", "gas", "eth_exposure", "2022", "2023", "2024", "2025",
                "2026"]].to_string(float_format=lambda v: f"{v:+.4f}"))
    wins = [f"win_{s}" for s in h38.WINDOW_STARTS]
    diff = p.loc[wins, "fp_spot"] - p.loc[wins, "btc_gate"]
    print("H40 windows\n", pd.DataFrame({"fp_spot": p.loc[wins, "fp_spot"], "btc_gate": p.loc[wins, "btc_gate"],
                                         "eth_gate": p.loc[wins, "eth_gate"], "fp - btc": diff})
          .to_string(float_format=lambda v: f"{v:+.4f}"))
    w = checks(diff)
    c_ret = cont.loc["fp_spot", "net"] - cont.loc["btc_gate", "net"]
    c_dd = cont.loc["fp_spot", "maxDD"] - cont.loc["btc_gate", "maxDD"]
    ok = w["pass"] and c_ret > 0 and c_dd >= -0.02
    print(f"H40: windows {w}; continuous return diff {c_ret:+.4f}, maxDD diff {c_dd:+.4f} -> {'PASS' if ok else 'fail'}")
    hours = [f"hour_{h:02d}" for h in range(24)]
    hd = p.loc[hours, "fp_spot"] - p.loc[hours, "btc_gate"]
    hdd = dd.loc[hours, "fp_spot"] - dd.loc[hours, "btc_gate"]
    print("H41 hours\n", pd.DataFrame({"fp_spot": p.loc[hours, "fp_spot"], "btc_gate": p.loc[hours, "btc_gate"],
                                       "eth_gate": p.loc[hours, "eth_gate"], "fp - btc": hd, "maxDD fp - btc": hdd})
          .to_string(float_format=lambda v: f"{v:+.4f}"))
    ok41 = hd.median() > 0 and (hd > 0).sum() >= 18
    print(f"H41: median diff {hd.median():+.4f}, positive {(hd > 0).sum()}/24 -> {'PASS' if ok41 else 'fail'}")
    dwins = [f"{w_}_delay" for w_ in wins]
    for v in ("fp_spot", "btc_gate"):
        dl = p.loc[dwins, v].to_numpy() - p.loc[wins, v].to_numpy()
        cd = p.loc["cont_delay", v] - p.loc["cont", v]
        cdd = dd.loc["cont_delay", v] - dd.loc["cont", v]
        print(f"H42 {v}: delay - instant per window min {dl.min():+.4f} median {np.median(dl):+.4f} max {dl.max():+.4f}; "
              f"continuous return {cd:+.4f}, maxDD {cdd:+.4f} (listed)")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a.add_argument("--gates", action="store_true")
    a.add_argument("--runs", action="store_true")
    a.add_argument("--report", action="store_true")
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if a.test:
        btc0 = batch.gate("99ac", 100)
        r = book("test_fp", FPRules(v3.binance_daily_frame(START, END)), START, END)
        ref = pd.read_csv(f"{h38.RESULT_DIR}/run_spot_100k.csv").iloc[0]
        print(f"fp_spot UTC 00 {r['net']:+.6f} maxDD {r['maxDD']:+.6f} trades {r['trades']}; "
              f"H38 spot_100k {ref['net']:+.6f} {ref['maxDD']:+.6f} {ref['trades']}")
        g = book("test_btc", GateRules(btc0), START, END, save=True)
        sw = btc0.loc[pd.Timestamp(START):pd.Timestamp(END)].astype(int).diff().iloc[1:]
        print(f"btc_gate {g['net']:+.4f} maxDD {g['maxDD']:+.4f}; trades {g['trades']} (the first included), "
              f"gate switches after the first day {int((sw != 0).sum())}")
        return
    if a.gates:
        for h in range(24):
            batch.gate("99ac", 100, h)
            batch.gate("88e6", 100, h)
            print(f"gates {h:02d}", flush=True)
        return
    if a.runs:
        run_all()
    if a.report:
        report(pd.read_csv(f"{RESULT_DIR}/books.csv"))


if __name__ == "__main__":
    main()
