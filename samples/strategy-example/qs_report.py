"""
QUAN-1216 QuantStats reports of v3.2 / v2.2 against three benchmarks (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md,
"Benchmarks in the QuantStats reports"): hold (the benchmark column), 50/50 HODL and fixed F = 0.5 (return columns beside the
strategy). The export and the cleaning are the checked 2026-11-04 reports' own steps; this file adds the two benchmarks and
an alpha table.

Two steps, two environments (strategy_layers needs the repo's venv, the report needs quantstats 0.0.86):
    $PY qs_report.py export <result dir> <csv dir>     # from samples/strategy-example, PY=../../.venv-rs/bin/python
    <qs python> qs_report.py html <csv dir> <html dir>  # quantstats 0.0.86, pandas 3.1.0, beautifulsoup4
<result dir> holds quan1216_l0/ (the strategy runs) and quan1216_fixedf/ (the BENCH_F=0.5 runs).
"""
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

L0 = {
    "v32": "quan1216_l0/gamma-maker-defense-ethusdc-v3.2-ig17s-price-gap-up20%~20%-dnprice-sema100-signal-usdceth-usdc-swap10bp-"
           "feeinrange-gascap-100000-20210506-20260831",
    "v22": "quan1216_l0/mainnet-ethbtc-mgl-v2_2-20211102-20260831",
}
FIXED = {
    "v32": "quan1216_fixedf/gamma-maker-defense-ethusdc-v3.2-ig17s-price-gap-up20%~20%-dnprice-sema100-signal-usdceth-usdc-"
           "swap10bp-feeinrange-gascap-bf0.5-100000-20210506-20260831",
    "v22": "quan1216_fixedf/mainnet-ethbtc-mgl-v2_2-bf0.5-bweak-20211102-20260831",
}
PAIR = {"v32": ("ethusdt", False), "v22": ("ethbtc", True)}   # hold price; True: invert (BTC per ETH -> ETH per BTC)
MODES = ("reinvest", "noreinvest")
COLS = {"strategy": "Strategy", "hodl": "50/50 HODL", "fixf": "Fixed F 0.5"}
META = {
    "v32": ("ETH-USDC MGL v3.2, mainnet 0x88e6, USD", "Hold ETH (USD)", "ETH + USDC"),
    "v22": ("ETH-cbBTC MGL v2.2, mainnet 0x4585, in ETH", "Hold BTC (in ETH)", "ETH + BTC"),
}


def _aligned(p: pd.Series, r: pd.Series, last: pd.Timestamp) -> pd.Series:
    """A price's daily change on the strategy's return days, as the checked export: the change into each 00:00, and for a
    23:59 end stamp the last close against the one before (the same 24 h)."""
    pb = p.reindex(pd.DatetimeIndex(sorted(set(p.index) | {r.index[0] - pd.Timedelta(days=1)}))).pct_change()
    b = pb.reindex(r.index)
    if last.hour or last.minute:
        b.iloc[-1] = pb.loc[last.normalize() + pd.Timedelta(days=1)]
    return b


