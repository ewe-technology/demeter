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
pre-registered rules in the results file (yearly_windows, judge_l1_l5).

Usage, from samples/strategy-example:
    python strategy_layers.py l0 <label>=<result folder>:<mode> ...      # mode: reinvest | noreinvest
    python strategy_layers.py yearly <label>=<result folder>:<mode> ...  # L1 + L5 tables
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


# the pre-registered L1 / L5 rule (VALIDATION-2026-10-29-v3_2-v2_2.md): anchored windows and the earlier L5 window start
# at ANCHOR, the later L5 window at L5_SPLIT; L1 counts the full years L1_YEARS (inclusive)
ANCHOR, L5_SPLIT, L1_YEARS = "2022-01-01", "2024-01-01", (2022, 2025)


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
    # report: the v3.2 run above (2024-01-01..2025-12-31 23:59) -> one full year 2024 (-20%), one partial 2025 (+50%)
    rep = yearly_report({"r": (str(tmp / "v32"), "reinvest")})
    assert "| r | -20.0% / -20.0% | +50.0% / 0.0% * |" in rep and "| r | 0 of 1 | not judged |" in rep, rep


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("l0", "yearly"):
        sys.exit(__doc__)
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
