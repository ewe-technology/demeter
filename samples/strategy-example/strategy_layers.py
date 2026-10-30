"""
QUAN-1216: validation layers L0-L10 (experiments/VALIDATION-LAYERS-FIT.md) for ETH-USDC MGL v3.2 and ETH-cbBTC MGL v2.2,
built on strategy_validation.py. Results: experiments/VALIDATION-2026-10-29-v3_2-v2_2.md.

L0 (backtest) so far: terminal, CAGR, max drawdown and Calmar of the UTC-0 daily net value (the 00:00 value of each day
plus the last value of the run), in the run's own unit (USD for v3.2, ETH for v2.2). A run is given as its result folder
and mode; the net value is read from
* v3.2 (gamma_maker_defense_ethusdc_v3_2.py): netvalue_*_<mode>.csv, Demeter's minute net value;
* v2.2 (gamma_ig_gap_bands_defense_btceth_v2_2.py): daily_*_<mode>.csv, principal_eth + reward_btc x btc_eth at the
  execution time (the reward balance in cbBTC valued in ETH that day), opened by the start capital a day before the
  first execution (the file has no row before the first build).

L1 + L5 (the yearly table): the same daily net value cut per calendar year and into anchored windows, judged by the
pre-registered reference rules in the results file (yearly_windows, judge_l1_l5), plus Sharpe / PSR(0) per full year
and per L5 window, a Sharpe difference test and Pardo's walk-forward efficiency (l1_l5_stats).

L6 (regime split): each daily return labelled bull / bear / range by the pre-registered rule on a Binance daily close
(regime_labels: EMA200 slope + drawdown from the 365-day high), per-regime numbers (regime_split) and the reference
rules L6a (gains in every regime) and L6b (the best of three settings per constant is the same in every regime).

L8 + L4 + L3 (whole run, daily log returns, no new backtest): PSR(0), MinTRL and an autocorrelation check (l8_psr), the
deflated Sharpe ratio at the trial ledger's N and the break-even N (deflated_sharpe, breakeven_n), and the stationary
bootstrap's mean test, one-year paths and kill line (l3_bootstrap), judged by the pre-registered reference rules.

Usage, from samples/strategy-example:
    python strategy_layers.py l0 <label>=<result folder>:<mode> ...      # mode: reinvest | noreinvest
    python strategy_layers.py yearly <label>=<result folder>:<mode> ...  # L1 + L5 tables
    python strategy_layers.py regime [--parts] <label>=<result folder>:<mode>:<pair> ...   # pair: ethusdt | ethbtc
    python strategy_layers.py robust <pair> <mode> spec=<folder> ema-=<folder> ema+=<folder> w-=<folder> w+=<folder>
    python strategy_layers.py psr <N trials> <label>=<result folder>:<mode> ...   # L8 + L4 + L3 tables
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

import strategy_validation as SV


def daily_net_value(folder: str | Path, mode: str) -> pd.Series:
    """The run's UTC-0 daily net value (00:00 of each day, plus the run's last value) from its result folder."""
    v32 = glob.glob(f"{folder}/netvalue_*_{mode}.csv")
    v22 = glob.glob(f"{folder}/daily_*_{mode}.csv")
    if len(v32) + len(v22) != 1:
        raise FileNotFoundError(f"{folder}: want one netvalue_*_{mode}.csv or daily_*_{mode}.csv, found {v32 + v22}")
    if v32:
        nv = SV.load_net_value(v32[0])
        midnight = nv[(nv.index.hour == 0) & (nv.index.minute == 0)]
        return pd.concat([midnight, nv.iloc[-1:]]).groupby(level=0).last()
    d = pd.read_csv(v22[0], parse_dates=["exec"]).set_index("exec").sort_index()
    nv = (d["principal_eth"] + d["reward_btc"] * d["btc_eth"]).astype(float)
    # the first row is after the first build (swap cost paid): the start capital (in the file name) opens the series
    found = re.search(r"daily_([\d.]+)ETH_", Path(v22[0]).name)
    if found is None:
        raise ValueError(f"{v22[0]}: no start capital in the name (want daily_<n>ETH_<mode>.csv)")
    start = float(found.group(1))
    return pd.concat([pd.Series([start], index=[nv.index[0] - pd.Timedelta(days=1)]), nv])


def l0(nv: pd.Series) -> dict:
    """L0 numbers of a daily net value: method 1 of strategy_validation plus Calmar = CAGR / |max drawdown|."""
    m = SV.method1_backtest(nv)
    m["calmar"] = m["cagr"] / -m["max_drawdown"] if m["max_drawdown"] < 0 else float("inf")
    m["start"], m["end"] = nv.index[0], nv.index[-1]
    return m


# the pre-registered L1 / L5 rule (VALIDATION-2026-10-29-v3_2-v2_2.md): anchored windows and the earlier L5 window start
# at ANCHOR, the later L5 window at L5_SPLIT; L1 counts the full years L1_YEARS (inclusive)
ANCHOR, L5_SPLIT, L1_YEARS = "2022-01-01", "2024-01-01", (2022, 2025)
MIN_DAYS = 30   # fewer daily returns than this: no Sharpe / PSR for the window (its variance means nothing)


def _window(nv: pd.Series, kind: str, label: str, lo: pd.Timestamp, hi: pd.Timestamp, partial: bool) -> dict:
    m = l0(nv[(nv.index >= lo) & (nv.index <= hi)])
    return {"kind": kind, "window": label, "partial": partial, "return": m["terminal"] / m["initial"] - 1, **m}


def yearly_windows(nv: pd.Series, anchor: str = ANCHOR) -> list[dict]:
    """L1 / L5 windows of a daily net value (VALIDATION-2026-10-29-v3_2-v2_2.md, L1 + L5 rule): one row per calendar
    year (its 1 January value, or the run start, to the next 1 January value, or the run end) and one per anchored
    window (from `anchor`, or the run start if later, to the end of each full year and to the run end). Each row carries
    l0()'s numbers plus `return`, and `partial` when the window does not cover whole calendar years."""
    first, last = nv.index[0], nv.index[-1]
    jan1 = lambda y: pd.Timestamp(year=y, month=1, day=1)
    rows = []
    for y in range(first.year, last.year + 1):
        lo, hi = jan1(y), jan1(y + 1)
        if ((nv.index >= lo) & (nv.index <= hi)).sum() >= 2:
            rows.append(_window(nv, "year", str(y), lo, hi, first > lo or last < hi))
    start = max(pd.Timestamp(anchor), first)
    name = str(start.year) if start == jan1(start.year) else f"{start:%Y-%m-%d}"
    for y in range(start.year, last.year + 1):
        hi = jan1(y + 1)
        if hi > last:   # the run ends inside year y: the last anchored window stops at the run end
            if last > jan1(y):
                rows.append(_window(nv, "anchored", f"{name}..{last:%Y-%m-%d}", start, last, True))
            break
        label = str(y) if name == str(y) else f"{name}..{y}"
        rows.append(_window(nv, "anchored", label, start, hi, start > jan1(start.year)))
    return rows


