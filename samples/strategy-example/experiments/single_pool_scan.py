"""Single-pool strategy scan (research screen, not an EXP): which strategy families beat v6 / spec v1 on one pool?

A fast screen, not demeter. Decisions at each UTC day close; LP fees accrue per minute from the pool's own swaps
(fee x input amount x our share of active liquidity, only while the close tick is inside our range); value at the day
close. Swaps cost a flat 0.1% of the notional (spec v1's cost model); gas is counted (rebuilds), not charged.
Signals come from Binance daily closes (as spec v1): ETHUSDT for 0x88e6, ETHUSDT / BTCUSDT for 0x4585.
Both pools have quote = token0, base = token1 (USDC/ETH, WBTC/ETH): values are in quote (USD, BTC).

usage: python experiments/single_pool_scan.py <pool-prefix> [start] [end]
"""
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/Users/dinohuang/Desktop/demeter-momentum/samples"   # minute data lives in the main checkout
CACHE = os.environ.get("SCAN_CACHE", os.path.join(MAIN, "strategy-example", "result", "single_pool_scan"))
SWAP_COST = 0.001

POOLS = {   # prefix: (address, folder, dec0 (quote), dec1 (base), fee, signal column(s), first day, init quote)
    "0x88e6": ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "real-data", 6, 18, 0.0005, ("ETHUSDT",), "2021-05-06", 100_000.0),
    "0x4585": ("0x4585fe77225b41b697c938b018e2ac67ac5a20c0", "holdout-data", 8, 18, 0.0005, ("ETHUSDT", "BTCUSDT"), "2021-11-02", 2.0),
}


def load_minutes(prefix: str) -> pd.DataFrame:
    addr, folder, d0, d1, *_ = POOLS[prefix]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{prefix}-minutes.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    d = os.path.join(MAIN, folder, addr)
    frames = []
    for f in sorted(os.listdir(d)):
        x = pd.read_csv(os.path.join(d, f), usecols=["timestamp", "closeTick", "inAmount0", "inAmount1", "currentLiquidity"],
                        dtype={"inAmount0": float, "inAmount1": float, "currentLiquidity": float})
        if len(x):
            frames.append(x)
    m = pd.concat(frames, ignore_index=True)
    m["timestamp"] = pd.to_datetime(m["timestamp"])
    m = m.sort_values("timestamp").drop_duplicates("timestamp")
    m["closeTick"] = m["closeTick"].ffill()
    m = m.dropna(subset=["closeTick"])
    m["P"] = 10.0 ** (d1 - d0) / 1.0001 ** m["closeTick"].astype(float)   # base price in quote
    # fee base per minute in quote units (fee tier applied later), pool liquidity in human units
    m["vol_q"] = m["inAmount0"] / 10 ** d0 + m["inAmount1"] / 10 ** d1 * m["P"]
    m["L_pool"] = m["currentLiquidity"] / 10 ** ((d0 + d1) / 2)
    m = m[["timestamp", "P", "vol_q", "L_pool"]].reset_index(drop=True)
    m.to_parquet(path)
    return m


def signal_closes(prefix: str) -> pd.Series:
    b = pd.read_csv(os.path.join(MAIN, "binance_daily_closes.csv"), parse_dates=["date"]).set_index("date")
    cols = POOLS[prefix][5]
    return (b[cols[0]] / b[cols[1]] if len(cols) == 2 else b[cols[0]]).dropna()


# ---------- v3 position math (human units, P = base price in quote) ----------

def lp_amounts(L, P, pa, pb):
    """(base, quote) held by liquidity L on [pa, pb] at price P."""
    s, sa, sb = np.sqrt(P), np.sqrt(pa), np.sqrt(pb)
    s = np.clip(s, sa, sb)
    return L * (1 / s - 1 / sb), L * (s - sa)


def lp_value_per_L(P, pa, pb):
    b, q = lp_amounts(1.0, P, pa, pb)
    return b * P + q


# ---------- engine ----------

