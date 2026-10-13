"""
Stand-alone scorecard for each of defense v1 / v2 / v3: the strategy judged against zero and against its own
variants (decision hour, start date, parameters, price paths, costs), no other strategy as benchmark.

    python scorecard_v123.py [out_dir]

Reads the T2 / T8b / T9 tables written by validate_v123.py (same out_dir) and computes the rest on the daily spec
simulator. Windows: spec 2021-05-05..2026-08-31 (primary, the simulator matches the spec there) and full
2018-01-01..2026-08-31 (includes the simulator's 2018, which is 26 % below the spec).
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.stats import norm

import spec_daily_sim as S
import validate_v123 as V

OUT = V.OUT
WINDOWS = {"spec": V.SPEC, "full": V.FULL}
T10 = {"v1": (196.8, -0.227), "v2": (181.1, -0.247), "v3": (224.9, -0.177)}  # Demeter 0x88e6, UTC 0, $k / max DD
EULER = 0.5772156649


def own_grid(version: str) -> tuple[dict, str, list]:
    """The version's own parameter neighbourhood: (configs, chosen key, neighbour keys)."""
    if version == "v1":
        g = {}
        for m in np.round(np.arange(0.6, 1.41, 0.1), 1):
            g[f"x{m:.1f}"] = replace(S.V1, name=f"v1 x{m:.1f}", refill=tuple(round(1 + s * m, 5) for s in V.BASE_STEPS))
        return g, "x1.0", ["x0.9", "x1.1"]
    if version == "v2":
        g = {f"x{m:.1f}": V.ladder_cfg(m) for m in np.round(np.arange(1.0, 2.21, 0.1), 1)}
        return g, "x1.5", ["x1.4", "x1.6"]
    g = {f"{on:.2f}": replace(S.V3, name=f"div {on:.2f}", div_on=on, div_off=0.20)
         for on in np.round(np.arange(0.20, 0.601, 0.05), 2)}
    return g, "0.40", ["0.35", "0.45"]


def hour_returns(cfg, window) -> pd.DataFrame:
    """Daily log returns per decision hour (columns 0..23)."""
    return pd.DataFrame({h: np.log(S.run(cfg, *window, hour=h).equity).diff() for h in V.HOURS}).dropna()


def sharpe_stats(r: pd.Series, n_trials: int, var_sr: float) -> dict:
    T, sr = len(r), r.mean() / r.std()
    g3, g4 = float(r.skew()), float(r.kurt() + 3)
    den = math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    sr0 = math.sqrt(var_sr) * ((1 - EULER) * norm.ppf(1 - 1 / n_trials) + EULER * norm.ppf(1 - 1 / (n_trials * math.e)))
    psr = norm.cdf(sr * math.sqrt(T - 1) / den)
    dsr = norm.cdf((sr - sr0) * math.sqrt(T - 1) / den)
    mintrl = 1 + (1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) * (norm.ppf(0.95) / sr) ** 2 if sr > 0 else float("inf")
    return {"sharpe_annual": round(sr * math.sqrt(365), 3), "psr_gt0": round(float(psr), 3),
            "dsr_N18": round(float(dsr), 3), "mintrl_years": round(mintrl / 365, 1)}