def export(root: Path, out: Path) -> None:
    import strategy_layers as SL
    out.mkdir(parents=True, exist_ok=True)
    for key in L0:
        pair, invert = PAIR[key]
        p = SL.held_price(pair)
        if invert:
            p = 1 / p
        for mode in MODES:
            nv = SL.daily_net_value(root / L0[key], mode)
            last = nv.index[-1]
            r = nv.pct_change().dropna()
            b = _aligned(p, r, last)
            start = r.index[0] - pd.Timedelta(days=1)
            hodl = _aligned(0.5 + 0.5 * p / p.loc[start], r, last)
            nvf = SL.daily_net_value(root / FIXED[key], mode)
            rf = nvf.pct_change().dropna()
            if not rf.index.equals(r.index):
                raise ValueError(f"{key} {mode}: fixed-F days differ from the strategy's")
            df = pd.DataFrame({"strategy": r, "bench": b, "hodl": hodl, "fixf": rf})
            if df.isna().any().any():
                raise ValueError(f"{key} {mode}: missing returns\n{df[df.isna().any(axis=1)]}")
            df.to_csv(out / f"{key}_{mode}.csv")
            # alpha as the alpha / beta section: 00:00-to-00:00 returns (daily_simple_returns), hold from held_price
            rs = SL.daily_simple_returns(nv)
            hold = p.pct_change()
            rows = {"hold": SL.factor_row(rs, {"hold": hold}),
                    "fixf": SL.factor_row(rs, {"fixf": SL.daily_simple_returns(nvf)})}
            keep = ("days", "alpha", "alpha_t", "r2", "betas", "excess", "excess_t", "beta_up", "beta_down")
            json.dump({k: {f: v[f] for f in keep} for k, v in rows.items()}, open(out / f"{key}_{mode}_alpha.json", "w"),
                      indent=1, default=float)
            print(key, mode, len(df), df.index[0].date(), df.index[-1].date(),
                  " ".join(f"{c} x{(1 + df[c]).prod():.4f}" for c in df))


# Rows the 2026-11-04 four-agent check found wrong, or whose label misleads for these runs (Dino: show only correct rows)
DROP_ROWS = {
    "Time in Market": "counts days with a non-zero return, not days with liquidity deployed",
    "Smart Sharpe": "benchmark column takes the strategy's autocorrelation penalty",
    "Smart Sortino": "same as Smart Sharpe", "Smart Sortino/√2": "same as Smart Sharpe",
    "Max DD Period End": "shows the last day under water, not the recovery day",
    "R^2": "one strategy-vs-benchmark number printed in both columns",
    "Information Ratio": "daily, not annualised, printed in both columns",
    "Ulcer Performance Index": "cumulative return / Ulcer Index, not the standard annualised Martin ratio",
    "Risk-Adjusted Return": "quantstats bug: uses 252 periods a year, ignores periods_per_year=365",
    "Risk-Return Ratio": "a daily Sharpe, not annualised",
    "Avg. Return": "drops zero-return days (v3.2 parks in USDC on 30% of days)",
    "Profit Ratio": "non-standard formula; counts zero days as wins",
    "Expected Yearly": "treats the partial years 2021 and 2026 as full years",
    "Kelly Criterion": "win rate drops zero-return days",
    "Risk of Ruin": "always about 0 with ~1,900 days",
    "Daily Value-at-Risk": "assumes normal returns; understates the fat tail",
    "Expected Shortfall (cVaR)": "assumes normal returns; understates the fat tail",
    "Gain/Pain (1M)": "sums daily returns instead of compounding them",
    "Outlier Win Ratio": "denominator includes zero-return days",
    "Outlier Loss Ratio": "dropped with Outlier Win Ratio",
    "3Y (ann.)": "window is 35 months, not 36",
    "5Y (ann.)": "window is 59 months for v3.2 and the whole history for v2.2",
    "10Y (ann.)": "less than 10 years of data: equals All-time",
    "Best Year": "counts partial years as full years", "Worst Year": "counts partial years as full years",
    "Win Days": "drops zero-return days", "Win Month": "drops zero-return months",
    "Win Quarter": "drops zero-return quarters", "Win Year": "counts partial years",
    "Recovery Factor": "sum of simple returns / max DD, not the standard compounded definition",
    "Serenity Index": "ad hoc quantstats ratio, not comparable outside quantstats",
    "Alpha": "arithmetic daily intercept x 365, printed as a fraction",
    "Treynor Ratio": "cumulative return / beta, not annualised",
}
# Charts nobody verified, or that mislead (heatmap prints 0.00 for months outside the data)
DROP_CHARTS = ["vol_returns", "monthly_dist", "daily_returns", "rolling_beta", "rolling_vol", "rolling_sortino",
               "monthly_heatmap", "returns_dist"]
