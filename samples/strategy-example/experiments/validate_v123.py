"""
Overfitting tests T1-T9 of VALIDATION-2026-10-13-defense-v1-v3.md on the daily spec simulator (spec_daily_sim.py).

    python validate_v123.py <test> [out_dir]     # test: t1 t2 t3 t4 t5 t6 t7 t8a t8b t9 all

Tables go to out_dir (default: the main checkout's result/validate_v123/), one CSV per test, plus a summary line each.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import spec_daily_sim as S

FULL = ("2018-01-01", "2026-08-31")
SPEC = ("2021-05-05", "2026-08-31")
PRE = ("2018-01-01", "2021-05-04")
PAIRS = [("v2", "v1"), ("v3", "v2"), ("v3", "v1")]
HOURS = range(24)
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/Users/dinohuang/Desktop/demeter-momentum/samples/"
                                                        "strategy-example/result/validate_v123")
SUMMARY = {}


def save(df: pd.DataFrame, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{name}.csv")


def hour_table(cfgs: dict, window, **kw) -> pd.DataFrame:
    rows = []
    for h in HOURS:
        for name, cfg in cfgs.items():
            r = S.run(cfg, *window, hour=h, **kw)
            rows.append({"hour": h, "version": name, "terminal": r.terminal / 1e3, "maxdd": r.maxdd})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- T1 decision hour
def t1():
    out = {}
    for wname, w in (("full", FULL), ("spec", SPEC)):
        t = hour_table(S.VERSIONS, w)
        save(t, f"t1_hours_{wname}")
        piv = t.pivot(index="hour", columns="version", values="terminal")
        dd = t.pivot(index="hour", columns="version", values="maxdd")
        res = {"utc0": piv.loc[0].round(1).to_dict(), "mean": piv.mean().round(1).to_dict(),
               "median": piv.median().round(1).to_dict(), "worst": piv.min().round(1).to_dict(),
               "maxdd_mean": dd.mean().round(3).to_dict(), "maxdd_worst": dd.min().round(3).to_dict(),
               "utc0_rank_of_24": {v: int((piv[v] > piv.loc[0, v]).sum() + 1) for v in piv}}
        for a, b in PAIRS:
            wins = int((piv[a] > piv[b]).sum())
            res[f"{a}>{b}"] = {"hours_won": wins, "mean_diff": round(piv[a].mean() - piv[b].mean(), 1),
                               "pass": bool(wins >= 18 and piv[a].mean() > piv[b].mean())}
        out[wname] = res
    SUMMARY["t1"] = out


# ---------------------------------------------------------------- T2 start date
def t2():
    starts = pd.date_range("2018-01-01", "2023-08-01", freq="MS")
    rows = []
    for s in starts:
        e = s + pd.DateOffset(years=3) - pd.Timedelta(days=1)
        for h in HOURS:
            for name, cfg in S.VERSIONS.items():
                r = S.run(cfg, s, e, hour=h)
                rows.append({"start": s.date(), "hour": h, "version": name, "terminal": r.terminal / 1e3,
                             "maxdd": r.maxdd})
    t = pd.DataFrame(rows)
    save(t, "t2_starts")
    m = t.groupby(["start", "version"])["terminal"].mean().unstack()
    d = t.groupby(["start", "version"])["maxdd"].mean().unstack()
    res = {}
    for a, b in PAIRS:
        diff = m[a] - m[b]
        share = float((diff > 0).mean())
        res[f"{a}>{b}"] = {"share_of_starts": round(share, 3), "median_diff": round(float(diff.median()), 1),
                           "worst_diff": round(float(diff.min()), 1),
                           "maxdd_better_share": round(float((d[a] > d[b]).mean()), 3),
                           "pass": bool(share >= 2 / 3 and diff.median() > 0)}
    SUMMARY["t2"] = res


# ---------------------------------------------------------------- T3 before 2021-05-05
def t3():
    t = hour_table(S.VERSIONS, PRE)
    save(t, "t3_pre2021")
    m = t.groupby("version")[["terminal", "maxdd"]].mean()
    res = {"mean": m.round(3).to_dict()}
    for a, b in PAIRS:
        res[f"{a}>{b}"] = {"terminal_diff": round(m.loc[a, "terminal"] - m.loc[b, "terminal"], 1),
                           "maxdd_diff": round(m.loc[a, "maxdd"] - m.loc[b, "maxdd"], 3),
                           "pass": bool(m.loc[a, "terminal"] >= m.loc[b, "terminal"]
                                        and m.loc[a, "maxdd"] >= m.loc[b, "maxdd"])}
    SUMMARY["t3"] = res


# ---------------------------------------------------------------- grids for T4 / T5
BASE_STEPS = (0.05, 0.08333, 0.11667, 0.15)  # v1 ladder; v2 = x1.5


def ladder_cfg(m: float) -> S.Config:
    return replace(S.V2, name=f"ladder x{m:.1f}", refill=tuple(round(1 + s * m, 5) for s in BASE_STEPS))


def grid() -> dict:
    g = {"v1": S.V1}
    for m in np.round(np.arange(1.0, 2.21, 0.1), 1):
        g[f"ladder x{m:.1f}"] = ladder_cfg(m)
    for on in np.round(np.arange(0.20, 0.601, 0.05), 2):
        g[f"div {on:.2f}/half"] = replace(S.V3, name=f"div {on:.2f}/half", div_on=on, div_off=on / 2)
        g[f"div {on:.2f}/0.20"] = replace(S.V3, name=f"div {on:.2f}/0.20", div_on=on, div_off=0.20)
    return g


def plateau(series: pd.Series, chosen: str, neighbours: list) -> dict:
    c = series[chosen]
    nb = {n: round(series[n] / c - 1, 3) for n in neighbours if n in series}
    others = series.drop(chosen)
    return {"chosen": round(c, 1), "neighbours_rel": nb, "grid_max": series.idxmax(),
            "grid_max_value": round(series.max(), 1),
            "pass": bool(all(abs(v) <= 0.10 for v in nb.values()) and not (c > others.max() * 1.10))}


def t4():
    g = grid()
    res = {}
    for wname, w in (("full", FULL), ("spec", SPEC)):
        t = hour_table(g, w)
        save(t, f"t4_grid_{wname}")
        m = t.groupby("version")["terminal"].mean()
        dd = t.groupby("version")["maxdd"].mean()
        lad = m[[k for k in m.index if k.startswith("ladder")]]
        half = m[[k for k in m.index if k.endswith("/half")]]
        fixed = m[[k for k in m.index if k.endswith("/0.20")]]
        res[wname] = {
            "ladder": plateau(lad, "ladder x1.5", ["ladder x1.4", "ladder x1.6"]),
            "ladder_values": lad.round(1).to_dict(),
            "div_half": plateau(half, "div 0.40/half", ["div 0.35/half", "div 0.45/half"]),
            "div_half_values": half.round(1).to_dict(),
            "div_fixed": plateau(fixed, "div 0.40/0.20", ["div 0.35/0.20", "div 0.45/0.20"]),
            "div_fixed_values": fixed.round(1).to_dict(),
            "maxdd": dd.round(3).to_dict(),
            "v1": round(m["v1"], 1),
        }
    SUMMARY["t4"] = res


# ---------------------------------------------------------------- T5 PBO / CSCV
def daily_returns(cfgs: dict, window, hour=0, **kw) -> pd.DataFrame:
    return pd.DataFrame({n: np.log(S.run(c, *window, hour=hour, **kw).equity).diff().dropna()
                         for n, c in cfgs.items()})


def pbo(R: pd.DataFrame, S_: int = 16) -> dict:
    T = len(R) // S_ * S_
    X = R.iloc[:T].to_numpy()
    blocks = np.array_split(np.arange(T), S_)
    logits, deg = [], []
    for comb in itertools.combinations(range(S_), S_ // 2):
        is_idx = np.concatenate([blocks[i] for i in comb])
        oos_idx = np.concatenate([blocks[i] for i in range(S_) if i not in comb])
        sr_is = X[is_idx].mean(0) / X[is_idx].std(0)
        sr_oos = X[oos_idx].mean(0) / X[oos_idx].std(0)
        best = int(np.argmax(sr_is))
        rank = (sr_oos < sr_oos[best]).sum() + 0.5 * ((sr_oos == sr_oos[best]).sum() - 1)
        w = (rank + 1) / (X.shape[1] + 1)
        logits.append(math.log(w / (1 - w)))
        deg.append(sr_oos[best] - np.median(sr_oos))
    logits = np.array(logits)
    return {"pbo": round(float((logits <= 0).mean()), 3), "n_configs": X.shape[1], "n_splits": len(logits),
            "median_oos_minus_median": round(float(np.median(deg)) * math.sqrt(365), 3)}


def t5():
    R = daily_returns(grid(), FULL)
    save(R, "t5_returns_utc0")
    res = {"all": pbo(R)}
    sr = (R.mean() / R.std() * math.sqrt(365)).sort_values(ascending=False)
    res["sharpe_top5"] = sr.head(5).round(3).to_dict()
    res["sharpe_v1_v2_v3"] = sr[["v1", "ladder x1.5", "div 0.40/0.20"]].round(3).to_dict()
    res["pass"] = bool(res["all"]["pbo"] <= 0.25)
    SUMMARY["t5"] = res


# ---------------------------------------------------------------- T6 deflated Sharpe
def dsr(r: pd.Series, n_trials: int, var_sr: float) -> dict:
    T, sr = len(r), r.mean() / r.std()
    g3, g4 = float(r.skew()), float(r.kurt() + 3)
    e = 0.5772156649
    sr0 = math.sqrt(var_sr) * ((1 - e) * norm.ppf(1 - 1 / n_trials) + e * norm.ppf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    psr0 = (sr) * math.sqrt(T - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return {"sr_annual": round(sr * math.sqrt(365), 3), "sr0_annual": round(sr0 * math.sqrt(365), 3),
            "psr_vs_0": round(float(norm.cdf(psr0)), 4), "dsr": round(float(norm.cdf(z)), 4), "T": T,
            "N": n_trials, "pass": bool(norm.cdf(z) >= 0.95)}


def t6():
    path = OUT / "t5_returns_utc0.csv"
    R = pd.read_csv(path, index_col=0) if path.exists() else daily_returns(grid(), FULL)
    var_sr = float((R.mean() / R.std()).var())
    res = {}
    for name, col in (("v2", "ladder x1.5"), ("v3", "div 0.40/0.20"), ("v1", "v1")):
        res[name] = {f"N={n}": dsr(R[col], n, var_sr) for n in (18, R.shape[1])}
    SUMMARY["t6"] = res


# ---------------------------------------------------------------- T7 paired stationary bootstrap
def stationary_index(n: int, block: float, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap indices: a new random start with probability 1/block, else the next day."""
    new = rng.random(n) < 1 / block
    new[0] = True
    starts = rng.integers(n, size=n)
    ar = np.arange(n)
    last = np.maximum.accumulate(np.where(new, ar, 0))
    return (starts[last] + ar - last) % n


