"""
Summarise v6_validate.py runs the way the EXP files report them (daily equity, net of price impact).

usage (from samples/strategy-example):
    python experiments/exp_metrics.py cont  <folder> [<folder> ...]   # continuous runs: total / CAGR / max DD / Sharpe / Calmar
    python experiments/exp_metrics.py years <folder> [<folder> ...]   # yearly segments: net return per variant, wins vs A, median gain

<folder> is result/v6_validate/<tag>/ (the per-variant equity_<name>.csv files). The baseline is the variant whose
name starts with "A_". Calmar = CAGR / |max DD|, CAGR over 365.25-day years, Sharpe from daily returns x sqrt(365).
"""
import glob
import os
import sys

import numpy as np
import pandas as pd


def load(folder: str) -> dict:
    out = {}
    for f in sorted(glob.glob(os.path.join(folder, "equity_*.csv"))):
        name = os.path.basename(f)[len("equity_"):-len(".csv")]
        out[name] = pd.read_csv(f, index_col=0, parse_dates=True)["net_value"]
    return out


def metrics(eq: pd.Series) -> dict:
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    dd = float((eq / eq.cummax() - 1).min())
    r = eq.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else float("nan")
    return {"total": total, "cagr": cagr, "maxdd": dd, "sharpe": sharpe,
            "calmar": cagr / abs(dd) if dd < 0 else float("nan")}


def cont(folders: list) -> None:
    rows = []
    for folder in folders:
        for name, eq in load(folder).items():
            rows.append({"run": os.path.basename(folder.rstrip("/")), "variant": name, **metrics(eq)})
    df = pd.DataFrame(rows)
    for c in ("total", "cagr", "maxdd"):
        df[c] = (df[c] * 100).round(1)
    df["sharpe"] = df["sharpe"].round(2)
    df["calmar"] = df["calmar"].round(2)
    pd.set_option("display.width", 220, "display.max_colwidth", 60)
    print(df.to_string(index=False))


def years(folders: list) -> None:
    table = {}
    for folder in folders:
        seg = os.path.basename(folder.rstrip("/"))[-21:]   # <start>-<end>
        for name, eq in load(folder).items():
            table.setdefault(name, {})[seg] = eq.iloc[-1] / eq.iloc[0] - 1
    df = pd.DataFrame(table).T
    base = next(n for n in df.index if n.startswith("A_"))
    print((df * 100).round(1).to_string())
    for name in df.index:
        if name == base:
            continue
        gain = (df.loc[name] - df.loc[base]) * 100
        print(f"{name}: wins {int((gain > 0).sum())}/{len(gain)}, median gain {gain.median():+.2f} pts, "
              f"gains {[round(g, 1) for g in gain]}")


if __name__ == "__main__":
    {"cont": cont, "years": years}[sys.argv[1]](sys.argv[2:])
