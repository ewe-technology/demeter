"""
Generic strategy validation: five methods that need only a backtest's net-value series, so any strategy run in Demeter
(or any engine that writes a time-indexed net value) can be scored the same way. Used first on Maker's defense v1/v2/v3
(experiments/VALIDATION-2026-10-13-defense-v1-v3-demeter.md, "Final scorecard"); method notes and references in
experiments/RESEARCH-2026-10-13-strategy-validation.md.

  1 real-data backtest   terminal, CAGR, max drawdown of the net value (largest percentage drop, at the input's resolution)
  2 parameter plateau    profit of neighbour-parameter runs relative to the chosen run's profit
  3 significance         daily log returns r_t = ln(V_t / V_t-1): Sharpe, PSR (Bailey & Lopez de Prado 2012) and
                         1 - p of a one-sided stationary bootstrap of the mean (Politis & Romano 1994)
  4 forward kill line    5th percentile of `kill_days`-day returns from stationary-bootstrapped daily returns
  5 Monte Carlo          `mc_days`-day paths of stationary-bootstrapped daily returns: max drawdown and loss probability

Verdict per pool: 1 fails -> "not for deployment"; 1 and 2 pass -> "pilot"; 3 also passes -> "deployable". Methods 4 and 5
set a rule and a stress figure; they do not gate. Nothing here charges gas or fees the backtest did not charge.

Input: a CSV with a time column and a net-value column (Demeter's netvalue_*.csv works as is: index = time, column
`net_value`). Usage, from samples/strategy-example:

    python strategy_validation.py --pool mainnet=path/netvalue.csv --pool base=path/netvalue.csv \
        --neighbour x0.9=path/netvalue.csv --neighbour x1.1=path/netvalue.csv --initial 100000 \
        --out result/my_strategy/scorecard.json --md result/my_strategy/scorecard.md

Neighbour runs are compared with the first --pool (run them on that pool and window). In Python:

    import strategy_validation as SV
    card = SV.scorecard({"mainnet": "a.csv"}, neighbours={"x0.9": "b.csv"}, initial=100_000)
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass(frozen=True)
class Settings:
    psr_bar: float = 0.95          # method 3 pass bar
    plateau_bar: float = 0.25      # method 2: |profit change| of each neighbour at most this
    sig_block: float = 20.0        # mean block length (days) for methods 3 and 4
    sig_draws: int = 5_000
    kill_days: int = 90            # method 4 horizon
    kill_pct: float = 5.0
    kill_draws: int = 10_000
    mc_block: float = 90.0         # method 5
    mc_days: int = 365
    mc_draws: int = 10_000
    seed: int = 14


# ---------------------------------------------------------------- inputs
def load_net_value(path: str | Path, column: str | None = None) -> pd.Series:
    """Net value indexed by time. Takes Demeter's netvalue_*.csv (first column = time, `net_value`), or any CSV whose
    first column parses as time; `column` names the value column, else `net_value`, else the first numeric column."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    col = column or ("net_value" if "net_value" in df.columns else df.select_dtypes("number").columns[0])
    return df[col].astype(float).dropna().sort_index()


def daily_log_returns(nv: pd.Series) -> pd.Series:
    """r_t = ln(V_t / V_t-1) on the last value of each calendar day."""
    d = nv.resample("1D").last().dropna()
    return np.log(d).diff().dropna()


