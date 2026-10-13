"""
Scorecards of defense v1 / v2 / v3 on Demeter runs (VALIDATION-2026-10-13-defense-v1-v3-demeter.md): methods A1-A6
(generic) and B1-B2 (specific to v1 / v2 / v3).

    python scorecard_demeter_v123.py          # after demeter_runs_v123.py

Reads result/validate_v123/demeter/<tag>/ (and t10/ for v2 / v3 at UTC 0 on mainnet), writes
result/validate_v123/scorecard_demeter.json. A6 and B2 run on the daily simulator and are labelled "model".
"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import spec_daily_sim as S
import validate_v123 as V

ROOT = Path("/Users/dinohuang/Desktop/demeter-momentum/samples/strategy-example/result/validate_v123")
SAMPLES = Path("/Users/dinohuang/Desktop/demeter-momentum/samples")
HOURS = (0, 4, 8, 12, 16, 20)
GAS_UNITS = (260_000, 450_000, 150_000)  # remove / add per band, swap (v6_validate.py:126)
BANDS = 16
EULER = 0.5772156649
N_TRIALS = 18 * len(HOURS)


def run_dir(v: str, kind: str, x=None) -> Path:
    if kind == "hour" and x == 0:
        d = ROOT / "demeter" / "R0-v1-h0" if v == "v1" else ROOT / "t10"
    elif kind == "hour":
        d = ROOT / "demeter" / f"R1-{v}-h{x}"
    elif kind == "base":
        d = ROOT / "demeter" / f"R2-{v}-base"
    else:
        d = ROOT / "demeter" / f"R3-{v}-{x}"
    hits = [Path(p) for p in glob.glob(str(d / f"gamma-maker-defense-ethusdc-{v}-*"))]
    assert len(hits) == 1, f"{d}: {hits}"
    return hits[0]


GAS = ETH = None


def gas_usd(events: pd.DataFrame) -> float:
    global GAS, ETH
    if GAS is None:
        GAS = pd.read_csv(SAMPLES / "gas_ethereum_hourly.csv", parse_dates=["timestamp"]).set_index("timestamp")["gwei"].sort_index()
        ETH = pd.read_csv(SAMPLES / "eth_usd_hourly.csv", parse_dates=["timestamp"]).set_index("timestamp")["usd"].sort_index()
    total = 0.0
    for _, e in events.iterrows():
        units = GAS_UNITS[2]
        if e.base_removed > 0 or e.quote_removed > 0:
            units += BANDS * GAS_UNITS[0]
        if e.base_added > 0 or e.quote_added > 0:
            units += BANDS * GAS_UNITS[1]
        ts = pd.Timestamp(e.time)
        total += units * float(GAS.asof(ts)) * 1e-9 * float(ETH.asof(ts))
    return total


SWAP_PER_REBUILD: dict[str, float] = {}  # $k, from the UTC 0 mainnet run of each version


def load(d: Path, chain: str = "mainnet", v: str | None = None) -> dict:
    """One Demeter run. The decision-hour runs crash in Maker's post-run metrics (benchmark length mismatch) after the
    backtest has finished and written its net value, events and daily fees, so they have no apr_remix summary:
    fees come from the daily fee log, swap cost = rebuilds x the version's UTC 0 swap cost per rebuild."""
    nv = pd.read_csv(next(d.glob("netvalue_*.csv")), index_col=0, parse_dates=True)["net_value"].astype(float)
    ev = pd.read_csv(next(d.glob("result_*.csv")))
    years = (nv.index[-1] - nv.index[0]).days / 365.25
    term = nv.iloc[-1] / 1e3
    daily = nv.resample("1D").last().dropna()
    aprs = list(d.glob("apr_remix_*.csv"))
    if aprs:
        apr = pd.read_csv(aprs[0]).iloc[0]
        fees, swap = float(apr["Total Fee"]) / 1e3, float(apr["Total Swap Fee"]) / 1e3
        if v and chain == "mainnet" and v not in SWAP_PER_REBUILD:
            SWAP_PER_REBUILD[v] = swap / len(ev)
    else:
        last = pd.read_csv(next(d.glob("fees_*.csv"))).iloc[-1]
        fees = (float(last.collected_quote) + float(last.pending_quote)) / 1e3
        swap = SWAP_PER_REBUILD[v] * len(ev)
    gas = gas_usd(ev) / 1e3 if chain == "mainnet" else 0.0
    return {"terminal": term, "cagr": (term / 100) ** (1 / years) - 1, "maxdd": float((nv / nv.cummax() - 1).min()),
            "fees": fees, "swap_cost": swap, "rebuilds": len(ev), "gas": gas, "years": years,
            "ret": np.log(daily).diff().dropna()}


