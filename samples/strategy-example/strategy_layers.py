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

Usage, from samples/strategy-example:
    python strategy_layers.py l0 <label>=<result folder>:<mode> ...      # mode: reinvest | noreinvest
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pandas as pd

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


def l0_table(runs: dict[str, tuple[str, str]]) -> str:
    """Markdown table, one row per labelled run (result folder, mode)."""
    lines = ["| run | window | start | end value | multiple | CAGR | max DD (daily) | Calmar |", "|---|---|---|---|---|---|---|---|"]
    for label, (folder, mode) in runs.items():
        m = l0(daily_net_value(folder, mode))
        lines.append(f"| {label} | {m['start']:%Y-%m-%d}..{m['end']:%Y-%m-%d} | {m['initial']:,.4g} | {m['terminal']:,.4g} | "
                     f"x{m['terminal'] / m['initial']:.3f} | {m['cagr'] * 100:.2f}% | {m['max_drawdown'] * 100:.2f}% | {m['calmar']:.2f} |")
    return "\n".join(lines)


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


def main(argv: list[str]) -> None:
    if not argv or argv[0] != "l0":
        sys.exit(__doc__)
    runs = {}
    for a in argv[1:]:
        label, spec = a.split("=", 1)
        folder, mode = spec.rsplit(":", 1)
        runs[label] = (folder, mode)
    print(l0_table(runs))


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        _self_check(Path(d))
    main(sys.argv[1:])