def judge_l1_l5(nv: pd.Series) -> dict:
    """The pre-registered L1 / L5 rules (VALIDATION-2026-10-29-v3_2-v2_2.md). L1: return > 0 in at least 3 of the 4
    full years 2022-2025. L5: the later window 2024-01-01..run end has CAGR > 0 and Calmar >= 0.5 x the Calmar of
    2022-01-01..2023-12-31 (CAGR > 0 alone if that Calmar is <= 0). A pass is None when the run does not cover what the
    rule needs (it starts after 2022-01-01, or lacks a full year / the later window)."""
    full = [r for r in yearly_windows(nv) if r["kind"] == "year" and not r["partial"]
            and L1_YEARS[0] <= int(r["window"]) <= L1_YEARS[1]]
    up = sum(r["return"] > 0 for r in full)
    n = L1_YEARS[1] - L1_YEARS[0] + 1
    out = {"l1_up_years": up, "l1_full_years": len(full), "l1_pass": up >= n - 1 if len(full) == n else None,
           "l5_earlier": None, "l5_later": None, "l5_pass": None}
    start, split = pd.Timestamp(ANCHOR), pd.Timestamp(L5_SPLIT)
    if nv.index[0] <= start and nv.index[-1] > split:
        early = _window(nv, "l5", f"{start.year}..{split.year - 1}", start, split, False)
        last = nv.index[-1]
        late = _window(nv, "l5", f"{split.year}..{last:%Y-%m-%d}", split, last, last != pd.Timestamp(year=last.year, month=1, day=1))
        out.update(l5_earlier=early, l5_later=late)
        if early["calmar"] != float("inf"):   # no drawdown in the earlier window: the rule does not cover it
            out["l5_pass"] = late["cagr"] > 0 and (early["calmar"] <= 0 or late["calmar"] >= 0.5 * early["calmar"])
    return out


def significance(r: pd.Series) -> dict:
    """strategy_validation's method 3 on daily log returns: Sharpe, PSR(0) with skew / kurtosis, bootstrap 1 - p."""
    return SV.method3_significance(r, SV.Settings(), np.random.default_rng(SV.Settings.seed))


def sharpe_diff(earlier: dict, later: dict) -> dict:
    """Is the later Sharpe below the earlier one? Takes significance() of two non-overlapping samples of daily returns;
    each Sharpe has the asymptotic variance under non-normal returns that PSR also uses (Mertens 2002; Opdyke 2007):
    Var(SR) = D^2 / (T - 1), D^2 = 1 - skew x SR + (kurt - 1) / 4 x SR^2. z = (SR_later - SR_earlier) /
    sqrt(Var_earlier + Var_later); p_later_worse = Phi(z), the one-sided p of a later Sharpe this low if both periods
    share one true Sharpe. Independent returns are assumed (no autocorrelation term)."""
    se = np.sqrt(earlier["D"] ** 2 / (earlier["days"] - 1) + later["D"] ** 2 / (later["days"] - 1))
    z = (later["sharpe_daily"] - earlier["sharpe_daily"]) / se
    return {"z": float(z), "p_later_worse": float(norm.cdf(z))}


def l1_l5_stats(nv: pd.Series) -> dict:
    """Statistics beside the L1 / L5 reference rule: Sharpe and PSR(0) of each full calendar year (L1), of the whole
    span from ANCHOR (or the run start) to the run end, and of the earlier / later L5 windows, the Sharpe difference
    test between them, and Pardo's walk-forward efficiency WFE = later CAGR / earlier CAGR. A window with fewer than
    MIN_DAYS daily returns gets None; WFE is None when the earlier CAGR is <= 0 (the ratio's sign means nothing)."""
    def sig(lo, hi):
        r = SV.daily_log_returns(nv[(nv.index >= lo) & (nv.index <= hi)])
        return significance(r) if len(r) >= MIN_DAYS else None
    years = [{"window": w["window"], **s} for w in yearly_windows(nv) if w["kind"] == "year" and not w["partial"]
             for s in [sig(w["start"], w["end"])] if s]
    out = {"years": years, "full": sig(max(pd.Timestamp(ANCHOR), nv.index[0]), nv.index[-1]),
           "earlier": None, "later": None, "diff": None, "wfe": None}
    j = judge_l1_l5(nv)
    if j["l5_earlier"] is not None:
        e, l = j["l5_earlier"], j["l5_later"]
        s_e, s_l = sig(e["start"], e["end"]), sig(l["start"], l["end"])
        if s_e and s_l:
            out.update(earlier=s_e, later=s_l, diff=sharpe_diff(s_e, s_l),
                       wfe=l["cagr"] / e["cagr"] if e["cagr"] > 0 else None)
    return out


# the pre-registered L6 regime rule (VALIDATION-2026-10-29-v3_2-v2_2.md, L6): EMA200 of the daily close, its change over
# SLOPE_DAYS and the close's drawdown from its HIGH_DAYS high, judged on day D's close
REGIME_EMA, SLOPE_DAYS, HIGH_DAYS = 200, 30, 365
SLOPE_MIN, BEAR_DD = 0.02, -0.20
REGIMES = ("bull", "bear", "range")


def _slope_dd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema = close.ewm(span=REGIME_EMA, adjust=False).mean()
    return ema / ema.shift(freq=f"{SLOPE_DAYS}D").reindex(close.index) - 1, close / close.rolling(f"{HIGH_DAYS}D").max() - 1


def regime_labels(close: pd.Series) -> pd.Series:
    """bull / bear / range per daily close (index = day D): bull = EMA200 up >= 2% over 30 days and the close less than
    20% below its 365-day high; bear = EMA200 down >= 2% and the close 20% or more below the high; range = the rest.
    NaN while the 30-day slope does not exist yet. The EMA is seeded on the first close (adjust=False)."""
    slope, dd = _slope_dd(close)
    label = pd.Series("range", index=close.index, dtype=object)
    label[(slope >= SLOPE_MIN) & (dd > BEAR_DD)] = "bull"
    label[(slope <= -SLOPE_MIN) & (dd <= BEAR_DD)] = "bear"
    label[slope.isna()] = np.nan
    return label


RANGE_PARTS = ("range: flat EMA", "range: drop, EMA up", "range: rebound, EMA down")