class Book:
    def __init__(self, init_q):
        self.b, self.q = 0.0, init_q   # idle base / quote
        self.L, self.pa, self.pb = 0.0, None, None
        self.rebuilds, self.swap_notional, self.fees = 0, 0.0, 0.0

    def nav(self, P):
        lb, lq = lp_amounts(self.L, P, self.pa, self.pb) if self.L else (0.0, 0.0)
        return (self.b + lb) * P + self.q + lq

    def lp_value(self, P):
        if not self.L:
            return 0.0
        lb, lq = lp_amounts(self.L, P, self.pa, self.pb)
        return lb * P + lq

    def set_target(self, P, f_lp, rng, w_base):
        """Close everything, then hold f_lp of NAV in an LP on rng=(pa, pb) and w_base of the rest in base."""
        if self.L:
            lb, lq = lp_amounts(self.L, P, self.pa, self.pb)
            self.b += lb
            self.q += lq
            self.L = 0.0
        nav = self.b * P + self.q
        if f_lp > 0 and rng is not None:
            pa, pb = rng
            vL = lp_value_per_L(P, pa, pb)
            L = f_lp * nav / vL
            lb, lq = lp_amounts(L, P, pa, pb)
        else:
            L, lb, lq, pa, pb = 0.0, 0.0, 0.0, None, None
        spot = nav - (lb * P + lq)
        want_b = lb + w_base * spot / P
        trade = abs(want_b - self.b) * P
        cost = SWAP_COST * trade
        self.swap_notional += trade
        # pay the cost out of quote; whole book scaled down by the cost
        scale = (nav - cost) / nav
        L, lb, lq, want_b = L * scale, lb * scale, lq * scale, want_b * scale
        self.b = want_b - lb
        self.q = (nav - cost) - self.b * P - (lb * P + lq)
        self.L, self.pa, self.pb = L, pa, pb
        if L:
            self.rebuilds += 1


def run(prefix, strategy, start, end, minutes, sig):
    fee = POOLS[prefix][4]
    init_q = POOLS[prefix][7]
    m = minutes[(minutes.timestamp >= pd.Timestamp(start)) & (minutes.timestamp < pd.Timestamp(end) + pd.Timedelta(days=1))]
    day = m.timestamp.dt.normalize().values
    P_all, V_all, Lp_all = m.P.values, m.vol_q.values * fee, m.L_pool.values
    days, idx = np.unique(day, return_index=True)
    idx = list(idx) + [len(m)]
    book = Book(init_q)
    st = {}
    out = []
    P0 = P_all[0]
    strategy(book, P0, sig.loc[:pd.Timestamp(days[0]) - pd.Timedelta(days=1)], st, first=True)
    for i, d in enumerate(days):
        sl = slice(idx[i], idx[i + 1])
        P = P_all[sl]
        if book.L:
            inr = (P >= book.pa) & (P <= book.pb)
            share = book.L / (Lp_all[sl] + book.L)
            fq = float(np.sum(V_all[sl] * share * inr))
            book.q += fq   # fees kept as quote
            book.fees += fq
        Pc = P[-1]
        out.append((pd.Timestamp(d), book.nav(Pc), Pc))
        hist = sig.loc[:pd.Timestamp(d)]
        strategy(book, Pc, hist, st, first=False)
    eq = pd.DataFrame(out, columns=["date", "nav", "P"]).set_index("date")
    return eq, book


def metrics(nav: pd.Series):
    r = nav.iloc[-1] / nav.iloc[0] - 1
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (1 + r) ** (1 / yrs) - 1
    dd = float((nav / nav.cummax() - 1).min())
    return r, cagr, dd, cagr / -dd if dd < 0 else np.nan


# ---------- strategies (fixed textbook constants, no tuning) ----------

def ema(h, n):
    return h.ewm(span=n, adjust=False).mean().iloc[-1]


def recentre(width_lo, width_hi):
    return lambda P: (P * (1 - width_lo), P * (1 + width_hi)) if width_hi is not None else (P * (1 - width_lo), P / (1 - width_lo))


def S_hold(w):
    def f(book, P, h, st, first):
        if first:
            book.set_target(P, 0, None, w)
    return f


def S_rebal(w, every=30):
    def f(book, P, h, st, first):
        st["n"] = st.get("n", -1) + 1
        if first or st["n"] % every == 0:
            book.set_target(P, 0, None, w)
    return f


