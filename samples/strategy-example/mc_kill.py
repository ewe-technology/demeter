"""
QUAN-1216 kill rules (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md, "Kill rules: Monte Carlo"): stationary bootstrap of the L0
daily returns (the fixed F = 0.5 baseline drawn on the same days), 730-day paths, five fixed rules; how often each fires on paths
as good as the backtest (A), with the timing edge removed (B) or halved (C).

Usage, from samples/strategy-example (PY=../../.venv-rs/bin/python):
    $PY mc_kill.py <result dir>          # <result dir> holds quan1216_l0/ and quan1216_fixedf/
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_layers as SL

V32 = "gamma-maker-defense-ethusdc-v3.2-ig17s-price-gap-up20%~20%-dnprice-sema100-signal-usdceth-usdc-swap10bp-feeinrange-gascap"
RUNS = {"v3.2 0x88e6 (USD)": (f"{V32}-100000-20210506-20260831", f"{V32}-bf0.5-100000-20210506-20260831"),
        "v2.2 0x4585 (ETH)": ("mainnet-ethbtc-mgl-v2_2-20211102-20260831", "mainnet-ethbtc-mgl-v2_2-bf0.5-bweak-20211102-20260831")}
MODES = ("reinvest", "noreinvest")
PATHS, DAYS, SEED = 10_000, 730, 20261104
BLOCKS = (20.0, 90.0)          # mean block: 20 judged, 90 reported
RULES = ("R1 stop: DD", "R2 pause: 90d", "R3 retire: 365d", "R4 retire: under water", "R5 pause: one day", "any")


def stationary_index(n: int, block: float, rng: np.random.Generator) -> np.ndarray:
    """PATHS x DAYS indices into a series of n days: each day continues the block with prob 1 - 1/block, else jumps."""
    idx = np.empty((PATHS, DAYS), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, PATHS)
    jump = rng.random((PATHS, DAYS)) < 1 / block
    fresh = rng.integers(0, n, (PATHS, DAYS))
    for t in range(1, DAYS):
        idx[:, t] = np.where(jump[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def rolling(logr: np.ndarray, n: int) -> np.ndarray:
    """Compounded n-day returns ending on each day from day n on (paths x (DAYS - n + 1))."""
    c = np.concatenate([np.zeros((logr.shape[0], 1)), np.cumsum(logr, axis=1)], axis=1)
    return np.expm1(c[:, n:] - c[:, :-n])


def drawdown(logr: np.ndarray) -> np.ndarray:
    w = np.exp(np.concatenate([np.zeros((logr.shape[0], 1)), np.cumsum(logr, axis=1)], axis=1))
    return (w / np.maximum.accumulate(w, axis=1) - 1)[:, 1:]


def under_water(dd: np.ndarray) -> np.ndarray:
    out = np.zeros_like(dd, dtype=np.int64)
    cur = np.zeros(dd.shape[0], dtype=np.int64)
    for t in range(dd.shape[1]):
        cur = np.where(dd[:, t] < 0, cur + 1, 0)
        out[:, t] = cur
    return out


def first_day(hit: np.ndarray, offset: int = 0) -> np.ndarray:
    """Day (1-based, from the path's start) of the first True per path; DAYS + 1 if never."""
    any_ = hit.any(axis=1)
    return np.where(any_, hit.argmax(axis=1) + 1 + offset, DAYS + 1)


def thresholds(r: pd.Series) -> dict:
    lr = np.log1p(r.to_numpy())[None, :]
    dd = drawdown(lr)
    return {"R1 stop: DD": 1.25 * dd.min(), "R2 pause: 90d": np.quantile(rolling(lr, 90), 0.01),
            "R3 retire: 365d": np.quantile(rolling(lr, 365), 0.01), "R4 retire: under water": 1.5 * under_water(dd).max(),
            "R5 pause: one day": 1.5 * r.min()}


def fire_days(r: np.ndarray, th: dict) -> dict:
    lr = np.log1p(r)
    dd = drawdown(lr)
    d = {"R1 stop: DD": first_day(dd < th["R1 stop: DD"]),
         "R2 pause: 90d": first_day(rolling(lr, 90) < th["R2 pause: 90d"], 89),
         "R3 retire: 365d": first_day(rolling(lr, 365) < th["R3 retire: 365d"], 364),
         "R4 retire: under water": first_day(under_water(dd) > th["R4 retire: under water"]),
         "R5 pause: one day": first_day(r < th["R5 pause: one day"])}
    d["any"] = np.minimum.reduce(list(d.values()))
    return d


def five_pct_levels(r: np.ndarray) -> dict:
    """R1-R3 levels that 5% of these paths cross within DAYS (the path's worst DD / 90d / 365d at its 5th percentile)."""
    lr = np.log1p(r)
    return {"R1 stop: DD": np.quantile(drawdown(lr).min(axis=1), 0.05),
            "R2 pause: 90d": np.quantile(rolling(lr, 90).min(axis=1), 0.05),
            "R3 retire: 365d": np.quantile(rolling(lr, 365).min(axis=1), 0.05)}


def five_pct_levels_hit(r: np.ndarray, levels: dict) -> dict:
    """Share of paths whose worst DD / 90d / 365d within DAYS is below each level."""
    lr = np.log1p(r)
    worst = {"R1 stop: DD": drawdown(lr).min(axis=1), "R2 pause: 90d": rolling(lr, 90).min(axis=1),
             "R3 retire: 365d": rolling(lr, 365).min(axis=1)}
    return {k: float((worst[k] < levels[k]).mean()) for k in levels}


def fmt(rule: str, x: float) -> str:
    return f"{x:.0f} days" if rule.startswith("R4") else f"{100 * x:+.1f}%"


def main(root: Path) -> None:
    for name, (l0f, fixf) in RUNS.items():
        for mode in MODES:
            s = SL.daily_simple_returns(SL.daily_net_value(root / "quan1216_l0" / l0f, mode))
            f = SL.daily_simple_returns(SL.daily_net_value(root / "quan1216_fixedf" / fixf, mode))
            if not s.index.equals(f.index):
                raise ValueError(f"{name} {mode}: fixed-F days differ")
            edge = float((s - f).mean())
            th = thresholds(s)
            print(f"### {name}, {mode}: {len(s)} days, mean excess over fixed F 0.5 {100 * 365 * edge:+.1f}% a year (x365)")
            print("thresholds: " + "; ".join(f"{k} {fmt(k, v)}" for k, v in th.items()))
            for block in BLOCKS:
                rng = np.random.default_rng(SEED)
                idx = stationary_index(len(s), block, rng)
                sv = s.to_numpy()[idx]
                sc = {"A": sv, "B": sv - edge, "C": sv - edge / 2}
                days = {k: fire_days(v, th) for k, v in sc.items()}
                print(f"\nblock {block:g}: | rule | A 1y / 2y | B 1y / 2y | C 1y / 2y | B median first day |")
                for rule in RULES:
                    cells = []
                    for k in ("A", "B", "C"):
                        d = days[k][rule]
                        cells.append(f"{100 * (d <= 365).mean():.1f}% / {100 * (d <= DAYS).mean():.1f}%")
                    b = days["B"][rule]
                    med = f"{np.median(b[b <= DAYS]):.0f}" if (b <= DAYS).any() else "-"
                    print(f"| {rule} | " + " | ".join(cells) + f" | {med} |")
                lv = five_pct_levels(sc["A"])
                print("5% false-alarm levels over 2 years (A): " + "; ".join(f"{k} {fmt(k, v)}" for k, v in lv.items()))
                # not pre-registered: how often B and C cross those 5% levels within 2 years (detection at 5% false alarm)
                det = {k: (five_pct_levels_hit(sc["B"], lv), five_pct_levels_hit(sc["C"], lv)) for k in ("x",)}["x"]
                print("  at those levels, B / C fire within 2 years: "
                      + "; ".join(f"{k} {100 * det[0][k]:.1f}% / {100 * det[1][k]:.1f}%" for k in lv))
            print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