def range_parts(close: pd.Series) -> pd.Series:
    """regime_labels with range split in its three parts (a post-hoc diagnostic, not part of the pre-registered rule):
    flat EMA200 (|slope| < 2%), a close 20% or more below the high while the EMA200 still rises, a close less than 20%
    below the high while the EMA200 still falls."""
    slope, dd = _slope_dd(close)
    label = regime_labels(close)
    rng = label == "range"
    label[rng & (slope.abs() < SLOPE_MIN)] = RANGE_PARTS[0]
    label[rng & (slope >= SLOPE_MIN)] = RANGE_PARTS[1]
    label[rng & (slope <= -SLOPE_MIN)] = RANGE_PARTS[2]
    return label


def regime_split(nv: pd.Series, labels: pd.Series, price: pd.Series, groups: tuple[str, ...] = REGIMES) -> dict[str, dict]:
    """Per regime (each label in `groups`), the daily log returns of a daily net value whose return from day D's value to the next one takes
    the label of day D's close (`labels` and `price` indexed by day D): days, share of the labelled days, episodes (runs
    of consecutive days with that label), chained return, annualised return exp(mean x 365) - 1, annualised Sharpe, max
    drawdown of the chained days, and the price's chained / annualised change close(D) / close(D - 1) on the same days."""
    r = np.log(nv.values[1:] / nv.values[:-1])
    day = nv.index[:-1].normalize()
    lab = labels.reindex(day).to_numpy()
    p = np.log(price / price.shift(1)).reindex(day).to_numpy()
    known = pd.notna(lab)
    out = {}
    for g in groups:
        on = lab == g
        x, px = r[on], p[on]
        path = np.exp(np.cumsum(np.r_[0.0, x]))
        out[g] = {"days": int(on.sum()), "share": on.sum() / known.sum() if known.any() else np.nan,
                  "episodes": int((on & ~np.r_[False, on[:-1]]).sum()),
                  "chained": float(path[-1] - 1), "annual": float(np.expm1(x.mean() * 365)) if len(x) else np.nan,
                  "sharpe": float(x.mean() / x.std(ddof=1) * np.sqrt(365)) if len(x) > 1 and x.std(ddof=1) > 0 else np.nan,
                  "max_drawdown": float((path / np.maximum.accumulate(path) - 1).min()),
                  "price_chained": float(np.expm1(px.sum())), "price_annual": float(np.expm1(px.mean() * 365)) if len(x) else np.nan}
    return out


def judge_l6a(split: dict[str, dict]) -> bool | None:
    """The pre-registered L6a rule: annualised return > 0 in every regime with at least MIN_DAYS days; None when no
    regime has that many."""
    judged = [s["annual"] > 0 for s in split.values() if s["days"] >= MIN_DAYS]
    return all(judged) if judged else None


def judge_l6b(settings: dict[str, dict[str, dict]]) -> dict:
    """The pre-registered L6b rule for one constant: `settings` maps "-" / "spec" / "+" to regime_split(); per regime with
    at least MIN_DAYS days in the spec run, the setting with the highest annualised return; stable = one setting wins
    every judged regime; None when no regime is judged."""
    best = {g: max(settings, key=lambda k: settings[k][g]["annual"])
            for g in REGIMES if settings["spec"][g]["days"] >= MIN_DAYS}
    return {"best": best, "stable": len(set(best.values())) == 1 if best else None}


# the pre-registered L8 / L4 / L3 rules (VALIDATION-2026-10-29-v3_2-v2_2.md, L8 + L4 + L3): one-sided 95% bars, Ljung-Box
# over LB_LAGS lags, bootstrap mean blocks (the first is judged) and the one-year loss probability bar
PSR_BAR, LB_LAGS = 0.95, 10
BOOT_BLOCKS, LOSS_BAR = (20.0, 5.0, 60.0), 0.10
Z95 = float(norm.ppf(PSR_BAR))


def _d(s: dict) -> float:
    """sqrt of 1 - skew x SR + (kurt - 1) / 4 x SR^2 (daily SR): the non-normal factor of PSR's standard error."""
    sr = s["sharpe_daily"]
    return float(np.sqrt(1 - s["skew"] * sr + (s["kurt"] - 1) / 4 * sr ** 2))


def min_trl(s: dict) -> float:
    """Minimum track record length (Bailey & Lopez de Prado 2012): days of returns a daily Sharpe with this skew and
    kurtosis needs for PSR(0) >= PSR_BAR, 1 + D^2 x (z / SR)^2; infinite when SR <= 0."""
    sr = s["sharpe_daily"]
    return 1 + _d(s) ** 2 * (Z95 / sr) ** 2 if sr > 0 else float("inf")


def psr_at(s: dict, sr0: float, days: float | None = None) -> float:
    """PSR(sr0) of significance() numbers: Phi((SR - sr0) x sqrt(T - 1) / D), T = `days` (default: the sample's)."""
    t = s["days"] if days is None else days
    return float(norm.cdf((s["sharpe_daily"] - sr0) * np.sqrt(t - 1) / _d(s)))


def l8_psr(nv: pd.Series) -> dict:
    """L8 of a daily net value over the whole run: significance() of its daily log returns plus MinTRL, the lag-1
    autocorrelation rho1, the Ljung-Box Q over lags 1..LB_LAGS and its p-value, and PSR(0) with the AR(1) effective
    sample size T_eff = T (1 - rho1) / (1 + rho1) (None when rho1 <= 0)."""
    r = SV.daily_log_returns(nv)
    s = significance(r)
    x = r.to_numpy() - r.mean()
    t = len(x)
    acf = np.array([(x[k:] * x[:-k]).sum() for k in range(1, LB_LAGS + 1)]) / (x * x).sum()
    q = t * (t + 2) * (acf ** 2 / (t - np.arange(1, LB_LAGS + 1))).sum()
    rho1 = float(acf[0])
    t_eff = t * (1 - rho1) / (1 + rho1) if rho1 > 0 else None
    return {**s, "min_trl": min_trl(s), "rho1": rho1, "lb_q": float(q), "lb_p": float(chi2.sf(q, LB_LAGS)),
            "t_eff": t_eff, "psr_eff": psr_at(s, 0.0, t_eff) if t_eff else None, "l8_pass": s["psr"] >= PSR_BAR}


EULER_GAMMA = 0.5772156649015329


def expected_max_sharpe(n: int, var: float) -> float:
    """Expected maximum of n Sharpe estimates whose true Sharpe is 0 and whose variance is `var` (Bailey & Lopez de
    Prado 2014, the deflated Sharpe ratio): sqrt(var) x ((1 - g) Phi^-1(1 - 1/n) + g Phi^-1(1 - 1/(n e))); 0 for n = 1."""
    if n <= 1:
        return 0.0
    return float(np.sqrt(var) * ((1 - EULER_GAMMA) * norm.ppf(1 - 1 / n) + EULER_GAMMA * norm.ppf(1 - 1 / (n * np.e))))


