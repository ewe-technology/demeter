"""
Robustness checks on the spot BTC gate of spot_btc_eth_gate.py (report section 11). Base config:
BTC/USD close above its EMA100 -> 50% ETH + 50% BTC, otherwise USDC, trade only when the target changes.

  --hours      daily close taken at every UTC hour instead of 00:00, and trading 0-48 h after the signal
  --plateau    EMA span 40-250 x ETH share 0-100%
  --yield      idle USDC earning 0 / 3 / 5% a year
  --bench      against common trend-following and volatility-targeting rules
  --volscale   each coin's share cut when its own 30-day volatility is high, aimed at the ETH-only drop
  --bootstrap  paired block bootstrap of daily returns, base vs buy-and-hold 50/50
  (no flag: all of the above)
  --minute     the base and a few alternatives replayed on minute prices, against the hourly run

Signals come from the hourly price cache (the price at the top of each hour), not the minute closes, so the base
numbers differ slightly from section 11. 2026 was looked at in section 11 already: it is shown, never used to choose.

Run from samples/strategy-example after spot_btc_eth_gate.py has built the price cache:
  PYTHONPATH=../.. python spot_robustness.py
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

from spot_btc_eth_gate import END, HOLDOUT, IN_SAMPLE, RESULT_DIR, load_prices, stats, yearly
from tri_btc_eth_gate import DATA_START, ETH_POOL, RATIO_POOL

COST_BPS = 10
DROP = ("2024-12-16", "2025-03-05")  # the ETH-only drop of section 9 the BTC gate does not cover
HOUR = pd.Timedelta(hours=1)


def closes(prices: pd.DataFrame, hour: int = 0) -> pd.DataFrame:
    """One row per day: the price at `hour` UTC, which is the close of the hour before."""
    return prices[prices.index.hour == hour]


def simulate(weights: pd.DataFrame, prices: pd.DataFrame, start: str = IN_SAMPLE[0], cost_bps: float = COST_BPS,
             cash_yield: float = 0.0, threshold: float | None = None, exposure: bool = False):
    """
    Hourly net value. `weights` holds the (eth, btc) value shares wanted from each timestamp on, the rest in USDC.
    threshold None: trade whenever the wanted shares change. A number: trade when any share has drifted further than
    that from the wanted one (used by the rules whose target moves a little every day).
    Returns (nav, trades), or with exposure=True (nav, trades, the share of the net value actually in ETH and BTC).
    """
    p = prices.loc[start:]
    w = weights.loc[start:]
    w = w[w.index.isin(p.index)]
    t0 = p.index[0]
    growth = lambda t: (1 + cash_yield) ** ((t - t0).total_seconds() / (365.25 * 86400))  # one parked USDC since t0
    cost = cost_bps / 10_000
    q_eth, q_btc, units = 0.0, 0.0, 100_000.0
    last, trades, rows = None, 0, []
    for t, we, wb in zip(w.index, w["eth"].to_numpy(), w["btc"].to_numpy()):
        pe, pb, g = p.at[t, "eth"], p.at[t, "btc"], growth(t)
        value = q_eth * pe + q_btc * pb + units * g
        if threshold is None:
            go = (we, wb) != last
        else:
            go = max(abs(we - q_eth * pe / value), abs(wb - q_btc * pb / value)) > threshold
        if go:
            moved = abs(we * value - q_eth * pe) + abs(wb * value - q_btc * pb)
            value -= moved * cost
            q_eth, q_btc, units = we * value / pe, wb * value / pb, value * (1 - we - wb) / g
            last, trades = (we, wb), trades + (moved > 1)
        rows.append((t, q_eth, q_btc, units))
    held = pd.DataFrame(rows, columns=["t", "eth", "btc", "units"]).set_index("t")
    held = held.reindex(p.index, method="ffill").fillna({"eth": 0.0, "btc": 0.0, "units": 100_000.0})
    g = (1 + cash_yield) ** ((p.index - t0).total_seconds() / (365.25 * 86400))
    crypto = held["eth"] * p["eth"] + held["btc"] * p["btc"]
    nav = crypto + held["units"] * g
    return (nav, trades, crypto / nav) if exposure else (nav, trades)


def summary(name: str, nav: pd.Series, trades: int | None = None, **extra) -> dict:
    ins = stats(nav, *IN_SAMPLE)
    hold = stats(nav, HOLDOUT, "2100-01-01")
    drop = nav.loc[DROP[0]:DROP[1]]
    return {"run": name, **extra, **yearly(nav), "total": ins["total"], "annual": ins["annual"], "maxDD": ins["maxDD"],
            "calmar": ins["calmar"], "drop window": drop.iloc[-1] / drop.iloc[0] - 1,
            "2026": hold["total"], "2026 maxDD": hold["maxDD"], "trades": trades}


# ---- weight rules. Every rule decides on the close at `hour` and trades `lag` hours later ----

def gate(prices, hour=0, span=100, eth=0.5, lag=0, ma="ema", each=False) -> pd.DataFrame:
    """
    each False: both coins in while BTC is above its average (the base rule).
    each True: every coin in only while it is above its own average.
    """
    c = closes(prices, hour)
    avg = c.ewm(span=span, adjust=False).mean() if ma == "ema" else c.rolling(span).mean()
    above = c > avg
    on_eth = above["eth"] if each else above["btc"]
    w = pd.DataFrame({"eth": eth * on_eth, "btc": (1 - eth) * above["btc"]}, index=c.index).astype(float)
    w.index = w.index + lag * HOUR
    return w


def constant(prices, eth=0.5, btc=0.5, monthly=False) -> pd.DataFrame:
    c = closes(prices)
    if monthly:
        c = c[c.index.day == 1]
    return pd.DataFrame({"eth": eth, "btc": btc}, index=c.index)


def ts_momentum(prices, lookback=90) -> pd.DataFrame:
    """Each coin 50% while its own return over `lookback` days is positive."""
    c = closes(prices)
    up = (c / c.shift(lookback) - 1) > 0
    return pd.DataFrame({"eth": 0.5 * up["eth"], "btc": 0.5 * up["btc"]}, index=c.index).astype(float)


def dual_momentum(prices, lookback=90) -> pd.DataFrame:
    """Monthly: all in the coin with the better `lookback`-day return if that return is positive, else USDC."""
    c = closes(prices)
    ret = (c / c.shift(lookback) - 1)[c.index.day == 1]
    best_eth = ret["eth"] > ret["btc"]
    best = ret.max(axis=1) > 0
    return pd.DataFrame({"eth": (best & best_eth).astype(float), "btc": (best & ~best_eth).astype(float)}, index=ret.index)


def realised_vol(prices, window=30) -> pd.DataFrame:
    r = closes(prices).pct_change()
    r["mix"] = 0.5 * r["eth"] + 0.5 * r["btc"]
    return r.rolling(window).std() * np.sqrt(365)


def vol_target(prices, base: pd.DataFrame, target: float) -> pd.DataFrame:
    """Scale both shares of `base` by target / realised 50/50 volatility, capped at 1."""
    scale = (target / realised_vol(prices)["mix"]).clip(upper=1).fillna(0)
    return base.mul(scale.reindex(base.index).ffill(), axis=0)


def vol_scale_each(prices, base: pd.DataFrame, target: float, coins=("eth", "btc")) -> pd.DataFrame:
    """Scale each coin's share by target / its own realised volatility, capped at 1."""
    vol = realised_vol(prices).reindex(base.index).ffill()
    out = base.copy()
    for coin in coins:
        out[coin] = base[coin] * (target / vol[coin]).clip(upper=1).fillna(0)
    return out