def S_lp(width, recentre_on_exit=True, full=False):
    """Static LP of `width` (multiplicative, symmetric in log: [P/(1+w), P*(1+w)]); rebuild when out of range."""
    def rng(P):
        return (P / 1000, P * 1000) if full else (P / (1 + width), P * (1 + width))

    def f(book, P, h, st, first):
        if first or (recentre_on_exit and not (book.pa <= P <= book.pb)):
            book.set_target(P, 1.0, rng(P), 0.5)
    return f


def trend_on(h, kind):
    c = h.iloc[-1]
    if kind == "ema100":
        return c > ema(h, 100)
    if kind == "sma200":
        return c > h.iloc[-200:].mean()
    if kind == "tsmom84":
        return c > h.iloc[-85]
    if kind == "ema_cross":
        return ema(h, 20) > ema(h, 100)
    raise ValueError(kind)


def S_trend_spot(kind, off_w=0.0):
    def f(book, P, h, st, first):
        on = trend_on(h, kind)
        if first or on != st.get("on"):
            book.set_target(P, 0, None, 1.0 if on else off_w)
            st["on"] = on
    return f


def S_trend_lp(kind, width, full=False, off_w=0.0):
    """Above the trend line: LP (recentre on exit); below: off_w in base, rest quote."""
    def rng(P):
        return (P / 1000, P * 1000) if full else (P / (1 + width), P * (1 + width))

    def f(book, P, h, st, first):
        on = trend_on(h, kind)
        changed = first or on != st.get("on")
        st["on"] = on
        if on and (changed or not (book.pa <= P <= book.pb)):
            book.set_target(P, 1.0, rng(P), 0.5)
        elif not on and changed:
            book.set_target(P, 0, None, off_w)
    return f


def S_trend_ladder(kind, width):
    """Above the trend: hold base plus a sell-side range order [P, P(1+w)] on half (covered-call-like);
    below: quote plus a buy-side range order [P/(1+w), P] on half (earns fees while waiting, buys dips)."""
    def f(book, P, h, st, first):
        on = trend_on(h, kind)
        changed = first or on != st.get("on")
        st["on"] = on
        out = book.L and not (book.pa <= P <= book.pb)
        if changed or out:
            if on:
                book.set_target(P, 0.5, (P * 1.0001, P * (1 + width)), 1.0)
            else:
                book.set_target(P, 0.5, (P / (1 + width), P / 1.0001), 0.0)
    return f


def S_voltarget(target, kind=None):
    def f(book, P, h, st, first):
        st["n"] = st.get("n", -1) + 1
        if not first and st["n"] % 7:
            return
        r = np.log(h).diff().iloc[-30:]
        vol = float(r.std() * np.sqrt(365))
        w = min(1.0, target / vol) if vol > 0 else 1.0
        if kind and not trend_on(h, kind):
            w = 0.0
        if first or abs(w - st.get("w", -1)) > 0.1:
            book.set_target(P, 0, None, w)
            st["w"] = w
    return f


def S_meanrev(n=50, lp=False):
    """Bollinger mean reversion: base weight 0.5 - z/4 clipped to [0, 1], z of log price vs its n-day mean, weekly."""
    def f(book, P, h, st, first):
        st["n"] = st.get("n", -1) + 1
        if not first and st["n"] % 7:
            return
        lg = np.log(h.iloc[-n:])
        z = float((lg.iloc[-1] - lg.mean()) / lg.std())
        w = float(np.clip(0.5 - z / 4, 0, 1))
        if lp:   # wide LP centred on the n-day mean: an LP is itself a mean-reversion bet
            mu = float(np.exp(lg.mean()))
            book.set_target(P, 1.0, (mu / 1.3, mu * 1.3) if mu / 1.3 < P < mu * 1.3 else (P / 1.3, P * 1.3), 0.5)
        else:
            book.set_target(P, 0, None, w)
    return f


# ---------- dynamic ladder width (the user's 2026-10-07 follow-up: make v6's +-20% dynamic) ----------

POOL_DAILY = None   # per-day pool stats (fee/LVR, volume), set by main()
DVOL = pd.read_csv(os.path.join(MAIN, "deribit_dvol_daily.csv"), parse_dates=["date"]).set_index("date")