# ---------------------------------------------------------------- resampling
def stationary_index(n: int, block: float, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap: each day starts a new block at a random position with probability
    1 / block, else continues with the next day (wrapping around)."""
    new = rng.random(n) < 1 / block
    new[0] = True
    starts = rng.integers(n, size=n)
    ar = np.arange(n)
    last = np.maximum.accumulate(np.where(new, ar, 0))
    return (starts[last] + ar - last) % n


# ---------------------------------------------------------------- methods
def method1_backtest(nv: pd.Series, initial: float | None = None) -> dict:
    v0 = float(initial) if initial is not None else float(nv.iloc[0])
    years = (nv.index[-1] - nv.index[0]).days / 365.25
    terminal = float(nv.iloc[-1])
    return {"initial": v0, "terminal": terminal, "years": years,
            "cagr": (terminal / v0) ** (1 / years) - 1 if years > 0 else float("nan"),
            "max_drawdown": float((nv / nv.cummax() - 1).min()), "pass": terminal > v0}


def method2_plateau(chosen_terminal: float, neighbours: dict[str, float], initial: float, bar: float) -> dict:
    profit = chosen_terminal - initial
    change = {k: (t - initial) / profit - 1 for k, t in neighbours.items()}
    return {"profit_change": change, "pass": bool(change) and all(abs(x) <= bar for x in change.values())}


def method3_significance(r: pd.Series, s: Settings, rng) -> dict:
    x = r.to_numpy()
    T, mu, sd = len(x), x.mean(), x.std()
    sr = mu / sd
    skew, kurt = float(r.skew()), float(r.kurt() + 3)       # pandas kurt() is excess kurtosis
    D = math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    psr = float(norm.cdf(sr * math.sqrt(T - 1) / D))
    boot = np.array([x[stationary_index(T, s.sig_block, rng)].mean() for _ in range(s.sig_draws)])
    one_minus_p = 1 - float(((boot - mu) >= mu).mean())
    return {"days": T, "mean": mu, "std": sd, "sharpe_daily": sr, "sharpe_annual": sr * math.sqrt(365),
            "skew": skew, "kurt": kurt, "D": D, "psr": psr, "bootstrap_one_minus_p": one_minus_p,
            "pass": psr >= s.psr_bar}


def method4_kill_line(r: pd.Series, s: Settings, rng) -> float:
    x = r.to_numpy()
    sums = np.array([x[stationary_index(len(x), s.sig_block, rng)[:s.kill_days]].sum() for _ in range(s.kill_draws)])
    return float(np.exp(np.percentile(sums, s.kill_pct)) - 1)


def method5_monte_carlo(r: pd.Series, s: Settings, rng) -> dict:
    x = r.to_numpy()
    dd, ret = np.empty(s.mc_draws), np.empty(s.mc_draws)
    for i in range(s.mc_draws):
        path = np.concatenate([[1.0], np.exp(np.cumsum(x[stationary_index(len(x), s.mc_block, rng)[:s.mc_days]]))])
        dd[i] = (path / np.maximum.accumulate(path) - 1).min()
        ret[i] = path[-1] - 1
    return {"max_drawdown_median": float(np.median(dd)), "max_drawdown_p5": float(np.percentile(dd, 5)),
            "return_median": float(np.median(ret)), "return_p5": float(np.percentile(ret, 5)),
            "loss_probability": float((ret < 0).mean())}


# ---------------------------------------------------------------- scorecard
def verdict(m1: bool, m2: bool | None, m3: bool) -> str:
    if not m1:
        return "not for deployment"
    if m2 is False:
        return "not for deployment"
    return "deployable" if m3 else "pilot"


def scorecard(pools: dict[str, str | Path | pd.Series], neighbours: dict[str, str | Path | pd.Series] | None = None,
              initial: float | None = None, settings: Settings = Settings()) -> dict:
    """Score one strategy. `pools`: name -> net-value CSV path (or Series); `neighbours`: name -> net value of
    neighbour-parameter runs on the first pool. One random stream (settings.seed) runs through all pools in order."""
    rng = np.random.default_rng(settings.seed)
    series = {k: (v if isinstance(v, pd.Series) else load_net_value(v)) for k, v in pools.items()}
    out = {"settings": asdict(settings), "pools": {}}
    first = next(iter(series))
    m1_first = method1_backtest(series[first], initial)
    plateau = None
    if neighbours:
        nb = {k: (v if isinstance(v, pd.Series) else load_net_value(v)) for k, v in neighbours.items()}
        plateau = method2_plateau(m1_first["terminal"], {k: float(v.iloc[-1]) for k, v in nb.items()},
                                  m1_first["initial"], settings.plateau_bar)
        out["method2_plateau"] = {"pool": first} | plateau
    for name, nv in series.items():
        r = daily_log_returns(nv)
        m1 = method1_backtest(nv, initial)
        m3 = method3_significance(r, settings, rng)
        out["pools"][name] = {"method1_backtest": m1, "method3_significance": m3,
                              "method4_kill_line": method4_kill_line(r, settings, rng),
                              "method5_monte_carlo": method5_monte_carlo(r, settings, rng),
                              "verdict": verdict(m1["pass"], plateau["pass"] if plateau else None, m3["pass"])}
    return out


def to_markdown(card: dict) -> str:
    s = card["settings"]
    pools = list(card["pools"])
    head = "| method | " + " | ".join(pools) + " |\n|---|" + "---|" * len(pools) + "\n"
    rows = []

    def g(pool, *keys):
        value = card["pools"][pool]
        for k in keys:
            value = value[k]
        return value

    rows.append("| 1 terminal / initial | " + " | ".join(
        f"{g(p, 'method1_backtest', 'terminal'):,.0f} / {g(p, 'method1_backtest', 'initial'):,.0f}" for p in pools) + " |")
    rows.append("| 1 CAGR / max DD | " + " | ".join(
        f"{g(p, 'method1_backtest', 'cagr'):.1%} / {g(p, 'method1_backtest', 'max_drawdown'):.1%}" for p in pools) + " |")
    if "method2_plateau" in card:
        pl = card["method2_plateau"]
        txt = ", ".join(f"{k} {v:+.1%}" for k, v in pl["profit_change"].items())
        rows.append(f"| 2 plateau ({pl['pool']}, bar ±{s['plateau_bar']:.0%}) | " + " | ".join(
            (f"{txt} {'pass' if pl['pass'] else 'fail'}" if p == pl["pool"] else "—") for p in pools) + " |")
    rows.append("| 3 annual Sharpe | " + " | ".join(f"{g(p, 'method3_significance', 'sharpe_annual'):.2f}" for p in pools) + " |")
    rows.append(f"| 3 PSR (bar {s['psr_bar']}) / bootstrap 1 − p | " + " | ".join(
        f"{g(p, 'method3_significance', 'psr'):.3f} / {g(p, 'method3_significance', 'bootstrap_one_minus_p'):.3f}" for p in pools) + " |")
    rows.append(f"| 4 kill line ({s['kill_days']}-day, P{s['kill_pct']:g}) | " + " | ".join(
        f"{g(p, 'method4_kill_line'):.1%}" for p in pools) + " |")
    rows.append(f"| 5 {s['mc_days']}-day max DD median / P5 | " + " | ".join(
        f"{g(p, 'method5_monte_carlo', 'max_drawdown_median'):.1%} / {g(p, 'method5_monte_carlo', 'max_drawdown_p5'):.1%}" for p in pools) + " |")
    rows.append(f"| 5 {s['mc_days']}-day loss probability | " + " | ".join(
        f"{g(p, 'method5_monte_carlo', 'loss_probability'):.1%}" for p in pools) + " |")
    rows.append("| **verdict** | " + " | ".join(f"**{card['pools'][p]['verdict']}**" for p in pools) + " |")
    return head + "\n".join(rows) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pool", action="append", required=True, metavar="NAME=CSV", help="net value per pool (repeat)")
    ap.add_argument("--neighbour", action="append", default=[], metavar="NAME=CSV",
                    help="neighbour-parameter run on the first pool (repeat)")
    ap.add_argument("--initial", type=float, default=None, help="starting capital (default: first net value)")
    ap.add_argument("--seed", type=int, default=Settings.seed)
    ap.add_argument("--psr-bar", type=float, default=Settings.psr_bar)
    ap.add_argument("--plateau-bar", type=float, default=Settings.plateau_bar)
    ap.add_argument("--out", help="write the scorecard JSON here")
    ap.add_argument("--md", help="write the markdown table here")
    a = ap.parse_args(argv)
    split = lambda xs: dict(x.split("=", 1) for x in xs)
    card = scorecard(split(a.pool), split(a.neighbour) or None, a.initial,
                     Settings(seed=a.seed, psr_bar=a.psr_bar, plateau_bar=a.plateau_bar))
    md = to_markdown(card)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(card, indent=1))
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(md)
    print(md)


if __name__ == "__main__":
    main()