# ---- experiments ----

def run_hours(prices) -> pd.DataFrame:
    rows = []
    for hour in range(24):
        nav, trades = simulate(gate(prices, hour=hour), prices)
        rows.append(summary(f"close {hour:02d}h", nav, trades, test="close hour", value=hour))
    for lag in (0, 1, 2, 4, 8, 12, 24, 48):
        nav, trades = simulate(gate(prices, lag=lag), prices)
        rows.append(summary(f"lag {lag}h", nav, trades, test="lag", value=lag))
    return pd.DataFrame(rows).set_index("run")


def run_plateau(prices) -> pd.DataFrame:
    rows = []
    for span in range(40, 260, 10):
        for eth in np.round(np.arange(0, 1.01, 0.1), 1):
            nav, trades = simulate(gate(prices, span=span, eth=eth), prices)
            rows.append(summary(f"ema{span}_eth{eth:g}", nav, trades, span=span, eth=eth))
    return pd.DataFrame(rows).set_index("run")


BASE = "base: btc ema100 gate 50/50"
HOLD = "hold 50/50"


def benchmarks(prices) -> dict:
    """name -> (weights, threshold)"""
    base = gate(prices)
    return {
        BASE: (base, None),
        HOLD: (constant(prices), None),
        "hold 50/50, monthly rebalance": (constant(prices, monthly=True), 0.0),
        "btc sma200 gate 50/50": (gate(prices, span=200, ma="sma"), None),
        "each coin own sma200": (gate(prices, span=200, ma="sma", each=True), None),
        "each coin own ema100": (gate(prices, each=True), None),
        "each coin 90d momentum": (ts_momentum(prices), None),
        "dual momentum 90d, monthly": (dual_momentum(prices), None),
        "vol target 40%, 50/50": (vol_target(prices, constant(prices), 0.40), 0.10),
        "vol target 60%, 50/50": (vol_target(prices, constant(prices), 0.60), 0.10),
        "base + vol target 40%": (vol_target(prices, base, 0.40), 0.10),
        "base + vol target 60%": (vol_target(prices, base, 0.60), 0.10),
    }