def deflated_sharpe(s: dict, n: int) -> float:
    """DSR = PSR(SR0), SR0 = the expected maximum Sharpe of n null trials; with no return series of the other trials,
    their Sharpe variance is taken as one estimate's under the null, 1 / (T - 1) (pre-registered L4 rule)."""
    return psr_at(s, expected_max_sharpe(n, 1 / (s["days"] - 1)))


def breakeven_n(s: dict, bar: float = PSR_BAR, cap: int = 10 ** 12) -> int:
    """The largest trial count n with DSR >= bar (DSR falls with n); 0 when even one trial fails, `cap` if none fails."""
    if deflated_sharpe(s, 1) < bar:
        return 0
    lo, hi = 1, 2
    while hi < cap and deflated_sharpe(s, hi) >= bar:
        lo, hi = hi, hi * 2
    if hi >= cap:
        return cap
    while hi - lo > 1:   # DSR(lo) >= bar > DSR(hi)
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if deflated_sharpe(s, mid) >= bar else (lo, mid)
    return lo


def worst_year_return(nv: pd.Series) -> float:
    """The worst return over any 365 days of the run, on its last value of each calendar day."""
    d = nv.resample("1D").last().dropna()
    return float((d / d.shift(365, freq="D").reindex(d.index) - 1).min())


def l3_bootstrap(nv: pd.Series) -> dict:
    """L3 of a daily net value over the whole run, strategy_validation's stationary bootstrap of its daily log returns
    with one random stream seeded Settings.seed, used in this order: the mean test (method 3, 1 - p that the mean is
    > 0) at each mean block in BOOT_BLOCKS, the 90-day kill line (method 4), the one-year paths (method 5). Beside them
    the real run's worst 365-day return and max drawdown. Pass: 1 - p >= PSR_BAR at the first block and the one-year
    loss probability <= LOSS_BAR."""
    r = SV.daily_log_returns(nv)
    s = SV.Settings()
    rng = np.random.default_rng(s.seed)
    one_minus_p = {b: SV.method3_significance(r, SV.Settings(sig_block=b), rng)["bootstrap_one_minus_p"]
                   for b in BOOT_BLOCKS}
    kill = SV.method4_kill_line(r, s, rng)
    mc = SV.method5_monte_carlo(r, s, rng)
    return {"one_minus_p": one_minus_p, "kill_line": kill, **mc, "worst_year": worst_year_return(nv),
            "max_drawdown": float((nv / nv.cummax() - 1).min()),
            "l3_pass": one_minus_p[BOOT_BLOCKS[0]] >= PSR_BAR and mc["loss_probability"] <= LOSS_BAR}


def binance_close(pair: str) -> pd.Series:
    """Binance daily closes binance_<pair>_1d.csv (date = the UTC day D, close = its 24:00 close), next to this file."""
    f = Path(__file__).with_name(f"binance_{pair}_1d.csv")
    return pd.read_csv(f, parse_dates=["date"]).set_index("date")["close"].astype(float)


def _pct(x: float) -> str:
    return "n/a" if x != x else f"{x * 100:+.1f}%"


def _word(p: bool | None) -> str:
    return "not judged" if p is None else ("pass" if p else "fail")


def regime_report(runs: dict[str, tuple[str, str, str]], parts: bool = False) -> str:
    """Markdown for L6a, one row per labelled run (result folder, mode, Binance pair that labels it): per regime days
    (share) / episodes, annualised return, Sharpe, max DD of the chained days and the pair's annualised change.
    parts=True: the range days split by range_parts (post-hoc, no L6a verdict)."""
    groups = ("bull", "bear") + RANGE_PARTS if parts else REGIMES
    out = ["Per regime: days (share) / episodes; annualised return; Sharpe; max DD of the chained days; pair annualised",
           "", "| run | pair | " + " | ".join(groups) + (" |" if parts else " | L6a |"),
           "|---|---|" + "---|" * (len(groups) + (0 if parts else 1))]
    for label, (folder, mode, pair) in runs.items():
        close = binance_close(pair)
        s = regime_split(daily_net_value(folder, mode), (range_parts if parts else regime_labels)(close), close, groups)
        cell = lambda g: (f"{s[g]['days']} ({s[g]['share'] * 100:.0f}%) / {s[g]['episodes']}; {_pct(s[g]['annual'])}; "
                          f"{s[g]['sharpe']:.2f}; {_pct(s[g]['max_drawdown'])}; {_pct(s[g]['price_annual'])}")
        out.append(f"| {label} | {pair} | " + " | ".join(cell(g) for g in groups)
                   + (" |" if parts else f" | {_word(judge_l6a(s))} |"))
    return "\n".join(out)


ROBUST = {"ema": ("ema-", "spec", "ema+"), "width": ("w-", "spec", "w+")}


def robust_report(pair: str, mode: str, folders: dict[str, str]) -> str:
    """Markdown for L6b on one pool: per setting (spec, ema-, ema+, w-, w+) the full-run CAGR / max DD / Calmar and the
    annualised return per regime, then per constant the best setting per regime and whether it is stable."""
    close = binance_close(pair)
    labels = regime_labels(close)
    nv = {k: daily_net_value(f, mode) for k, f in folders.items()}
    split = {k: regime_split(v, labels, close) for k, v in nv.items()}
    out = [f"| setting | CAGR / max DD / Calmar | " + " | ".join(REGIMES) + " |", "|---|---|" + "---|" * len(REGIMES)]
    for k in folders:
        m = l0(nv[k])
        out.append(f"| {k} | {_pct(m['cagr'])} / {_pct(m['max_drawdown'])} / {m['calmar']:.2f} | "
                   + " | ".join(_pct(split[k][g]["annual"]) for g in REGIMES) + " |")
    out += ["", "| constant | best per regime | L6b |", "|---|---|---|"]
    verdicts = []
    for name, keys in ROBUST.items():
        if all(k in split for k in keys):
            b = judge_l6b({("-", "spec", "+")[i]: split[k] for i, k in enumerate(keys)})
            verdicts.append(b["stable"])
            out.append(f"| {name} | " + ", ".join(f"{g}: {w}" for g, w in b["best"].items()) + f" | {_word(b['stable'])} |")
    # the pre-registered rule needs both constants stable; a constant with no judged regime leaves it not judged
    both = None if len(verdicts) < len(ROBUST) or None in verdicts else all(verdicts)
    out.append(f"| both constants | | {_word(both)} |")
    return "\n".join(out)


