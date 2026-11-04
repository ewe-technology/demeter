"""
QUAN-1216 forward window 2026-09-01..2026-11-03 (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md, "Forward window"): the L0 runs
and the fixed F = 0.5 baselines continued to 2026-11-03, read against L0 and against hold, 50/50 HODL and fixed F = 0.5.

Usage, from samples/strategy-example (PY=../../.venv-rs/bin/python):
    $PY forward_window.py <result dir> <v32|v22|v22base> ...
<result dir> holds quan1216_l0/ (L0), quan1216_oos/ (the continued runs: strategy and -bf0.5).
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import strategy_layers as SL

V32 = "gamma-maker-defense-ethusdc-v3.2-ig17s-price-gap-up20%~20%-dnprice-sema100-signal-usdceth-usdc-swap10bp-feeinrange-gascap"
RUNS = {   # L0 folder, continued folder, fixed-F continued folder, hold pair, invert, unit
    "v32": (f"{V32}-100000-20210506-20260831", f"{V32}-100000-20210506-20261103", f"{V32}-bf0.5-100000-20210506-20261103",
            "ethusdt", False, "USD"),
    "v22": ("mainnet-ethbtc-mgl-v2_2-20211102-20260831", "mainnet-ethbtc-mgl-v2_2-20211102-20261103",
            "mainnet-ethbtc-mgl-v2_2-bf0.5-bweak-20211102-20261103", "ethbtc", True, "ETH"),
    "v22base": ("base-ethbtc-mgl-v2_2-20240914-20260831", "base-ethbtc-mgl-v2_2-20240914-20261103",
                "base-ethbtc-mgl-v2_2-bf0.5-bweak-20240914-20261103", "ethbtc", True, "ETH"),
}
MODES = ("reinvest", "noreinvest")
FREEZE = pd.Timestamp("2026-10-28")   # first day after the 2026-10-27 spec freeze


def returns(nv: pd.Series) -> pd.DataFrame:
    """Daily returns labelled by their end point, with the point each starts from (the QuantStats export's series)."""
    return pd.DataFrame({"r": nv.pct_change(), "start": pd.Series(nv.index, index=nv.index).shift()}).iloc[1:]


def held_returns(p: pd.Series, r: pd.DataFrame) -> pd.Series:
    """The hold price's change over each return's own span (start -> end; a 23:59 end uses that day's close)."""
    def at(t):
        return p.loc[t.normalize() + pd.Timedelta(days=1)] if (t.hour or t.minute) else p.loc[t]
    return pd.Series([at(e) / at(s) - 1 for e, s in zip(r.index, r["start"])], index=r.index)


def stats(r: pd.Series) -> dict:
    path = (1 + r).cumprod()
    dd = float((path / path.cummax().clip(lower=1) - 1).min())
    vol = float(r.std() * np.sqrt(365))
    return {"ret": float(path.iloc[-1] - 1), "dd": dd, "vol": vol,
            "sharpe": float(r.mean() * 365 / vol) if vol else float("nan")}


def rolling_percentile(r_bt: pd.Series, n: int, x: float) -> float:
    """x as a mid-rank percentile of the compounded returns of every n-day rolling window of the backtest series: the
    share below x plus half the share equal to it (review 2026-11-04; v3.2 has many windows at exactly 0, all USDC)."""
    roll = np.exp(np.log1p(r_bt).rolling(n).sum().dropna()) - 1
    tie = np.isclose(roll, x, rtol=0.0, atol=1e-12)
    return float(((roll < x) & ~tie).mean() + 0.5 * tie.mean())


def mean_f(root: Path, key: str, folder: str, a: pd.Timestamp, b: pd.Timestamp) -> float:
    if key == "v32":
        s = pd.read_csv(root / "quan1216_oos" / "signal_daily_v3.2_bn_20210506_20261103.csv", parse_dates=["date"]).set_index("date")
        col = "Fp"
    else:
        s = pd.read_csv(root / "quan1216_oos" / folder / "signal_frame.csv", index_col=0, parse_dates=True)
        col = "F"
    return float(s.loc[a - pd.Timedelta(days=1):b - pd.Timedelta(days=1), col].astype(float).mean())


def rebuilds(root: Path, key: str, folder: str, mode: str, a: pd.Timestamp) -> int:
    if key == "v32":
        f = glob.glob(f"{root / 'quan1216_oos' / folder}/result_*_{mode}.csv")[0]
    else:
        f = glob.glob(f"{root / 'quan1216_oos' / folder}/rebuilds_*_{mode}.csv")[0]
    t = pd.to_datetime(pd.read_csv(f)["time"])
    return int((t >= a).sum())


def report(root: Path, key: str) -> list[str]:
    l0f, cont, fixed, pair, invert, unit = RUNS[key]
    p = SL.held_price(pair)
    if invert:
        p = 1 / p
    out = [f"### {key} ({unit})", ""]
    for mode in MODES:
        old = SL.daily_net_value(root / "quan1216_l0" / l0f, mode)
        new = SL.daily_net_value(root / "quan1216_oos" / cont, mode)
        common = old.index.intersection(new.index)
        common = common[(common.hour == 0) & (common.minute == 0)]
        same = bool((old.loc[common] == new.loc[common]).all())
        # the forward window starts at the first 00:00 after L0's last day: v3.2's L0 ends 08-31 23:59, v2.2's daily file at
        # 08-31 00:00 though its run covered that day (review 2026-11-04: the return from 08-31 belonged to L0's run)
        a = old.index[-1].floor("D") + pd.Timedelta(days=1)
        r = returns(new)
        rf = returns(SL.daily_net_value(root / "quan1216_oos" / fixed, mode))
        if not rf.index.equals(r.index):
            raise ValueError(f"{key} {mode}: fixed-F days differ")
        hold = held_returns(p, r)
        bt = returns(old)["r"]
        out.append(f"{mode}: continued run equals L0 on {len(common)} common 00:00 values: {same}; window starts {a.date()}")
        out.append("")
        out.append("| window | days | series | return | max DD | vol | Sharpe | strategy − it | percentile in backtest |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for name, lo in (("forward", a), ("clean", FREEZE)):
            w = r["start"] >= lo
            s = r.loc[w, "r"]
            hodl_path = 0.5 + 0.5 * (1 + hold[w]).cumprod()
            hodl = hodl_path.pct_change()
            hodl.iloc[0] = hodl_path.iloc[0] - 1
            series = {"strategy": s, "hold": hold[w], "50/50 HODL": hodl, "fixed F 0.5": rf.loc[w, "r"]}
            st = {k: stats(v) for k, v in series.items()}
            for k, v in st.items():
                diff = "" if k == "strategy" else f"{100 * (st['strategy']['ret'] - v['ret']):+.1f} pts"
                pct = f"{100 * rolling_percentile(bt, len(s), v['ret']):.0f}%" if k == "strategy" else ""
                out.append(f"| {name} {s.index[0].date()}..{s.index[-1].date()} | {len(s)} | {k} | {100 * v['ret']:+.2f}% | "
                           f"{100 * v['dd']:.1f}% | {100 * v['vol']:.0f}% | {v['sharpe']:.2f} | {diff} | {pct} |")
            if name == "forward":
                fm = mean_f(root, key, cont, a, s.index[-1])
                out.append(f"| | | mean F {fm:.3f}, rebuilds {rebuilds(root, key, cont, mode, a)} | | | | | | |")
        out.append("")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    for key in sys.argv[2:]:
        print("\n".join(report(root, key)))