def run_bench(prices) -> pd.DataFrame:
    rows = []
    for name, (w, thr) in benchmarks(prices).items():
        nav, trades = simulate(w, prices, threshold=thr)
        rows.append(summary(name, nav, trades))
    return pd.DataFrame(rows).set_index("run")


def run_yield(prices) -> pd.DataFrame:
    rows = []
    bench = benchmarks(prices)
    for y in (0.0, 0.03, 0.05):
        for name in (BASE, HOLD, "btc sma200 gate 50/50", "dual momentum 90d, monthly"):
            w, thr = bench[name]
            nav, trades = simulate(w, prices, cash_yield=y, threshold=thr)
            rows.append(summary(f"{name} @ {y:.0%}", nav, trades, cash_yield=y))
    return pd.DataFrame(rows).set_index("run")


def run_volscale(prices) -> pd.DataFrame:
    base = gate(prices)
    rows = [summary("base", *simulate(base, prices))]
    for target in (0.4, 0.6, 0.8, 1.0):
        for coins, label in ((("eth",), "eth only"), (("eth", "btc"), "both coins")):
            nav, trades = simulate(vol_scale_each(prices, base, target, coins), prices, threshold=0.10)
            rows.append(summary(f"vol cap {target:.0%}, {label}", nav, trades))
    return pd.DataFrame(rows).set_index("run")