def pool_daily(minutes: pd.DataFrame, fee: float) -> pd.DataFrame:
    m = minutes.set_index("timestamp")
    r = np.log(m["P"]).diff().fillna(0.0)
    per_l_fee = fee * m["vol_q"] / m["L_pool"].where(m["L_pool"] > 0)
    per_l_lvr = r * r * np.sqrt(m["P"]) / 4
    d = pd.DataFrame({"fee": per_l_fee, "lvr": per_l_lvr, "vol": m["vol_q"]}).resample("1D").sum(min_count=1).dropna()
    d["R7"] = d["fee"].rolling(7, min_periods=1).sum() / d["lvr"].rolling(7, min_periods=1).sum()
    d["vol_ratio"] = d["vol"].rolling(7, min_periods=1).mean() / d["vol"].rolling(90, min_periods=7).median()
    return d


def clamp(w, lo=0.10, hi=0.40):
    return float(min(max(w, lo), hi)) if w == w else 0.20


def width_fn(kind, prefix):
    def f(h):
        day = h.index[-1]
        lr = np.log(h).diff()
        if kind.startswith("fixed"):
            return int(kind[5:]) / 100
        if kind == "vol30":     # EXP-030's rule (10..30% there)
            return clamp(lr.iloc[-30:].std() * np.sqrt(30))
        if kind == "relvol":    # vol relative to its own last year: same 20% in a normal regime
            s30 = lr.rolling(30).std()
            return clamp(0.20 * s30.iloc[-1] / s30.iloc[-365:].median())
        if kind == "dvol":      # implied one-month 1-sigma move (Deribit DVOL, ETH)
            v = DVOL["ETH"].loc[:day]
            return clamp(v.iloc[-1] / 100 * np.sqrt(30 / 365)) if len(v) else 0.20
        if kind == "er30":      # Kaufman efficiency: trending -> wide, choppy -> narrow
            c = h.iloc[-31:]
            er = abs(c.iloc[-1] - c.iloc[0]) / c.diff().abs().sum()
            return clamp(0.10 + 0.40 * er)
        if kind == "feelvr7":   # pool pays its LVR -> concentrate; it does not -> widen
            d = POOL_DAILY.loc[:day]
            return 0.20 if not len(d) else (0.15 if d["R7"].iloc[-1] >= 1 else 0.30)
        if kind == "volume":    # busy pool -> narrow
            d = POOL_DAILY.loc[:day]
            x = d["vol_ratio"].iloc[-1] if len(d) else 1.0
            return 0.15 if x > 1.2 else (0.30 if x < 0.8 else 0.20)
        if kind == "trenddist":  # far from the EMA100 -> wider
            return clamp(0.15 + abs(h.iloc[-1] / ema(h, 100) - 1))
        raise ValueError(kind)
    return f


def S_lp_dyn(wf, trend=None):
    """LP recentred on exit with the width picked at each build; with `trend`, LP only above the line (quote below)."""
    def f(book, P, h, st, first):
        on = trend_on(h, trend) if trend else True
        changed = first or on != st.get("on")
        st["on"] = on
        if on and (changed or not (book.pa <= P <= book.pb)):
            w = wf(h)
            st.setdefault("widths", []).append(w)
            book.set_target(P, 1.0, (P / (1 + w), P * (1 + w)), 0.5)
        elif not on and changed:
            book.set_target(P, 0, None, 0.0)
    return f


WIDTHS = ["fixed20", "fixed30", "fixed40", "vol30", "relvol", "dvol", "er30", "feelvr7", "volume", "trenddist"]

