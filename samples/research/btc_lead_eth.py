"""
Does BTC lead ETH? Lead-lag study on Uniswap v3 minute data.

Pools (read from samples/real-data/<address>/):
  ETH  : 0x88e6... USDC/WETH 0.05% (token0 USDC 6, token1 WETH 18) -> log ETH/USD = -tick * ln(1.0001) + c
  BTC  : 0x5653... WBTC/USDT 0.05% (token0 WBTC 8, token1 USDT 6)  -> log BTC/USD = +tick * ln(1.0001) + c
  RATIO: 0x4585... WBTC/WETH 0.05% (token0 WBTC 8, token1 WETH 18) -> log WETH per WBTC = +tick * ln(1.0001) + c

Only log returns are used, so the decimal constants cancel out.

Run from samples/research:  python btc_lead_eth.py
"""
import glob
import os

import numpy as np
import pandas as pd

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "real-data")
LN_TICK = np.log(1.0001)
POOLS = {
    "ETH": ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", -1),
    "BTC": ("0x56534741CD8B152df6d48AdF7ac51f75169A83b2", 1),
    "RATIO": ("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 1),
}
LOAD_START, START, END = "2023-06-01", "2024-01-01", "2025-12-31"  # extra months only warm up the daily EMA
BPS = 1e4


def load(address: str, start: str, end: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(BASE, address, "*.minute.csv")))
    files = [f for f in files if start <= f[-21:-11] <= end]  # name ends with YYYY-MM-DD.minute.csv
    # amounts can exceed int64 (18-decimal tokens), float is enough to tell whether a swap happened
    df = pd.concat(pd.read_csv(f, usecols=["timestamp", "closeTick", "inAmount0", "inAmount1"],
                               dtype={"inAmount0": float, "inAmount1": float}) for f in files)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.drop_duplicates("timestamp", keep="last").set_index("timestamp").sort_index()


def ols(y: np.ndarray, x: np.ndarray):
    """OLS with constant. Returns coefficients, t-stats, R^2 (plain homoskedastic errors)."""
    X = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma2 = resid @ resid / (len(y) - X.shape[1])
    t = beta / np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    return beta, t, r2


def section(title: str):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


# ---------------------------------------------------------------- load
raw = {k: load(addr, LOAD_START, END) for k, (addr, _) in POOLS.items()}
grid = pd.date_range(LOAD_START, pd.Timestamp(END) + pd.Timedelta("23:59:00"), freq="min")
logp = pd.DataFrame({k: (sign * raw[k]["closeTick"] * LN_TICK).reindex(grid).ffill() for k, (_, sign) in POOLS.items()})
traded = pd.DataFrame({k: ((raw[k]["inAmount0"] > 0) | (raw[k]["inAmount1"] > 0)).reindex(grid, fill_value=False)
                       for k in POOLS})
full = logp  # includes warm-up, for the daily section
logp, traded = logp.loc[START:], traded.loc[START:]

# ---------------------------------------------------------------- 0. data health
section("0. Data health (2024-01-01 ~ 2025-12-31)")
days = pd.date_range(START, END, freq="D")
for k in POOLS:
    have = set(raw[k].loc[START:].index.normalize().unique())
    missing = [d.date().isoformat() for d in days if d not in have]
    t = traded[k]
    gaps = t[t].index.to_series().diff().dt.total_seconds().div(60).dropna()
    print(f"{k:6s} minutes with a swap: {t.mean():6.1%} | gap between swaps (min): median {gaps.median():.0f}, "
          f"p95 {gaps.quantile(.95):.0f}, max {gaps.max():.0f} | missing days: {len(missing)} {missing[:5]}")

# ---------------------------------------------------------------- 1. cross correlation
section("1. Lead-lag correlation of non-overlapping returns (lag = 1 bar)\n"
        "   BTC->ETH: corr(BTC ret in bar t, ETH ret in bar t+1)   ETH->BTC: the reverse   same: same bar\n"
        "   |corr| > sig is roughly significant at 95% (2/sqrt(N)).  pred: t-stat of lagged BTC in\n"
        "   ETH(t+1) ~ ETH(t) + BTC(t), i.e. does BTC add information beyond ETH's own last move")