def stationary_indices(n: int, mean_block: int, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap: blocks of geometric length, wrapping around."""
    out = np.empty(n, dtype=int)
    i = 0
    while i < n:
        start, length = rng.integers(n), rng.geometric(1 / mean_block)
        take = min(length, n - i)
        out[i:i + take] = (start + np.arange(take)) % n
        i += take
    return out


def run_bootstrap(prices, reps=2000, seed=11) -> pd.DataFrame:
    """Resample the same days for both, so the comparison stays paired. In-sample daily returns only."""
    bench = benchmarks(prices)
    navs = {}
    for name in (BASE, HOLD):
        w, thr = bench[name]
        nav, _ = simulate(w, prices, threshold=thr)
        navs[name] = nav[nav.index < IN_SAMPLE[1]]
    daily = pd.DataFrame(navs)
    daily = daily[daily.index.hour == 0].pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    n = len(daily)

    def measures(r):
        path = np.cumprod(1 + r, axis=0)
        annual = path[-1] ** (365.25 / n) - 1
        dd = (path / np.maximum.accumulate(path, axis=0) - 1).min(axis=0)
        return annual, dd

    rows = []
    for block in (20, 60, 120):
        diffs = []
        for _ in range(reps):
            annual, dd = measures(daily[stationary_indices(n, block, rng)])
            diffs.append((annual[0] - annual[1], dd[0] - dd[1], annual[0] / -dd[0] - annual[1] / -dd[1]))
        d = np.array(diffs)
        for k, label in enumerate(("annual return diff", "maxDD diff", "calmar diff")):
            q = np.quantile(d[:, k], [0.05, 0.25, 0.5, 0.75, 0.95])
            rows.append({"block days": block, "measure": label, "p5": q[0], "p25": q[1], "median": q[2], "p75": q[3],
                         "p95": q[4], "P(base better)": float((d[:, k] > 0).mean())})
    return pd.DataFrame(rows)


def load_minute_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Minute ETH and BTC prices from the closeTick column of the raw files, forward filled over minutes without
    trades and shifted one minute, which is how Demeter builds its price. Checked against the hourly cache, whose
    price is the first minute of each hour. Reading two columns keeps this small enough for the 7 GB backtest host.
    """
    cache = f"{RESULT_DIR}/prices_minute_{END}.parquet"
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    ticks = {}
    for name, pool in (("eth", ETH_POOL), ("ratio", RATIO_POOL)):
        files = sorted(glob.glob(f"../real-data/{pool}/ethereum-{pool}-*.minute.csv"))
        frames = [pd.read_csv(f, usecols=["timestamp", "closeTick"], parse_dates=["timestamp"]) for f in files]
        ticks[name] = pd.concat(frames).drop_duplicates("timestamp").set_index("timestamp")["closeTick"]
    index = pd.date_range(f"{DATA_START} 00:00", f"{END} 23:59", freq="1min")
    tick = pd.DataFrame({k: v.reindex(index.union(v.index)).ffill().reindex(index) for k, v in ticks.items()})
    eth = 1e12 / 1.0001 ** tick["eth"]  # USDC (6 decimals) is token0, WETH (18) token1
    frame = pd.DataFrame({"eth": eth, "btc": eth * 1.0001 ** tick["ratio"] / 1e10})  # WBTC (8) token0, WETH token1
    frame = frame.shift(1).dropna()  # Demeter's price at minute t is the close of minute t-1
    check = (frame.reindex(prices.index) / prices - 1).abs().max()
    print(f"minute vs hourly cache at the top of each hour, max relative gap: eth {check['eth']:.2e}, btc {check['btc']:.2e}")
    frame.to_parquet(cache)
    return frame


def run_minute(prices) -> pd.DataFrame:
    """The same decisions replayed on minute prices: intraday moves the hourly bars smooth out."""
    minute = load_minute_prices(prices)
    base = gate(prices)
    rules = {
        BASE: (base, None),
        "btc ema100 gate, eth 30%": (gate(prices, eth=0.3), None),
        "base + vol cap 40%, both coins": (vol_scale_each(prices, base, 0.4), 0.10),
        "btc sma200 gate 50/50": (gate(prices, span=200, ma="sma"), None),
        "each coin own sma200": (gate(prices, span=200, ma="sma", each=True), None),
        HOLD: (constant(prices), None),
        "hold btc": (constant(prices, eth=0.0, btc=1.0), None),
    }
    rows = []
    for name, (w, thr) in rules.items():
        for bar, p in (("1h", prices), ("1min", minute)):
            nav, trades = simulate(w, p, threshold=thr)
            rows.append(summary(f"{name} [{bar}]", nav, trades, bar=bar))
    return pd.DataFrame(rows).set_index("run")


PCT = {"2022", "2023", "2024", "2025", "total", "annual", "maxDD", "drop window", "2026", "2026 maxDD"}
MAIN = ["2022", "2023", "2024", "2025", "total", "maxDD", "calmar", "drop window", "2026", "2026 maxDD", "trades"]


def show(frame: pd.DataFrame, cols=None) -> str:
    shown = frame[cols].copy() if cols else frame.copy()
    for c in shown.columns:
        if c in PCT:
            shown[c] = shown[c].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    return shown.round(2).to_string()


def pivot(table: pd.DataFrame, value: str) -> str:
    return table.pivot(index="span", columns="eth", values=value).map(lambda v: f"{v:+.0%}").to_string()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    names = ("hours", "plateau", "yield", "bench", "volscale", "bootstrap")
    for flag in names + ("minute",):
        parser.add_argument(f"--{flag}", action="store_true")
    cli = vars(parser.parse_args())
    todo = [n for n in names + ("minute",) if cli[n]] or list(names)
    prices, _, _ = load_prices()
    pd.set_option("display.width", 250)

    if "hours" in todo:
        table = run_hours(prices)
        table.to_csv(f"{RESULT_DIR}/robust_hours.csv")
        print("\n== close hour and execution lag ==")
        print(show(table, MAIN))
    if "plateau" in todo:
        table = run_plateau(prices)
        table.to_csv(f"{RESULT_DIR}/robust_plateau.csv")
        print("\n== plateau: in-sample total, EMA span (rows) x ETH share (columns) ==")
        print(pivot(table, "total"))
        print("\n== plateau: in-sample maxDD ==")
        print(pivot(table, "maxDD"))
        print("\n== plateau: 2026 (looked at before, not for choosing) ==")
        print(pivot(table, "2026"))
    if "bench" in todo:
        table = run_bench(prices)
        table.to_csv(f"{RESULT_DIR}/robust_bench.csv")
        print("\n== benchmarks ==")
        print(show(table, MAIN))
    if "yield" in todo:
        table = run_yield(prices)
        table.to_csv(f"{RESULT_DIR}/robust_yield.csv")
        print("\n== idle USDC yield ==")
        print(show(table, MAIN))
    if "volscale" in todo:
        table = run_volscale(prices)
        table.to_csv(f"{RESULT_DIR}/robust_volscale.csv")
        print("\n== volatility cap per coin ==")
        print(show(table, MAIN))
    if "bootstrap" in todo:
        table = run_bootstrap(prices)
        table.to_csv(f"{RESULT_DIR}/robust_bootstrap.csv", index=False)
        print("\n== paired stationary bootstrap, base minus hold 50/50, 2022-2025 daily ==")
        shown = table.copy()
        for c in ("p5", "p25", "median", "p75", "p95"):
            shown[c] = [f"{v:+.2f}" if m == "calmar diff" else f"{v:+.1%}" for v, m in zip(shown[c], shown["measure"])]
        print(shown.to_string(index=False))
    if "minute" in todo:
        table = run_minute(prices)
        table.to_csv(f"{RESULT_DIR}/robust_minute.csv")
        print("\n== hourly vs minute bars ==")
        print(show(table, MAIN))
    print("ROBUST_DONE")