def card(version: str, wname: str, window, rng) -> dict:
    cfg = S.VERSIONS[version]
    years = (pd.Timestamp(window[1]) - pd.Timestamp(window[0])).days / 365.25
    R = hour_returns(cfg, window)
    term = {h: S.run(cfg, *window, hour=h) for h in V.HOURS}
    tv = pd.Series({h: r.terminal / 1e3 for h, r in term.items()})
    dd = pd.Series({h: r.maxdd for h, r in term.items()})
    cagr = lambda t: (t / 100) ** (1 / years) - 1
    # significance per decision hour (one deployment runs one hour; averaging hours would smooth the returns and
    # overstate the Sharpe), reported as the median over the 24 hours and at UTC 0
    g, chosen, nb = own_grid(version)
    G = pd.DataFrame({k: np.log(S.run(c, *window).equity).diff() for k, c in g.items()}).dropna()
    var_sr = float((G.mean() / G.std()).var())
    per_hour = []
    for h in V.HOURS:
        x = R[h].to_numpy()
        boot = V.stationary_boot_means(x, 20.0, 2000, rng)
        lo, hi = np.percentile(boot, [5, 95]) * 365
        st = sharpe_stats(R[h], 18, var_sr)
        per_hour.append({"lo": lo, "hi": hi, "p_gt0": 1 - float(((boot - x.mean()) >= x.mean()).mean()), **st})
    ph = pd.DataFrame(per_hour)
    gm = pd.Series({k: np.mean([S.run(c, *window, hour=h).terminal for h in V.HOURS]) / 1e3 for k, c in g.items()})
    # rolling one-year returns over every hour
    one_year = []
    for h, r in term.items():
        e = r.equity.to_numpy()
        one_year.append(e[365:] / e[:-365] - 1)
    one_year = np.concatenate(one_year)
    out = {
        "return": {
            "utc0_terminal_k": round(tv[0], 1), "mean24_terminal_k": round(tv.mean(), 1),
            "worst_hour_terminal_k": round(tv.min(), 1),
            "cagr_utc0": round(cagr(tv[0]), 4), "cagr_mean24": round(cagr(tv.mean()), 4),
            "ann_logret_ci90_utc0": [round(ph.lo[0], 4), round(ph.hi[0], 4)],
            "ann_logret_ci90_median_hour": [round(ph.lo.median(), 4), round(ph.hi.median(), 4)],
            "prob_return_gt0_utc0": round(ph.p_gt0[0], 3), "prob_return_gt0_median_hour": round(ph.p_gt0.median(), 3)},
        "sharpe": {"utc0": ph.drop(columns=["lo", "hi", "p_gt0"]).iloc[0].to_dict(),
                   "median_hour": ph.drop(columns=["lo", "hi", "p_gt0"]).median().round(3).to_dict()},
        "risk": {"maxdd_utc0": round(dd[0], 3), "maxdd_mean24": round(dd.mean(), 3), "maxdd_worst_hour": round(dd.min(), 3),
                 "prob_loss_1y": round(float((one_year < 0).mean()), 3),
                 "one_year_p5": round(float(np.percentile(one_year, 5)), 3)},
        "stability": {"utc0_vs_mean24": round(tv.mean() / tv[0] - 1, 3),
                      "plateau_neighbours": {n: round(gm[n] / gm[chosen] - 1, 3) for n in nb},
                      "plateau_pass": bool(all(abs(gm[n] / gm[chosen] - 1) <= 0.10 for n in nb)),
                      "grid_best": f"{gm.idxmax()} ({gm.max():.1f})"},
    }
    return out


def main():
    rng = np.random.default_rng(13)
    cards = {v: {w: card(v, w, win, rng) for w, win in WINDOWS.items()} for v in S.VERSIONS}
    # start dates (T2), price paths (T8b), costs (T9), real pool (T10)
    t2 = pd.read_csv(OUT / "t2_starts.csv")
    starts = t2.groupby(["start", "version"])["terminal"].mean().unstack()
    paths = pd.read_csv(OUT / "t8b_paths.csv")
    t9 = json.loads((OUT / "t9_summary.json").read_text())
    for v in S.VERSIONS:
        cards[v]["start_dates_3y"] = {"share_profitable": round(float((starts[v] > 100).mean()), 3),
                                      "median_terminal_k": round(float(starts[v].median()), 1),
                                      "worst_terminal_k": round(float(starts[v].min()), 1)}
        cards[v]["monte_carlo_8y"] = {"prob_loss": round(float((paths[v] < 100).mean()), 3),
                                      "median_terminal_k": round(float(paths[v].median()), 1),
                                      "terminal_p5_k": round(float(paths[v].quantile(0.05)), 1),
                                      "maxdd_median": round(float(paths[f"{v}_dd"].median()), 3),
                                      "maxdd_p5": round(float(paths[f"{v}_dd"].quantile(0.05)), 3)}
        cards[v]["cost_stress_mean24_k"] = {w: t9[w]["stressed"][v] for w in ("spec", "full")}
        cards[v]["real_pool_utc0"] = {"terminal_k": T10[v][0], "maxdd": T10[v][1]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scorecard.json").write_text(json.dumps(cards, indent=1, default=str))
    print(json.dumps(cards, default=str))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT = V.OUT = __import__("pathlib").Path(sys.argv[1])
    main()