STRATEGIES = {
    "hold_quote": S_hold(0.0),
    "hold_base": S_hold(1.0),
    "rebal_50_50": S_rebal(0.5),
    "lp_full_range": S_lp(0, full=True),
    "lp_pm50": S_lp(0.5),
    "lp_pm20": S_lp(0.2),
    "lp_pm10": S_lp(0.1),
    "trend_ema100_spot": S_trend_spot("ema100"),
    "trend_sma200_spot": S_trend_spot("sma200"),
    "trend_tsmom84_spot": S_trend_spot("tsmom84"),
    "trend_ema20x100_spot": S_trend_spot("ema_cross"),
    "trend_ema100_lp20": S_trend_lp("ema100", 0.2),
    "trend_ema100_lpfull": S_trend_lp("ema100", 0, full=True),
    "trend_ema100_lp50": S_trend_lp("ema100", 0.5),
    "trend_ema100_ladder20": S_trend_ladder("ema100", 0.2),
    "voltarget_60": S_voltarget(0.6),
    "voltarget_60_ema100": S_voltarget(0.6, "ema100"),
    "meanrev_bb50": S_meanrev(50),
    "meanrev_lp_mean50": S_meanrev(50, lp=True),
}
DYN = {}
for _w in WIDTHS:
    DYN[f"lp_w_{_w}"] = (_w, None)
    DYN[f"trend_lp_w_{_w}"] = (_w, "ema100")

BASELINES = {   # demeter full-history runs in the main checkout (same windows)
    "0x88e6": {"specv1 (A)": "0x88e6-opt-AGAGBGCGDGEGFGGGH-specv1-2021-05-06-2026-09-17/equity_A_v6.csv",
               "v6.75 on specv1 (GA)": "0x88e6-opt-AGAGBGCGDGEGFGGGH-specv1-2021-05-06-2026-09-17/equity_GA_nolow.csv",
               "v6.75+xasset (GB)": "0x88e6-opt-AGAGBGCGDGEGFGGGH-specv1-2021-05-06-2026-09-17/equity_GB_nolow_xasset.csv"},
    "0x4585": {"v6 (A)": "0x4585-opt-ACADOEBAIAK-2021-11-02-2026-09-17/equity_A_v6.csv",
               "v6.75 (CA)": "0x4585-opt-ACADOEBAIAK-2021-11-02-2026-09-17/equity_CA_no_new_low_refill.csv",
               "EXP-140 (EB)": "0x4585-opt-ACADOEBAIAK-2021-11-02-2026-09-17/equity_EB_tier_svr_nlxmacro.csv"},
}


def main():
    prefix = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else POOLS[prefix][6]
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-09-17"
    minutes = load_minutes(prefix)
    sig = signal_closes(prefix)
    global POOL_DAILY
    POOL_DAILY = pool_daily(minutes, POOLS[prefix][4])
    only = os.environ.get("SCAN_ONLY")
    rows, curves = [], {}
    res_dir = os.path.join(MAIN, "strategy-example", "result", "v6_validate")
    for name, rel in BASELINES[prefix].items():
        p = os.path.join(res_dir, rel)
        if os.path.exists(p):
            nav = pd.read_csv(p, index_col=0, parse_dates=True)["net_value"]
            nav = nav.loc[start:end]
            rows.append((name, *metrics(nav), np.nan, np.nan))
            curves[name] = nav
    todo = dict(STRATEGIES)
    for k, (w, tr) in DYN.items():
        if w == "dvol" and prefix != "0x88e6":
            continue
        todo[k] = S_lp_dyn(width_fn(w, prefix), tr)
    if only:
        todo = {k: v for k, v in todo.items() if any(k.startswith(o) for o in only.split(","))}
    for name, strat in todo.items():
        eq, book = run(prefix, strat, start, end, minutes, sig)
        r = metrics(eq.nav)
        rows.append((name, *r, book.rebuilds, book.fees / POOLS[prefix][7]))
        if st_w := getattr(strat, "widths", None):
            pass
        curves[name] = eq.nav
    t = pd.DataFrame(rows, columns=["strategy", "total", "cagr", "max_dd", "calmar", "lp_builds", "fees_over_init"])
    pd.set_option("display.width", 200)
    print(f"{prefix} {start}..{end}  (values in quote: {'USD' if prefix == '0x88e6' else 'BTC'})")
    print(t.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    os.makedirs(CACHE, exist_ok=True)
    t.to_csv(os.path.join(CACHE, f"{prefix}-{start}-{end}-summary.csv"), index=False)
    pd.DataFrame(curves).to_csv(os.path.join(CACHE, f"{prefix}-{start}-{end}-curves.csv"))


if __name__ == "__main__":
    main()