def stationary_boot_means(x: np.ndarray, block: float, draws: int, rng) -> np.ndarray:
    return np.array([x[stationary_index(len(x), block, rng)].mean() for _ in range(draws)])


def boot_p(x: np.ndarray, rng, draws=10_000, block=20.0) -> dict:
    m = stationary_boot_means(x, block, draws, rng)
    p = float(((m - x.mean()) >= x.mean()).mean())
    lo, hi = np.percentile(m, [5, 95])
    return {"mean_daily_bp": round(x.mean() * 1e4, 3), "annual_pts": round(x.mean() * 365 * 100, 2),
            "ci90_annual_pts": [round(lo * 365 * 100, 2), round(hi * 365 * 100, 2)], "p_one_sided": round(p, 4)}


def t7():
    rng = np.random.default_rng(7)
    rets = {h: daily_returns(S.VERSIONS, FULL, hour=h) for h in HOURS}
    res = {}
    for a, b in PAIRS:
        d0 = (rets[0][a] - rets[0][b]).to_numpy()
        davg = pd.concat([rets[h][a] - rets[h][b] for h in HOURS], axis=1).mean(1).to_numpy()
        r0, ravg = boot_p(d0, rng), boot_p(davg, rng)
        res[f"{a}-{b}"] = {"utc0": r0, "avg24": ravg,
                           "pass": bool(r0["p_one_sided"] <= 0.05 and ravg["p_one_sided"] <= 0.05)}
    SUMMARY["t7"] = res