def stress(r: dict) -> dict:
    """A2: fees x 0.66 / x 0.8, swap cost x 2, gas on mainnet."""
    out = {}
    for m in (0.8, 0.66):
        out[f"fees x{m} + swap x2 + gas"] = round(r["terminal"] - (1 - m) * r["fees"] - r["swap_cost"] - r["gas"], 1)
    out["gas only"] = round(r["terminal"] - r["gas"], 1)
    return out


def sig(rets: dict[int, pd.Series], var_sr: float, rng) -> dict:
    """A4 per hour: 1 - one-sided bootstrap p, PSR, DSR (N = 18 x hours), MinTRL vs SR0; median over hours."""
    sr0 = math.sqrt(var_sr) * ((1 - EULER) * norm.ppf(1 - 1 / N_TRIALS) + EULER * norm.ppf(1 - 1 / (N_TRIALS * math.e)))
    rows = []
    for h, r in rets.items():
        x = r.to_numpy()
        T, sr = len(x), x.mean() / x.std()
        g3, g4 = float(r.skew()), float(r.kurt() + 3)
        den = math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
        boot = V.stationary_boot_means(x, 20.0, 2000, rng)
        mintrl = (1 + (1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) * (norm.ppf(0.95) / (sr - sr0)) ** 2) / 365 if sr > sr0 else float("inf")
        rows.append({"hour": h, "sharpe": sr * math.sqrt(365), "one_minus_p": 1 - float(((boot - x.mean()) >= x.mean()).mean()),
                     "psr": float(norm.cdf(sr * math.sqrt(T - 1) / den)),
                     "dsr": float(norm.cdf((sr - sr0) * math.sqrt(T - 1) / den)), "mintrl_years_vs_sr0": mintrl})
    t = pd.DataFrame(rows).set_index("hour")
    return {"sr0_annual": round(sr0 * math.sqrt(365), 3), "median": t.median().round(3).to_dict(),
            "utc0": t.loc[0].round(3).to_dict(), "pass": bool(t["dsr"].median() >= 0.95)}


def kill_line(ret: pd.Series, rng, n=10_000) -> float:
    """A5: 5th percentile of 90-day log returns from block-bootstrapped daily returns."""
    x = ret.to_numpy()
    sums = [x[V.stationary_index(len(x), 20.0, rng)[:90]].sum() for _ in range(n)]
    return float(np.exp(np.percentile(sums, 5)) - 1)


def b2_fair_null(n=1000, rng=None) -> dict:
    """B2 (model): v3's divergence exits vs random exits of the same lengths, started only on deployed days above
    EMA100; the episode open at the window start is excluded from both."""
    w = V.SPEC
    s3 = S.signal_cached(S.V3, 0).loc[w[0]:w[1]]
    s2 = S.signal_cached(S.V2, 0).loc[w[0]:w[1]]
    eps = V.episodes(s3["diverged"].to_numpy())
    eps = [(s, d) for s, d in eps if s > 0]
    fp3 = s2["Fp"].copy()
    for s, d in eps:
        fp3.iloc[s:s + d] = 0.0
    v3 = S.run(S.V2, *w, fp=fp3).terminal / 1e3
    ok = ((s2["Fp"] >= 0.9) & (s2["close"] > s2["ema"])).to_numpy()
    cand = np.flatnonzero(ok)
    L = len(s2)
    res = []
    for _ in range(n):
        mask = np.zeros(L, bool)
        for _s, d in eps:
            for _t in range(2000):
                s0 = int(rng.choice(cand))
                if s0 + d < L and not mask[max(0, s0 - 1):s0 + d + 1].any():
                    mask[s0:s0 + d] = True
                    break
        res.append(S.run(S.V2, *w, fp=s2["Fp"].where(~mask, 0.0)).terminal / 1e3)
    res = np.array(res)
    return {"episodes": [(str(s2.index[s].date()), d) for s, d in eps], "v3_terminal_model": round(v3, 1),
            "null_median": round(float(np.median(res)), 1), "v3_rank": round(float((res < v3).mean()), 3),
            "pass": bool((res < v3).mean() >= 0.95)}


