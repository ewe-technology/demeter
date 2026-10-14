"""
Final scorecard of defense v1 / v2 / v3 (Dino, 2026-10-14): five generic methods, all computed from the method-1
Demeter backtests (Maker's maker-defense scripts), on mainnet `0x88e6` and Base `0xd0b5`, UTC 0. No cost overlay
(the cost and gas stress was dropped), no DSR / MinTRL.

    python scorecard_final_v123.py      # writes result/validate_v123/scorecard_final.json

Methods:
  1 real-data backtest   terminal, CAGR, max DD (largest % drop of the minute net value), fees, rebuilds
  2 parameter plateau    mainnet neighbours: profit change one step away (Demeter R3 runs)
  3 significance         daily log returns r_t = ln(V_t / V_t-1): Sharpe, PSR, 1 - p of a stationary bootstrap
  4 forward kill line    5th percentile of 90-day returns from stationary-bootstrapped daily returns
  5 Monte Carlo          1-year paths of stationary-bootstrapped daily returns: max DD and loss probability
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

import scorecard_demeter_v123 as C
import validate_v123 as V

POOLS = {"mainnet": "hour", "base": "base"}
BLOCK_SIG, BLOCK_MC = 20.0, 90.0
N_SIG, N_KILL, N_MC = 5000, 10_000, 10_000
HORIZON = 365


def daily(d) -> pd.Series:
    nv = pd.read_csv(next(d.glob("netvalue_*.csv")), index_col=0, parse_dates=True)["net_value"].astype(float)
    return nv.resample("1D").last().dropna()


def significance(r: pd.Series, rng) -> dict:
    x = r.to_numpy()
    T, mu, sd = len(x), x.mean(), x.std()
    sr = mu / sd
    g3, g4 = float(r.skew()), float(r.kurt() + 3)
    D = math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    boot = V.stationary_boot_means(x, BLOCK_SIG, N_SIG, rng)
    return {"T": T, "mean": mu, "std": sd, "sharpe_daily": sr, "sharpe_annual": sr * math.sqrt(365), "skew": g3,
            "kurt": g4, "D": D, "psr": float(norm.cdf(sr * math.sqrt(T - 1) / D)),
            "one_minus_p": 1 - float(((boot - mu) >= mu).mean())}


def kill_line(r: pd.Series, rng) -> float:
    x = r.to_numpy()
    sums = np.array([x[V.stationary_index(len(x), BLOCK_SIG, rng)[:90]].sum() for _ in range(N_KILL)])
    return float(np.exp(np.percentile(sums, 5)) - 1)


def monte_carlo(r: pd.Series, rng) -> dict:
    x = r.to_numpy()
    dd, term = np.empty(N_MC), np.empty(N_MC)
    for i in range(N_MC):
        path = np.exp(np.cumsum(x[V.stationary_index(len(x), BLOCK_MC, rng)[:HORIZON]]))
        path = np.concatenate([[1.0], path])
        dd[i] = (path / np.maximum.accumulate(path) - 1).min()
        term[i] = path[-1] - 1
    return {"maxdd_median": float(np.median(dd)), "maxdd_p5": float(np.percentile(dd, 5)),
            "ret_1y_median": float(np.median(term)), "ret_1y_p5": float(np.percentile(term, 5)),
            "p_loss_1y": float((term < 0).mean())}


def main():
    rng = np.random.default_rng(14)
    out = {}
    nb = {"v1": ("x0.9", "x1.1"), "v2": ("x1.4", "x1.6"), "v3": ("div0.35", "div0.45")}
    for v in ("v1", "v2", "v3"):
        out[v] = {}
        for pool, kind in POOLS.items():
            d = C.run_dir(v, kind, 0) if kind == "hour" else C.run_dir(v, kind)
            m1 = C.load(d, chain=pool, v=v)
            r = np.log(daily(d)).diff().dropna()
            out[v][pool] = {
                "m1": {k: m1[k] for k in ("terminal", "cagr", "maxdd", "fees", "rebuilds", "years")},
                "m3": significance(r, rng), "m4_kill_90d": kill_line(r, rng), "m5": monte_carlo(r, rng)}
        t0 = out[v]["mainnet"]["m1"]["terminal"]
        out[v]["m2_plateau"] = {x: (C.load(C.run_dir(v, "nb", x), v=v)["terminal"] - 100) / (t0 - 100) - 1 for x in nb[v]}
    path = C.ROOT / "scorecard_final.json"
    path.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, default=float))


if __name__ == "__main__":
    main()
