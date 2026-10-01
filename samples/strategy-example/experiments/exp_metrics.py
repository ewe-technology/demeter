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
        res = pd.read_csv(folder.rstrip("/") + ".csv").set_index("variant")["net_return"]   # net of impact, vs the initial quote
        for name, value in res.items():
            table.setdefault(name, {})[seg] = value
    df = pd.DataFrame(table).T
    base = next(n for n in df.index if n.startswith("A_"))
    print((df * 100).round(1).to_string())
    for name in df.index:
        if name == base:
            continue
        gain = (df.loc[name] - df.loc[base]) * 100
        print(f"{name}: wins {int((gain > 0).sum())}/{len(gain)}, median gain {gain.median():+.2f} pts, "
              f"gains {[round(g, 1) for g in gain]}")


def result(args: list) -> None:
    """result <variant prefix, e.g. S_> <segment folders...> --cont <ETH cont folder> <WBTC cont folder>
    Prints the EXP file's Result tables (yearly gain vs A, continuous metrics) for that variant."""
    prefix, i = args[0], args.index("--cont")
    segs, conts = args[1:i], args[i + 1:]
    names = ("ETH", "WBTC")
    if "--names" in conts:   # --names a,b,c after the folders: row labels for other pools (holdouts)
        j = conts.index("--names")
        conts, names = conts[:j], tuple(conts[j + 1].split(","))
    rows, gains = [], []
    for folder in segs:
        res = pd.read_csv(folder.rstrip("/") + ".csv").set_index("variant")
        a = res[[n.startswith("A_") for n in res.index]].iloc[0]
        v = res[[n.startswith(prefix) for n in res.index]].iloc[0]
        seg = os.path.basename(folder.rstrip("/"))[-21:]
        label = seg[:4] if seg.endswith("12-31") else seg[:7] + ".." + seg[-5:]
        gains.append((v.net_return - a.net_return) * 100)
        rows.append(f"| {label} | {a.net_return * 100:+.1f}% | {v.net_return * 100:+.1f}% | {gains[-1]:+.1f} | "
                    f"{abs(a.max_draw_down) * 100:.1f}% → {abs(v.max_draw_down) * 100:.1f}% |")
    if rows:
        print("| test | v6 | this | gain | max DD v6 → this |\n|---|---|---|---|---|")
        print("\n".join(rows))
        print(f"\nWins {sum(g > 0 for g in gains)}/{len(gains)}, median {pd.Series(gains).median():+.2f} pts.\n")
    print("| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |\n|---|---|---|---|---|---|---|---|---|")
    for folder, asset in zip(conts, names):
        eqs, res = load(folder), pd.read_csv(folder.rstrip("/") + ".csv").set_index("variant")
        for tag, pre in (("v6", "A_"), ("this", prefix)):
            name = next(n for n in eqs if n.startswith(pre))
            m, r = metrics(eqs[name]), res.loc[name]
            print(f"| {asset} {tag} | {m['total'] * 100:+.1f}% | {m['cagr'] * 100:.1f}% | {m['maxdd'] * 100:.1f}% | "
                  f"{m['sharpe']:.2f} | {m['calmar']:.2f} | ${r.fees / 1000:.1f}k | ${r.impact / 1000:.2f}k | {int(r.rebuilds)} |")


if __name__ == "__main__":
    {"cont": cont, "years": years, "result": result}[sys.argv[1]](sys.argv[2:])