def main():
    rng = np.random.default_rng(21)
    t8b = pd.read_csv(ROOT / "t8b_paths.csv")
    hist_dd = {"v1": -0.632, "v2": -0.614, "v3": -0.472}  # simulator, 2018-01..2026-08, UTC 0 (t1_hours_full.csv)
    cards = {}
    nb = {"v1": ("x0.9", "x1.1"), "v2": ("x1.4", "x1.6"), "v3": ("div0.35", "div0.45")}
    for v in ("v1", "v2", "v3"):
        hours = {h: load(run_dir(v, "hour", h), v=v) for h in HOURS}
        base = load(run_dir(v, "base"), chain="base", v=v)
        neigh = {x: load(run_dir(v, "nb", x), v=v) for x in nb[v]}
        r0 = hours[0]
        srs = [r["ret"].mean() / r["ret"].std() for r in list(hours.values()) + list(neigh.values())]
        profit0 = r0["terminal"] - 100
        tv = pd.Series({h: r["terminal"] for h, r in hours.items()})
        cards[v] = {
            "A1_real_data": {"mainnet": {k: (round(r0[k], 4) if k in ("cagr", "maxdd") else round(r0[k], 1))
                                         for k in ("terminal", "cagr", "maxdd", "fees", "swap_cost", "gas")} | {"rebuilds": r0["rebuilds"]},
                             "base": {k: (round(base[k], 4) if k in ("cagr", "maxdd") else round(base[k], 1))
                                      for k in ("terminal", "cagr", "maxdd", "fees", "swap_cost")} | {"rebuilds": base["rebuilds"], "years": round(base["years"], 2)},
                             "pass": bool(r0["terminal"] > 100 and base["terminal"] > 100)},
            "A2_cost_gas": {"mainnet": stress(r0), "base": stress(base)},
            "A3_plateau": {x: round((r["terminal"] - 100) / profit0 - 1, 3) for x, r in neigh.items()},
            "A4_significance": sig({h: r["ret"] for h, r in hours.items()}, float(np.var(srs, ddof=1)), rng),
            "A5_kill_line_90d": round(kill_line(r0["ret"], rng), 3),
            "A6_monte_carlo_model": {"maxdd_median": round(float(t8b[f"{v}_dd"].median()), 3),
                                     "maxdd_p5": round(float(t8b[f"{v}_dd"].quantile(0.05)), 3),
                                     "history_2018_sim": hist_dd[v]},
            "B1_decision_hour": {"terminal": tv.round(1).to_dict(), "mean": round(tv.mean(), 1), "worst": round(tv.min(), 1),
                                 "utc0_rank_of_6": int((tv > tv[0]).sum() + 1),
                                 "maxdd": {h: round(r["maxdd"], 3) for h, r in hours.items()},
                                 "pass": bool(tv.min() > 100)},
        }
        c = cards[v]
        c["A2_cost_gas"]["pass_mainnet"] = bool(c["A2_cost_gas"]["mainnet"]["fees x0.66 + swap x2 + gas"] > 100)
        c["A2_cost_gas"]["pass_base"] = bool(c["A2_cost_gas"]["base"]["fees x0.66 + swap x2 + gas"] > 100)
        c["A3_plateau"]["pass"] = bool(all(abs(x) <= 0.25 for x in c["A3_plateau"].values()))
    cards["v3"]["B2_random_timing_model"] = b2_fair_null(rng=rng)
    (ROOT / "scorecard_demeter.json").write_text(json.dumps(cards, indent=1, default=str))
    print(json.dumps(cards, default=str))


if __name__ == "__main__":
    main()