# ---------------------------------------------------------------- T8a random-timing null for v3's rule
def episodes(flag: np.ndarray) -> list:
    eps, start = [], None
    for i, f in enumerate(flag):
        if f and start is None:
            start = i
        if not f and start is not None:
            eps.append((start, i - start))
            start = None
    if start is not None:
        eps.append((start, len(flag) - start))
    return eps


def t8a(n=1000):
    rng = np.random.default_rng(8)
    res = {}
    for wname, w in (("full", FULL), ("spec", SPEC)):
        sig3 = S.signal_cached(S.V3, 0).loc[w[0]:w[1]]
        F = S.signal_cached(S.V2, 0).loc[w[0]:w[1], "Fp"]
        eps = episodes(sig3["diverged"].to_numpy())
        durs = [d for _, d in eps]
        v3 = S.run(S.V2, *w, fp=sig3["Fp"])  # v2 engine with v3's F': identical to v3
        v2 = S.run(S.V2, *w)
        rows = []
        L = len(F)
        for _ in range(n):
            mask = np.zeros(L, dtype=bool)
            for d in durs:
                for _try in range(1000):
                    s0 = int(rng.integers(0, L - d))
                    if not mask[max(0, s0 - 1):s0 + d + 1].any():
                        mask[s0:s0 + d] = True
                        break
            fp = F.where(~mask, 0.0)
            r = S.run(S.V2, *w, fp=fp)
            rows.append({"terminal": r.terminal / 1e3, "maxdd": r.maxdd})
        t = pd.DataFrame(rows)
        save(t, f"t8a_random_timing_{wname}")
        res[wname] = {"episodes": [(str(F.index[s].date()), d) for s, d in eps],
                      "v3_terminal": round(v3.terminal / 1e3, 1), "v3_maxdd": round(v3.maxdd, 3),
                      "v2_terminal": round(v2.terminal / 1e3, 1), "v2_maxdd": round(v2.maxdd, 3),
                      "random_terminal_median": round(t.terminal.median(), 1),
                      "random_maxdd_median": round(t.maxdd.median(), 3),
                      "v3_terminal_pct_rank": round(float((t.terminal < v3.terminal / 1e3).mean()), 3),
                      "v3_maxdd_pct_rank": round(float((t.maxdd < v3.maxdd).mean()), 3)}
        res[wname]["pass"] = bool(res[wname]["v3_terminal_pct_rank"] >= 0.95 or res[wname]["v3_maxdd_pct_rank"] >= 0.95)
    SUMMARY["t8a"] = res