print(f"{'bar':>6s} {'period':>9s} {'N':>8s} {'same':>7s} {'BTC->ETH':>9s} {'ETH->BTC':>9s} {'sig':>6s} {'pred t':>7s}")
for bar in ["1min", "5min", "15min", "60min", "240min", "1440min"]:
    for label, lo, hi in [("2024-25", START, END), ("2024", "2024-01-01", "2024-12-31"), ("2025", "2025-01-01", END)]:
        r = logp.loc[lo:hi, ["ETH", "BTC"]].resample(bar).last().diff().dropna()
        r = r[(r != 0).any(axis=1)]  # bars where neither pool moved carry no information
        e, b = r["ETH"].values, r["BTC"].values
        same = np.corrcoef(e, b)[0, 1]
        b2e = np.corrcoef(b[:-1], e[1:])[0, 1]
        e2b = np.corrcoef(e[:-1], b[1:])[0, 1]
        _, t, _ = ols(e[1:], np.column_stack([e[:-1], b[:-1]]))
        print(f"{bar:>6s} {label:>9s} {len(r):8d} {same:7.3f} {b2e:9.3f} {e2b:9.3f} {2 / np.sqrt(len(r)):6.3f} {t[2]:7.1f}")

# ---------------------------------------------------------------- 2. event study
section("2. Event study: BTC moves more than X within 15 min -> what does ETH do next?\n"
        "   Returns are signed by BTC's direction (+ = ETH follows BTC). Events at least 60 min apart.\n"
        "   ETH same = ETH move in the same 15 min.  'lagging' = ETH moved less than half of BTC in that window")
r15 = logp - logp.shift(15)
fwd = {h: logp["ETH"].shift(-h) - logp["ETH"] for h in (15, 60, 240)}
print(f"{'X':>5s} {'subset':>9s} {'N':>5s} {'BTC mv':>7s} {'ETH same':>9s} "
      + " ".join(f"{'ETH +' + str(h) + 'm':>10s} {'hit':>5s} {'t':>5s}" for h in fwd))
for x in (0.0075, 0.01, 0.015, 0.02):
    cand = r15["BTC"][r15["BTC"].abs() > x]
    events, last = [], None
    for ts in cand.index:
        if last is None or ts - last >= pd.Timedelta("60min"):
            events.append(ts)
            last = ts
    ev = pd.DataFrame(index=pd.DatetimeIndex(events))
    ev["sign"] = np.sign(r15["BTC"].loc[ev.index])
    ev["btc"] = r15["BTC"].loc[ev.index] * ev["sign"]
    ev["eth_same"] = r15["ETH"].loc[ev.index] * ev["sign"]
    for h, s in fwd.items():
        ev[f"f{h}"] = s.loc[ev.index] * ev["sign"]
    ev = ev.dropna()
    for subset, sub in [("all", ev), ("lagging", ev[ev["eth_same"] < 0.5 * ev["btc"]])]:
        if len(sub) < 5:
            continue
        cells = []
        for h in fwd:
            v = sub[f"f{h}"]
            cells.append(f"{v.mean() * BPS:9.1f}b {(v > 0).mean():5.0%} {v.mean() / v.std() * np.sqrt(len(v)):5.1f}")
        print(f"{x:5.2%} {subset:>9s} {len(sub):5d} {sub['btc'].mean() * BPS:6.0f}b {sub['eth_same'].mean() * BPS:8.0f}b "
              + " ".join(cells))

# ---------------------------------------------------------------- 3. volatility spillover
section("3. Volatility spillover (hourly realised vol from 1-min returns)\n"
        "   log RV_ETH(next) ~ log RV_ETH(now) [+ log RV_BTC(now)] : does BTC vol add forecasting power?")