# Rolling Sharpe, back on 2026-11-04 (Dino: "加回去"): quantstats' rolling_sharpe checked equal (0 difference) to
# mean / std x sqrt(365) over a 183-day window on all four exports; redrawn here because the report's own chart leaves out
# the benchmark (hold) line
RS_WINDOW = 183


def _pct(x: float) -> str:
    return f"{100 * x:+.1f}%"


def rolling_sharpe_svg(df: pd.DataFrame, bname: str) -> str:
    """The rolling Sharpe chart (RS_WINDOW days, annualised x sqrt(365), rf 0) of the strategy, hold and the two return
    benchmarks, as an inline SVG; the median of each line is in its legend label."""
    import io
    import matplotlib.pyplot as plt
    import quantstats as qs
    series = {"Strategy": df["strategy"], bname: df["bench"], "50/50 HODL": df["hodl"], "Fixed F 0.5": df["fixf"]}
    style = {"Strategy": ("#348dc1", 1.6), bname: ("#fedd78", 1.2), "50/50 HODL": ("#ff9b74", 1.0), "Fixed F 0.5": ("#3bb273", 1.0)}
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for name, r in series.items():
        rs = qs.stats.rolling_sharpe(r, 0.0, RS_WINDOW, True, 365).dropna()
        color, lw = style[name]
        ax.plot(rs.index, rs.values, color=color, lw=lw, label=f"{name} (median {rs.median():.2f})")
    ax.axhline(0, color="#000", lw=0.8)
    ax.set_title(f"Rolling Sharpe ({RS_WINDOW} days, annualised x sqrt(365), rf 0)", fontsize=12, fontweight="bold",
                 color="#000", loc="left")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, ncol=2)
    ax.grid(alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    buf = io.StringIO()
    fig.savefig(buf, format="svg")
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


def alpha_table(soup, a: dict, bname: str):
    """The alpha table (Newey-West t, 10 lags): against hold, and the excess over fixed F = 0.5 (the timing gain)."""
    h, f = a["hold"], a["fixf"]
    rows = [("benchmark", "beta", "alpha / excess a year (t)", "R^2", "beta up / down"),
            (f"{bname}: regression", f"{h['betas']['hold']:.2f}", f"alpha {_pct(h['alpha'])} ({h['alpha_t']:.2f})",
             f"{h['r2']:.2f}", f"{h['beta_up']:.2f} / {h['beta_down']:.2f}"),
            ("Fixed F 0.5: strategy − benchmark", "1 (held)", f"excess {_pct(f['excess'])} ({f['excess_t']:.2f})", "", ""),
            ("Fixed F 0.5: regression", f"{f['betas']['fixf']:.2f}", f"alpha {_pct(f['alpha'])} ({f['alpha_t']:.2f})",
             f"{f['r2']:.2f}", f"{f['beta_up']:.2f} / {f['beta_down']:.2f}")]
    div = soup.new_tag("div")
    div["id"] = "alpha_bench"
    title = soup.new_tag("h3")
    title.string = "Alpha against the benchmarks"
    div.append(title)
    table = soup.new_tag("table")
    for i, row in enumerate(rows):
        tr = soup.new_tag("tr")
        for cell in row:
            c = soup.new_tag("th" if i == 0 else "td")
            c.string = cell
            tr.append(c)
        table.append(tr)
    div.append(table)
    note = soup.new_tag("p")
    note["style"] = "font-size:12px;color:#666"
    note.string = (f"{a['hold']['days']} days of 00:00-to-00:00 returns; alpha and excess = 365 x the daily mean, t is "
                   "Newey-West (10 lags). Excess over fixed F 0.5 = the timing gain over the same LP held at F = 0.5. "
                   "50/50 HODL has no alpha row: its daily return is close to 0.5 x the hold return.")
    div.append(note)
    return div


def clean(path: Path, alpha: dict, bname: str, pair: str, rs_svg: str) -> None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    right = soup.find("div", id="right")
    metrics = right.find("table")
    for tr in metrics.find_all("tr"):
        td = tr.find("td")
        if td and td.get_text(strip=True) in DROP_ROWS:
            tr.decompose()
    # collapse separator rows left next to each other, or at the end
    rows = metrics.tbody.find_all("tr", recursive=False)
    prev_sep = True
    for tr in rows:
        sep = tr.find("hr") is not None
        if sep and prev_sep:
            tr.decompose()
        prev_sep = sep
    rows = metrics.tbody.find_all("tr", recursive=False)
    if rows and rows[-1].find("hr"):
        rows[-1].decompose()
    # EOY table: drop Multiplier if present (strategy / benchmark, meaningless when the benchmark is negative)
    eoy = soup.find("div", id="eoy").find("table")
    heads = [th.get_text(strip=True) for th in eoy.find_all("th")]
    if "Multiplier" in heads:
        k = heads.index("Multiplier")
        for tr in eoy.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) > k:
                cells[k].decompose()
    # Worst drawdowns (one table per return column): the second column is the last day under water
    for th in soup.find("div", id="ddinfo").find_all("th"):
        if th.get_text(strip=True) == "Recovered":
            th.string = "Last day under water"
    for cid in DROP_CHARTS:
        div = soup.find("div", id=cid)
        if div:
            div.decompose()
    rs = soup.find("div", id="rolling_sharpe")
    rs.clear()
    rs.append(BeautifulSoup(rs_svg, "html.parser"))
    right.insert(right.contents.index(metrics) + 1 if metrics in right.contents else 0, alpha_table(soup, alpha, bname))
    note = soup.new_tag("p")
    note["style"] = "font-size:12px;color:#666;margin:6px 0 0"
    note.string = (f"Benchmarks (QUAN-1216, pre-registered 2026-11-04): {bname} (benchmark column); 50/50 HODL = half "
                   f"{pair} at the close before the first return, never rebalanced; Fixed F 0.5 = the same script with F held "
                   "at 0.5 on every day (v3.2 divergence off, v2.2 weak side), prices, fees, range breaks and costs real. "
                   "Cleaned 2026-11-04: rows, columns and charts that a four-agent check found wrong or misleading for these "
                   "runs are removed (" + "; ".join(sorted(DROP_ROWS)) + "; EOY Multiplier; charts: "
                   + ", ".join(DROP_CHARTS) + f"). Rolling Sharpe ({RS_WINDOW} days) redrawn with the hold line. Returns are labelled by the 00:00 UTC at which each day ends; v3.2 adds the "
                   "run's 2026-08-31 23:59 end value as its last return. Gas not charged.")
    soup.find("h4").insert_after(note)
    if soup.title:
        soup.title.string = path.stem.replace("_", " ") + " | QuantStats (cleaned, three benchmarks)"
    path.write_text(str(soup), encoding="utf-8")


def html(src: Path, dst: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import quantstats as qs
    warnings.filterwarnings("ignore")
    dst.mkdir(parents=True, exist_ok=True)
    for key, (title, bname, pair) in META.items():
        for mode in MODES:
            df = pd.read_csv(src / f"{key}_{mode}.csv", index_col=0, parse_dates=True)
            alpha = json.load(open(src / f"{key}_{mode}_alpha.json"))
            returns = df[list(COLS)].rename(columns=COLS)
            out = dst / f"{key}_{mode}.html"
            qs.reports.html(returns, benchmark=df["bench"].rename(bname), rf=0.0, periods_per_year=365, compounded=True,
                            match_dates=False, title=f"{title}, {mode}", benchmark_title=bname, output=str(out),
                            download_filename=out.name)
            clean(out, alpha, bname, pair, rolling_sharpe_svg(df, bname))
            print(key, mode, out.name)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("export", "html"):
        sys.exit(__doc__)
    (export if sys.argv[1] == "export" else html)(Path(sys.argv[2]), Path(sys.argv[3]))