# ---------------------------------------------------------------- T8b block-bootstrap price paths
def t8b(n=1000, block=90.0):
    rng = np.random.default_rng(9)
    close = S.daily_closes(0).loc[:"2026-08-31"]
    lr = np.log(close).diff().dropna().to_numpy()
    L = len(lr)
    kmean = S.reward_coefficients()["mean"]
    k = {"mean": kmean}
    idx_dates = close.index
    warm = 365  # first year only warms the EMAs and accounts
    rows = []
    for j in range(n):
        idx = stationary_index(L, block, rng)
        path = pd.Series(close.iloc[0] * np.exp(np.concatenate([[0], np.cumsum(lr[idx])])), index=idx_dates)
        row = {"path": j, "eth_hold": path.iloc[-1] / path.iloc[warm]}
        for name, cfg in S.VERSIONS.items():
            r = S.run(cfg, idx_dates[warm], idx_dates[-1], closes=path, k=k)
            row[name] = r.terminal / 1e3
            row[f"{name}_dd"] = r.maxdd
        rows.append(row)
    t = pd.DataFrame(rows)
    save(t, "t8b_paths")
    res = {"n": n, "years": round((L - warm) / 365, 1),
           "median_terminal": {v: round(float(t[v].median()), 1) for v in S.VERSIONS},
           "median_maxdd": {v: round(float(t[f"{v}_dd"].median()), 3) for v in S.VERSIONS}}
    for a, b in PAIRS:
        share = float((t[a] > t[b]).mean())
        res[f"{a}>{b}"] = {"share_paths": round(share, 3),
                           "share_dd_better": round(float((t[f"{a}_dd"] > t[f"{b}_dd"]).mean()), 3),
                           "pass": bool(share >= 2 / 3)}
    SUMMARY["t8b"] = res


# ---------------------------------------------------------------- T9 cost stress
def t9():
    res = {}
    stressed = {n: replace(c, reward_mult=0.8, swap_cost=0.002) for n, c in S.VERSIONS.items()}
    for wname, w in (("full", FULL), ("spec", SPEC)):
        base = hour_table(S.VERSIONS, w).groupby("version")["terminal"].mean()
        st = hour_table(stressed, w).groupby("version")["terminal"].mean()
        res[wname] = {"base": base.round(1).to_dict(), "stressed": st.round(1).to_dict()}
        for a, b in PAIRS:
            res[wname][f"{a}>{b}"] = {"base_diff": round(base[a] - base[b], 1), "stressed_diff": round(st[a] - st[b], 1),
                                      "pass": bool(np.sign(base[a] - base[b]) == np.sign(st[a] - st[b]))}
    SUMMARY["t9"] = res


TESTS = {"t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5, "t6": t6, "t7": t7, "t8a": t8a, "t8b": t8b, "t9": t9}

if __name__ == "__main__":
    which = list(TESTS) if sys.argv[1] == "all" else sys.argv[1].split(",")
    for name in which:
        TESTS[name]()
        print(json.dumps({name: SUMMARY[name]}, default=str))
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{name}_summary.json").write_text(json.dumps(SUMMARY[name], indent=1, default=str))