def psr_report(runs: dict[str, tuple[str, str]], n_trials: int) -> str:
    """Markdown for L8, L4 (DSR at the ledger's n_trials) and L3, one row per labelled run (result folder, mode), each
    over the whole run. A run with fewer than MIN_DAYS daily returns gets one "too few" row per table."""
    data = {label: daily_net_value(folder, mode) for label, (folder, mode) in runs.items()}
    ok = {label: len(SV.daily_log_returns(nv)) >= MIN_DAYS for label, nv in data.items()}
    p8 = {label: l8_psr(nv) for label, nv in data.items() if ok[label]}
    ann = lambda sr: sr * np.sqrt(365)
    l8 = ["L8: whole run, daily log returns", "",
          "| run | window | days | Sharpe | skew / kurt | PSR(0) | MinTRL days | rho1 | Ljung-Box Q(10) / p | "
          "T_eff / PSR(0) at T_eff | L8 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    l4 = [f"L4: DSR at the ledger's N = {n_trials} (SR0 = expected max Sharpe of N null trials, annualised)", "",
          "| run | SR0 at N | DSR at N | DSR at N = 1 / 10 / 100 / 1,000 | break-even N | L4 |", "|---|---|---|---|---|---|"]
    l3 = ["L3: stationary bootstrap of daily log returns (one-year paths: 365 days, block 90)", "",
          "| run | 1 − p block 20 / 5 / 60 | 90-day kill line (P5) | 1-year max DD median / P5 | "
          "1-year return median / P5 | loss probability | real worst 365-day / max DD | L3 |",
          "|---|---|---|---|---|---|---|---|"]
    for label, nv in data.items():
        if not ok[label]:
            for t in (l8, l4, l3):
                t.append(f"| {label} | too few daily returns |")
            continue
        s = p8[label]
        eff = f"{s['t_eff']:.0f} / {s['psr_eff']:.3f}" if s["t_eff"] else "rho1 <= 0"
        l8.append(f"| {label} | {nv.index[0]:%Y-%m-%d}..{nv.index[-1]:%Y-%m-%d} | {s['days']} | {s['sharpe_annual']:.2f} | "
                  f"{s['skew']:.2f} / {s['kurt']:.1f} | {s['psr']:.3f} | {s['min_trl']:,.0f} | {s['rho1']:+.3f} | "
                  f"{s['lb_q']:.1f} / {s['lb_p']:.3f} | {eff} | {_word(s['l8_pass'])} |")
        dsr = deflated_sharpe(s, n_trials)
        sr0 = expected_max_sharpe(n_trials, 1 / (s["days"] - 1))
        l4.append(f"| {label} | {ann(sr0):.2f} | {dsr:.3f} | "
                  + " / ".join(f"{deflated_sharpe(s, n):.3f}" for n in (1, 10, 100, 1000))
                  + f" | {breakeven_n(s):,} | {_word(dsr >= PSR_BAR)} |")
        b = l3_bootstrap(nv)
        l3.append(f"| {label} | " + " / ".join(f"{b['one_minus_p'][k]:.3f}" for k in BOOT_BLOCKS)
                  + f" | {_pct(b['kill_line'])} | {_pct(b['max_drawdown_median'])} / {_pct(b['max_drawdown_p5'])} | "
                  f"{_pct(b['return_median'])} / {_pct(b['return_p5'])} | {b['loss_probability'] * 100:.1f}% | "
                  f"{_pct(b['worst_year'])} / {_pct(b['max_drawdown'])} | {_word(b['l3_pass'])} |")
    return "\n".join(l8 + [""] + l4 + [""] + l3)


def l0_table(runs: dict[str, tuple[str, str]]) -> str:
    """Markdown table, one row per labelled run (result folder, mode)."""
    lines = ["| run | window | start | end value | multiple | CAGR | max DD (daily) | Calmar |", "|---|---|---|---|---|---|---|---|"]
    for label, (folder, mode) in runs.items():
        m = l0(daily_net_value(folder, mode))
        lines.append(f"| {label} | {m['start']:%Y-%m-%d}..{m['end']:%Y-%m-%d} | {m['initial']:,.4g} | {m['terminal']:,.4g} | "
                     f"x{m['terminal'] / m['initial']:.3f} | {m['cagr'] * 100:.2f}% | {m['max_drawdown'] * 100:.2f}% | {m['calmar']:.2f} |")
    return "\n".join(lines)


def yearly_report(runs: dict[str, tuple[str, str]]) -> str:
    """Markdown for L1 + L5, one row per labelled run (result folder, mode): calendar years (return / max DD), anchored
    windows (CAGR / max DD / Calmar) and the L1 / L5 verdicts. `*` marks a partial window."""
    pct = lambda x: "n/a" if x != x else (f"{x * 100:+.1f}%" if x else "0.0%")   # x != x: NaN (a zero-day window)
    star = lambda r: " *" if r["partial"] else ""
    cagr_dd_calmar = lambda m: f"{pct(m['cagr'])} / {pct(m['max_drawdown'])} / {m['calmar']:.2f}" if m else ""
    data = {label: daily_net_value(folder, mode) for label, (folder, mode) in runs.items()}
    wins = {label: yearly_windows(nv) for label, nv in data.items()}
    years = sorted({r["window"] for w in wins.values() for r in w if r["kind"] == "year"})
    out = ["Calendar years: return / max DD (* partial)", "",
           "| run | " + " | ".join(years) + " |", "|---|" + "---|" * len(years)]
    for label, w in wins.items():
        cell = {r["window"]: f"{pct(r['return'])} / {pct(r['max_drawdown'])}{star(r)}" for r in w if r["kind"] == "year"}
        out.append(f"| {label} | " + " | ".join(cell.get(y, "") for y in years) + " |")
    out += ["", "Anchored windows: CAGR / max DD / Calmar (* partial)", "", "| run | windows |", "|---|---|"]
    for label, w in wins.items():
        out.append(f"| {label} | " + "<br>".join(f"{r['window']}: {cagr_dd_calmar(r)}{star(r)}"
                                                 for r in w if r["kind"] == "anchored") + " |")
    out += ["", "| run | L1 up years (2022-25) | L1 | L5 earlier 2022-23 CAGR / DD / Calmar | L5 later 2024.. | L5 |",
            "|---|---|---|---|---|---|"]
    word = lambda p: "not judged" if p is None else ("pass" if p else "fail")
    for label, nv in data.items():
        j = judge_l1_l5(nv)
        out.append(f"| {label} | {j['l1_up_years']} of {j['l1_full_years']} | {word(j['l1_pass'])} | "
                   f"{cagr_dd_calmar(j['l5_earlier'])} | {cagr_dd_calmar(j['l5_later'])} | {word(j['l5_pass'])} |")
    out += ["", "Statistics: annual Sharpe / PSR(0) of daily log returns per full year; L5 earlier vs later Sharpe / PSR(0), "
            "Sharpe difference z and one-sided p (later worse), WFE = later CAGR / earlier CAGR", "",
            "| run | full years | whole span from 2022 (or start) | L5 earlier | L5 later | z / p (later worse) | WFE |",
            "|---|---|---|---|---|---|---|"]
    sp = lambda m: f"{m['sharpe_annual']:.2f} / {m['psr']:.3f}" if m else ""
    for label, nv in data.items():
        st = l1_l5_stats(nv)
        yrs = "<br>".join(f"{y['window']}: {sp(y)}" for y in st["years"])
        wfe = "" if st["wfe"] is None else f"{st['wfe']:.2f}"
        l5 = (f"{sp(st['earlier'])} | {sp(st['later'])} | {st['diff']['z']:+.2f} / {st['diff']['p_later_worse']:.3f} | "
              f"{wfe}") if st["diff"] else "| | |"
        out.append(f"| {label} | {yrs} | {sp(st['full'])} | {l5} |")
    return "\n".join(out)


