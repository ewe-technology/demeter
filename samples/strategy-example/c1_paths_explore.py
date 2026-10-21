"""Section 9 of reports/c1_drawdown_2026-10-21_report.md (listed only), run locally: python c1_paths_explore.py
Stylised gate-off books on three made-up daily paths (steady fall, crash and rebound, sideways), $100 in stablecoin
at day 0, fee proxy 0.10% a day of the LP's value on days the price is in range, 40 bps on every WBTC sold by a swap.
Structures: the C1 ladder, a fixed 0.7 ladder, the sell-range cycle (filled BTC is placed as a range just above the
price and sold back on bounces), a two-layer ladder (30% shallow, 70% deep) and a single wide ladder [p / 1.60, p x 1.01]. Fees are kept apart, not reinvested."""
import math

import numpy as np

FEE, SWAP = 0.001, 40e-4


def unit(p, a, b):
    """Value and BTC value per unit of liquidity of the range [a, b] at price p."""
    q = min(max(p, a), b)
    x = 1 / math.sqrt(q) - 1 / math.sqrt(b)
    y = math.sqrt(q) - math.sqrt(a)
    return x * p + y, x * p


class Pos:
    def __init__(self, value, p, a, b):
        self.a, self.b = a, b
        self.L = value / unit(p, a, b)[0]

    def val(self, p):
        v, btc = unit(p, self.a, self.b)
        return self.L * v, self.L * btc


def paths(n=120):
    t = np.arange(n + 1)
    fall = 100 * np.exp(-0.005 * t) * (1 + 0.02 * np.sin(t * 1.3))
    crash = np.where(t <= 7, 100 * (1 - 0.35 * t / 7), 65 + 35 * np.clip((t - 7) / 53, 0, 1))
    crash = crash * (1 + 0.015 * np.sin(t * 1.7))
    side = 100 * (1 + 0.12 * np.sin(2 * np.pi * t / 20))
    return {"持續下跌": fall, "急跌後反彈": crash, "橫盤 ±12%": side}


def run(px, kind):
    """kind: ladder | fixed | sell | layers | wide. Returns daily (value, BTC share), fees, swaps."""
    st = {"cash": 100.0, "fees": 0.0, "swaps": 0, "mode": None}
    pos = []

    def place_buy(p):
        if kind == "layers":
            v = st["cash"]
            pos.extend([Pos(0.3 * v, p, p / 1.15, p * 1.01), Pos(0.7 * v, p, p / 1.60, p / 1.15)])
        else:
            v = st["cash"] * (0.7 if kind == "fixed" else 1.0)
            pos.append(Pos(v, p, p / (1.60 if kind == "wide" else 1.40), p * 1.01))
        st["cash"] -= v
        st["mode"] = "buy"

    def close_all(p):
        for x in pos:
            v, btc = x.val(p)
            st["cash"] += v - btc * SWAP
            st["swaps"] += btc > 1e-9
        pos.clear()

    out = []
    for i, p in enumerate(px):
        if i == 0:
            place_buy(p)
        else:
            for x in pos:
                if x.a <= px[i - 1] <= x.b or x.a <= p <= x.b:
                    st["fees"] += FEE * x.val(p)[0]
            lo = min(x.a for x in pos) if pos else None
            hi = max(x.b for x in pos) if pos else None
            if st["mode"] == "buy" and pos and (p < lo or p > hi):
                if kind == "sell" and p < lo:  # filled: the BTC becomes a sell range [p, 1.25 p], no swap
                    v = sum(x.val(p)[0] for x in pos)
                    pos.clear()
                    pos.append(Pos(v, p, p, p * 1.25))
                    st["mode"] = "sell"
                else:
                    close_all(p)
                    place_buy(p)
            elif st["mode"] == "sell" and pos:
                x = pos[0]
                if p > x.b:  # sold out on the bounce: back to a buy ladder
                    st["cash"] += x.val(p)[0]
                    pos.clear()
                    place_buy(p)
                elif p < x.a:  # still falling: move the sell range down with the price (all BTC, no swap)
                    pos[0] = Pos(x.val(p)[0], p, p, p * 1.25)
        v = st["cash"] + sum(x.val(p)[0] for x in pos)
        btc = sum(x.val(p)[1] for x in pos)
        out.append((v, btc / v if v else 0.0))
    return np.array(out), st["fees"], st["swaps"]


NAMES = {"ladder": "C1 原版買單", "fixed": "固定 0.7 買單", "sell": "接到後改掛賣單", "layers": "分層 30% 淺 / 70% 深", "wide": "單一 [p/1.60, p×1.01]"}
for name, px in paths().items():
    print(f"\n== {name}：BTC 終點 {px[-1] / px[0] - 1:+.0%}，最低 {px.min() / px[0] - 1:+.0%}")
    for k, label in NAMES.items():
        arr, fees, swaps = run(px, k)
        v, sh = arr[:, 0], arr[:, 1]
        dd = (v / np.maximum.accumulate(v) - 1).min()
        snap = " ".join(f"d{d}:{v[d]:.0f}/{sh[d]:.0%}" for d in (7, 30, 60, 120))
        print(f"  {label:14s} 終值 {v[-1] + fees:6.1f}（價格 {v[-1]:5.1f} + 手續費 {fees:4.1f}） 最低 {v.min():5.1f} "
              f"回撤 {dd:6.1%} 最大 BTC {sh.max():4.0%} 賣幣 {swaps:2d} | 帳值/BTC 占比 {snap}")