r1 = logp[["ETH", "BTC"]].diff()
for horizon in ("60min", "240min"):
    rv = np.sqrt((r1 ** 2).resample(horizon).sum())
    rv = rv[(rv > 0).all(axis=1)]
    lrv = np.log(rv)
    y, e_now, b_now = lrv["ETH"].values[1:], lrv["ETH"].values[:-1], lrv["BTC"].values[:-1]
    _, _, r2_own = ols(y, e_now[:, None])
    beta, t, r2_both = ols(y, np.column_stack([e_now, b_now]))
    print(f"{horizon:>7s}: N={len(y)}  R^2 ETH only {r2_own:.3f} -> with BTC {r2_both:.3f}  "
          f"(BTC coef {beta[2]:.3f}, t {t[2]:.1f}; ETH coef {beta[1]:.3f}, t {t[1]:.1f})")

print("\n   LP-relevant: chance ETH's price leaves a +/-X band in the next 4h, by what happened in the last hour.\n"
      "   'BTC spike' = BTC 1h vol > 2x its trailing 24h median; 'ETH calm' = ETH 1h vol < 1.5x its own median")
rv1 = np.sqrt((r1 ** 2).resample("60min").sum())
ratio = rv1 / rv1.rolling(24).median().shift(1)
eth_h = logp["ETH"].resample("60min").last()
path = pd.concat([eth_h.shift(-k) - eth_h for k in range(1, 5)], axis=1)
excursion = path.abs().max(axis=1)
df = pd.DataFrame({"btc_x": ratio["BTC"], "eth_x": ratio["ETH"], "exc": excursion}).dropna()
groups = {
    "all hours": df,
    "BTC spike": df[df.btc_x > 2],
    "BTC spike & ETH calm": df[(df.btc_x > 2) & (df.eth_x < 1.5)],
    "ETH spike": df[df.eth_x > 2],
    "both calm": df[(df.btc_x < 1.5) & (df.eth_x < 1.5)],
}
print(f"   {'condition':<22s} {'N':>6s} {'median 4h move':>15s} {'P(>2%)':>7s} {'P(>3%)':>7s} {'P(>5%)':>7s}")
for name, g in groups.items():
    print(f"   {name:<22s} {len(g):6d} {g.exc.median() * 100:14.2f}% {(g.exc > .02).mean():7.1%} "
          f"{(g.exc > .03).mean():7.1%} {(g.exc > .05).mean():7.1%}")

# ---------------------------------------------------------------- 4. daily regime
section("4. Daily: BTC regime (close vs EMA100, judged on yesterday's close) and ETH's next day")
daily = full[["ETH", "BTC", "RATIO"]].resample("1D").last()
ema = np.exp(daily).ewm(span=100, adjust=False).mean()
above = (np.exp(daily) > ema).shift(1)  # known at today's 00:00
nxt = daily.diff()  # today's return, decided by yesterday's regime
d = pd.DataFrame({"btc_up": above["BTC"], "eth_up": above["ETH"], "eth_ret": nxt["ETH"]}).loc[START:END].dropna()
d = d.astype({"btc_up": bool, "eth_up": bool})
print(f"   {'regime':<28s} {'days':>5s} {'ETH mean/day':>13s} {'ETH vol/day':>12s} {'up days':>8s}")
for name, g in [("BTC above EMA", d[d.btc_up]), ("BTC below EMA", d[~d.btc_up]),
                ("ETH above EMA", d[d.eth_up]), ("ETH below EMA", d[~d.eth_up]),
                ("both above", d[d.btc_up & d.eth_up]), ("BTC above, ETH below", d[d.btc_up & ~d.eth_up]),
                ("BTC below, ETH above", d[~d.btc_up & d.eth_up]), ("both below", d[~d.btc_up & ~d.eth_up])]:
    print(f"   {name:<28s} {len(g):5d} {g.eth_ret.mean() * 100:12.2f}% {g.eth_ret.std() * 100:11.2f}% {(g.eth_ret > 0).mean():8.0%}")
dr = daily.diff().loc[START:END].dropna()
print(f"\n   corr(BTC ret day t, ETH ret day t+1) = {np.corrcoef(dr.BTC[:-1], dr.ETH[1:])[0, 1]:.3f}   "
      f"(N={len(dr) - 1}, sig ~{2 / np.sqrt(len(dr)):.3f})")