def _self_check(tmp: Path):
    # v3.2: minute file -> 00:00 values plus the last minute; 100 -> 80 -> 120 over two years: DD -20%, CAGR ~9.5%
    t = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 12:00", "2025-01-01 00:00", "2025-12-31 23:59"])
    run = tmp / "v32"
    run.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"net_value": [100.0, 999.0, 80.0, 120.0]}, index=t).to_csv(run / "netvalue_x_reinvest.csv")
    nv = daily_net_value(run, "reinvest")
    assert nv.tolist() == [100.0, 80.0, 120.0] and nv.index[-1] == t[-1], nv   # 12:00 is not a daily value
    m = l0(nv)
    assert abs(m["max_drawdown"] + 0.2) < 1e-12 and abs(m["calmar"] - m["cagr"] / 0.2) < 1e-12, m
    # v2.2: ETH = principal + cbBTC reward x ETH per BTC, indexed by execution time
    run = tmp / "v22"
    run.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "exec": ["2024-01-02", "2024-01-03"], "btc_eth": [15.0, 16.0],
                  "principal_eth": [1.0, 0.9], "reward_btc": [0.0, 0.01]}).to_csv(run / "daily_1ETH_noreinvest.csv", index=False)
    nv = daily_net_value(run, "noreinvest")   # the 1 ETH start (file name) at the run start, a day before the first exec
    assert nv.tolist() == [1.0, 1.0, 0.9 + 0.16] and nv.index[0] == pd.Timestamp("2024-01-01"), nv
    try:  # a mode with no file is an error, not an empty row
        daily_net_value(run, "reinvest")
        raise AssertionError("missing mode accepted")
    except FileNotFoundError:
        pass
    # L1 / L5 windows: a year runs from its 1 January value to the next 1 January value; 2024 stops at the run end
    nv = pd.Series([100.0, 80.0, 90.0, 150.0, 120.0, 132.0], index=pd.to_datetime(
        ["2022-01-01", "2022-06-01", "2023-01-01", "2023-07-01", "2024-01-01", "2024-06-30"]))
    w = {(r["kind"], r["window"]): r for r in yearly_windows(nv)}
    y22, y23, y24 = w["year", "2022"], w["year", "2023"], w["year", "2024"]
    assert abs(y22["return"] + 0.10) < 1e-12 and abs(y22["max_drawdown"] + 0.20) < 1e-12 and not y22["partial"], y22
    assert abs(y23["return"] - 1 / 3) < 1e-12 and abs(y23["max_drawdown"] + 0.20) < 1e-12, y23   # 150 -> 120
    assert abs(y24["return"] - 0.10) < 1e-12 and y24["max_drawdown"] == 0 and y24["partial"], y24
    a23, aend = w["anchored", "2022..2023"], w["anchored", "2022..2024-06-30"]
    assert abs(a23["return"] - 0.20) < 1e-12 and abs(a23["max_drawdown"] + 0.20) < 1e-12, a23
    assert abs(aend["return"] - 0.32) < 1e-12 and aend["partial"], aend
    j = judge_l1_l5(nv)   # only two full years 2022-2025: L1 cannot be judged; the earlier L5 window is complete
    assert j["l1_pass"] is None and j["l5_pass"] is not None, j
    # L1: 2022 and 2025 lose, 2023 and 2024 gain -> 2 of 4, fail. L5: earlier 100 -> 120 (DD -10%), later 120 -> 140
    t = pd.to_datetime(["2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01", "2026-06-30"])
    j = judge_l1_l5(pd.Series([100.0, 90.0, 120.0, 130.0, 125.0, 140.0], index=t))
    assert (j["l1_up_years"], j["l1_full_years"], j["l1_pass"]) == (2, 4, False), j
    assert abs(j["l5_earlier"]["return"] - 0.20) < 1e-12 and abs(j["l5_earlier"]["max_drawdown"] + 0.10) < 1e-12, j
    assert j["l5_pass"] is True, j
    # later 120 -> 121: CAGR ~0.3%, Calmar ~0.09 against the earlier ~0.95 -> L5 fails though the later CAGR is > 0
    j = judge_l1_l5(pd.Series([100.0, 90.0, 120.0, 130.0, 125.0, 121.0], index=t))
    assert j["l5_later"]["cagr"] > 0 and j["l5_pass"] is False and j["l1_pass"] is False, j
    # a run that starts after 2022-01-01 is reported, not judged
    j = judge_l1_l5(nv[nv.index >= "2023-01-01"])
    assert j["l1_pass"] is None and j["l5_pass"] is None, j
    # no drawdown in 2022-23: the earlier Calmar is infinite, which the rule does not cover -> not judged
    j = judge_l1_l5(pd.Series([100.0, 120.0, 110.0], index=pd.to_datetime(["2022-01-01", "2024-01-01", "2025-01-01"])))
    assert j["l5_earlier"]["max_drawdown"] == 0 and j["l5_pass"] is None, j
    # Sharpe difference: equal samples -> z 0, p 0.5; a later sample that loses steadily -> p near 0; swapping flips z
    rng = np.random.default_rng(1)
    a = significance(pd.Series(rng.normal(0.001, 0.01, 500)))
    d = sharpe_diff(a, a)
    assert abs(d["z"]) < 1e-12 and abs(d["p_later_worse"] - 0.5) < 1e-12, d
    b = significance(pd.Series(rng.normal(-0.002, 0.01, 500)))
    d, back = sharpe_diff(a, b), sharpe_diff(b, a)
    assert d["p_later_worse"] < 0.001 and abs(d["z"] + back["z"]) < 1e-12, d
    # L1 / L5 statistics of a daily net value: per full year and per L5 window; WFE = later CAGR / earlier CAGR
    days = pd.date_range("2022-01-01", "2025-06-30")
    nv = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, len(days)))), index=days)
    st = l1_l5_stats(nv)
    assert [y["window"] for y in st["years"]] == ["2022", "2023", "2024"], st["years"]   # 2025 is partial
    assert all(0 <= y["psr"] <= 1 for y in st["years"]), st
    j = judge_l1_l5(nv)
    assert abs(st["wfe"] - j["l5_later"]["cagr"] / j["l5_earlier"]["cagr"]) < 1e-12, st
    assert 0 <= st["later"]["psr"] <= 1 and 0 <= st["diff"]["p_later_worse"] <= 1, st
    assert st["full"]["days"] == len(days) - 1, st["full"]   # 2022-01-01..2025-06-30: one return per day after the first
    down = pd.Series(100 * np.exp(np.cumsum(rng.normal(-0.002, 0.01, len(days)))), index=days)
    st = l1_l5_stats(down)   # losing 2022-23: earlier CAGR < 0 -> no WFE, the Sharpe test still runs
    assert st["wfe"] is None and st["diff"] is not None, st
    # report: the v3.2 run above (2024-01-01..2025-12-31 23:59) -> one full year 2024 (-20%), one partial 2025 (+50%)
    rep = yearly_report({"r": (str(tmp / "v32"), "reinvest")})
    assert "| r |  |  | | | | |" in rep, rep   # 2 daily returns: too few for any statistic
    assert "| r | -20.0% / -20.0% | +50.0% / 0.0% * |" in rep and "| r | 0 of 1 | not judged |" in rep, rep
    # L6 regime labels: +1% a day -> EMA200 rises ~35% in 30 days at no drawdown: bull; -1% a day -> bear once 20% below
    # the high; flat -> range; the first 30 days have no slope: no label
    days = pd.date_range("2018-01-01", periods=400)
    up = regime_labels(pd.Series(100 * 1.01 ** np.arange(400), index=days))
    assert up.iloc[:30].isna().all() and (up.iloc[300:] == "bull").all(), up.value_counts()
    down = regime_labels(pd.Series(100 * 0.99 ** np.arange(400), index=days))
    assert (down.iloc[300:] == "bear").all(), down.value_counts()
    assert (regime_labels(pd.Series(100.0, index=days)).iloc[30:] == "range").all()
    # a 25% fall after a long rise: the EMA200 still climbs but the close is > 20% below the high -> range, not bull
    fall = pd.Series(np.r_[100 * 1.01 ** np.arange(399), 100 * 1.01 ** 398 * 0.75], index=days)
    assert regime_labels(fall).iloc[-1] == "range", regime_labels(fall).iloc[-3:]
    # range parts (post-hoc diagnostic): flat EMA200, a fall > 20% while the EMA200 still rises, a fall < 20% while it drops
    parts = range_parts(fall)
    assert parts.iloc[-1] == "range: drop, EMA up" and parts.iloc[300] == "bull", parts.iloc[-3:]
    assert (range_parts(pd.Series(100.0, index=days)).iloc[30:] == "range: flat EMA").all()
    # -1% a day, then a close at 85% of the 365-day high (day 35, ~70): 15% below the high while the EMA200 still drops
    bounce = pd.Series(np.r_[100 * 0.99 ** np.arange(399), 0.85 * 100 * 0.99 ** 35], index=days)
    assert range_parts(bounce).iloc[-1] == "range: rebound, EMA down", range_parts(bounce).iloc[-3:]
    # L6 split: the return from 00:00 of D to the next value takes D's label. +10% bull, -10% bear, 0 bear, +10% bull
    # (the last value is at 23:59, as v3.2's run end); the price doubles on bull days and halves on the first bear day
    t = pd.to_datetime(["2024-01-01 00:00", "2024-01-02 00:00", "2024-01-03 00:00", "2024-01-04 00:00", "2024-01-04 23:59"])
    nv = pd.Series([100.0, 110.0, 99.0, 99.0, 108.9], index=t)
    days = pd.date_range("2024-01-01", periods=4)
    labels = pd.Series(["bull", "bear", "bear", "bull"], index=days)
    price = pd.Series([10.0, 20.0, 10.0, 10.0, 20.0], index=pd.date_range("2023-12-31", periods=5))   # closes of D - 1..D
    s = regime_split(nv, labels, price)
    assert (s["bull"]["days"], s["bull"]["episodes"], s["bear"]["days"], s["bear"]["episodes"]) == (2, 2, 2, 1), s
    assert abs(s["bull"]["chained"] - 0.21) < 1e-12 and s["bull"]["max_drawdown"] == 0, s["bull"]
    assert abs(s["bear"]["chained"] + 0.10) < 1e-12 and abs(s["bear"]["max_drawdown"] + 0.10) < 1e-12, s["bear"]
    assert abs(s["bull"]["price_chained"] - 3.0) < 1e-12 and abs(s["bear"]["price_chained"] + 0.5) < 1e-12, s
    assert abs(s["bull"]["share"] - 0.5) < 1e-12 and s["range"]["days"] == 0, s
    assert abs(s["bull"]["annual"] - (1.21 ** (365 / 2) - 1)) < 1e-6 * 1.21 ** (365 / 2), s["bull"]
    # L6a: every regime with >= 30 days must gain; a short regime is not judged; nothing long enough -> None
    reg = lambda **a: {g: {"days": a[g][0], "annual": a[g][1]} for g in REGIMES}
    assert judge_l6a(reg(bull=(300, 0.3), bear=(200, 0.01), range=(500, 0.1))) is True
    assert judge_l6a(reg(bull=(300, 0.3), bear=(200, -0.01), range=(500, 0.1))) is False
    assert judge_l6a(reg(bull=(300, 0.3), bear=(29, -0.5), range=(500, 0.1))) is True   # bear too short to judge
    assert judge_l6a(reg(bull=(10, 0.3), bear=(29, -0.5), range=(0, np.nan))) is None
    # L6b: the best of the three settings per judged regime; stable when one setting wins every judged regime
    b = judge_l6b({"-": reg(bull=(300, 0.2), bear=(200, 0.0), range=(500, 0.1)),
                   "spec": reg(bull=(300, 0.3), bear=(200, 0.1), range=(500, 0.2)),
                   "+": reg(bull=(300, 0.1), bear=(200, 0.05), range=(500, 0.15))})
    assert b == {"best": {"bull": "spec", "bear": "spec", "range": "spec"}, "stable": True}, b
    b = judge_l6b({"-": reg(bull=(300, 0.4), bear=(20, 0.9), range=(500, 0.1)),
                   "spec": reg(bull=(300, 0.3), bear=(20, 0.1), range=(500, 0.2)),
                   "+": reg(bull=(300, 0.1), bear=(20, 0.05), range=(500, 0.15))})
    assert b == {"best": {"bull": "-", "range": "spec"}, "stable": False}, b   # bear has < 30 days in the spec run
    short = reg(bull=(10, 0.3), bear=(29, 0.1), range=(0, np.nan))
    assert judge_l6b({"-": short, "spec": short, "+": short}) == {"best": {}, "stable": None}
    # reports: the v3.2 run above (2024-01-01..2025-12-31, 3 values) on the real ETH/USD labels renders, too short to judge
    rep = regime_report({"r": (str(tmp / "v32"), "reinvest", "ethusdt")})
    assert rep.count("| r | ethusdt |") == 1 and rep.endswith("| not judged |"), rep
    rep = regime_report({"r": (str(tmp / "v32"), "reinvest", "ethusdt")}, parts=True)
    assert "range: flat EMA" in rep and "L6a" not in rep, rep
    rep = robust_report("ethusdt", "reinvest", {k: str(tmp / "v32") for k in ("spec", "ema-", "ema+", "w-", "w+")})
    assert "| ema | " in rep and "| width | " in rep, rep
    assert "| both constants | | not judged |" in rep, rep   # no regime has 30 days: no constant is judged
    # L8: MinTRL of a daily Sharpe 0.05 with normal returns (skew 0, kurtosis 3), worked by hand:
    # D^2 = 1 + 0.5 x 0.0025 = 1.00125, (1.644854 / 0.05)^2 = 1082.217 -> MinTRL = 1084.57 days
    assert abs(min_trl({"sharpe_daily": 0.05, "skew": 0.0, "kurt": 3.0}) - 1084.57) < 0.05
    assert min_trl({"sharpe_daily": -0.01, "skew": 0.0, "kurt": 3.0}) == float("inf")
    # white noise: rho1 near 0, Ljung-Box does not reject; AR(1) with phi 0.3: rho1 near 0.3, Ljung-Box rejects
    days = pd.date_range("2020-01-01", periods=1500)
    e = rng.normal(0.001, 0.01, len(days))
    p8 = l8_psr(pd.Series(100 * np.exp(np.cumsum(e)), index=days))
    assert abs(p8["rho1"]) < 0.08 and p8["lb_p"] > 0.01 and p8["days"] == len(days) - 1, p8
    ar = e.copy()
    for i in range(1, len(ar)):
        ar[i] = 0.3 * (ar[i - 1] - 0.001) + e[i]
    p8 = l8_psr(pd.Series(100 * np.exp(np.cumsum(ar)), index=days))
    assert abs(p8["rho1"] - 0.3) < 0.08 and p8["lb_p"] < 1e-6, p8
    assert p8["t_eff"] < p8["days"] and p8["psr_eff"] < p8["psr"], p8   # fewer effective days: less evidence
    # L4: the expected maximum of 1,000 standard normals is about 3.24 (order statistics tables); one trial: no haircut
    assert abs(expected_max_sharpe(1000, 1.0) - 3.24) < 0.03 and expected_max_sharpe(1, 1.0) == 0.0
    s = {"sharpe_daily": 0.06, "skew": -0.5, "kurt": 8.0, "days": 1800}
    dsr = {n: deflated_sharpe(s, n) for n in (1, 10, 100, 1000)}
    assert dsr[1] == psr_at(s, 0.0) and dsr[1] > dsr[10] > dsr[100] > dsr[1000], dsr
    be = breakeven_n(s)
    assert deflated_sharpe(s, be) >= PSR_BAR > deflated_sharpe(s, be + 1), be
    assert breakeven_n({**s, "sharpe_daily": 0.01}) == 0   # PSR(0) already below the bar: no N passes
    # L3: a steady gainer passes both parts at every block; a loser fails; one seed per run -> same numbers twice
    days = pd.date_range("2020-01-01", periods=1000)
    win = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.01, len(days)))), index=days)
    b3 = l3_bootstrap(win)
    assert all(v > 0.99 for v in b3["one_minus_p"].values()) and b3["loss_probability"] < 0.01 and b3["l3_pass"], b3
    assert l3_bootstrap(win) == b3
    lose = pd.Series(100 * np.exp(np.cumsum(rng.normal(-0.001, 0.01, len(days)))), index=days)
    b3 = l3_bootstrap(lose)
    assert b3["one_minus_p"][20.0] < 0.5 and b3["loss_probability"] > 0.5 and not b3["l3_pass"], b3
    # worst 365-day return of the real run: flat 100 for 400 days, then 50 -> -50%
    step = pd.Series(np.r_[np.full(400, 100.0), np.full(600, 50.0)], index=days)
    assert abs(worst_year_return(step) + 0.5) < 1e-12
    # report: the steady gainer as a v3.2 minute file renders all three tables with verdicts; the 3-value run is too short
    run = tmp / "win"
    run.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"net_value": win.values}, index=win.index).to_csv(run / "netvalue_x_reinvest.csv")
    rep = psr_report({"w": (str(run), "reinvest"), "r": (str(tmp / "v32"), "reinvest")}, n_trials=50)
    assert rep.count("| w | ") == 3 and rep.count("| pass |") == 3, rep
    assert rep.count("| r | too few daily returns |") == 3 and "N = 50" in rep, rep


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("l0", "yearly", "regime", "robust", "psr"):
        sys.exit(__doc__)
    if argv[0] == "psr":
        runs = {}
        for a in argv[2:]:
            label, spec = a.split("=", 1)
            runs[label] = tuple(spec.rsplit(":", 1))
        print(psr_report(runs, int(argv[1])))
        return
    if argv[0] == "robust":
        print(robust_report(argv[1], argv[2], dict(a.split("=", 1) for a in argv[3:])))
        return
    if argv[0] == "regime":
        parts = argv[1:2] == ["--parts"]
        runs = {}
        for a in argv[1 + parts:]:
            label, spec = a.split("=", 1)
            folder, mode, pair = spec.rsplit(":", 2)
            runs[label] = (folder, mode, pair)
        print(regime_report(runs, parts))
        return
    runs = {}
    for a in argv[1:]:
        label, spec = a.split("=", 1)
        folder, mode = spec.rsplit(":", 1)
        runs[label] = (folder, mode)
    print(l0_table(runs) if argv[0] == "l0" else yearly_report(runs))


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        _self_check(Path(d))
    main(sys.argv[1:])
