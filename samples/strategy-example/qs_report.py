"""
QUAN-1216 QuantStats reports of v3.2 / v2.2 against three benchmarks (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md,
"Benchmarks in the QuantStats reports"): hold (the benchmark column), 50/50 HODL, fixed F = 0.5 and, from 2026-11-05, Spot F
(the strategy's decisions as spot on a CLOB) (return columns beside the strategy). The export and the cleaning are the checked 2026-11-04 reports' own steps; this file adds the two benchmarks and
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

import numpy as np
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
COLS = {"strategy": "Strategy", "hodl": "50/50 HODL", "fixf": "Fixed F 0.5", "spot": "Spot F (CLOB)"}
# Spot F (Dino, 2026-11-05): the strategy's own F decisions as spot only on a CLOB, Binance daily closes, SPOT_COST of the
# value traded on every change of the target (Binance spot taker 0.1%), no fees earned, no intraday stops. v3.2: ETH weight
# F' x the LP's ETH share (0.7 above EMA100, 0.5 below), the rest USDC; v2.2: the book's LP share as 50/50 ETH / BTC, its ETH,
# BTC and USDC shares as held at each exec, traded on rebuilds and F / side changes
SPOT_COST = 0.001
SPOT_SIGNAL = {"v32": "signal_daily_v3.2_bn_20210506_20260831.csv"}
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


def spot_path(target: pd.DataFrame, prices: pd.DataFrame, trade: pd.Series) -> pd.Series:
    """The spot book's value at each 00:00 (start 1): a decision of day D (columns = assets, weights summing to 1) is traded
    at day D's close and recorded at D + 1 00:00; between trades the weights drift with `prices` (asset values in the unit,
    by close date; the unit itself at 1). The 00:00 of day D0 (the first decision) holds the start capital in the unit."""
    w, v, out = None, 1.0, {}
    days = list(target.index)
    out[days[0]] = 1.0
    for i, d in enumerate(days):
        if w is not None:
            g = (prices.loc[d] / prices.loc[days[i - 1]]).to_numpy()
            grow = float((w * g).sum())
            v *= grow
            w = w * g / grow
        t = target.loc[d].to_numpy(dtype=float)
        if w is None or trade.loc[d]:
            held = w if w is not None else (target.columns == "unit").astype(float)
            v *= 1 - SPOT_COST * float(np.abs(t - held).sum()) / 2
            w = t
        out[d + pd.Timedelta(days=1)] = v
    return pd.Series(out)


def spot_value(root: Path, key: str, mode: str) -> pd.Series:
    """spot_path of v3.2 (USD) or v2.2 (ETH, `mode`'s daily file) from its L0 decisions (SPOT_* above)."""
    import strategy_layers as SL
    if key == "v32":
        sig = pd.read_csv(root / SPOT_SIGNAL[key], parse_dates=["date"]).set_index("date")
        sig = sig.loc[pd.Timestamp("2021-05-05"):pd.Timestamp("2026-08-31")]
        eth = sig["Fp"] * np.where(sig["close"] > sig["ema"], 0.7, 0.5)
        target = pd.DataFrame({"eth": eth, "unit": 1 - eth})
        prices = pd.DataFrame({"eth": SL.binance_close("ethusdt").reindex(sig.index), "unit": 1.0})
        trade = target.diff().abs().sum(axis=1) > 1e-12
    else:
        d = pd.read_csv(root / L0[key] / f"daily_1ETH_{mode}.csv", parse_dates=["date"]).set_index("date")
        target = pd.DataFrame({"btc": d["cur_btc"] + 0.5 * d["cur_lp"], "usdc": d["cur_usdc"],
                               "unit": d["cur_eth"] + 0.5 * d["cur_lp"]})
        target = target.div(target.sum(axis=1), axis=0)
        prices = pd.DataFrame({"btc": 1 / SL.binance_close("ethbtc"), "usdc": 1 / SL.binance_close("ethusdt"),
                               "unit": 1.0}).reindex(d.index)
        trade = d["rebuild"].notna() | (d["F"].diff() != 0) | (d["strong"] != d["strong"].shift())
    if prices.isna().any().any():
        raise ValueError(f"{key}: missing closes for the spot book")
    return spot_path(target, prices, trade)


# Price and F context chart (Dino, 2026-11-05): the pair the strategy trades and the F it held, beside its net value
CONTEXT_PAIR = {"v32": ("ethusdt", "ETH/USD"), "v22": ("ethbtc", "ETH/BTC")}


def context_frame(root: Path, key: str, mode: str, r: pd.Series) -> pd.DataFrame:
    """Per return day of `r` (labelled by its end) plus its start: the traded pair's close at the label (CONTEXT_PAIR, a 23:59
    end takes that day's close) and the F in force during the return, i.e. decided on the close before the return's start
    (v3.2 F', v2.2 F and its strong side). The start row has no F."""
    import strategy_layers as SL
    held = SL.held_price(CONTEXT_PAIR[key][0])
    stamps = pd.DatetimeIndex([r.index[0] - pd.Timedelta(days=1)]).append(r.index)
    at = [t.normalize() + pd.Timedelta(days=1) if (t.hour or t.minute) else t for t in stamps]
    starts = pd.DatetimeIndex([pd.NaT]).append(stamps[:-1])
    decided = [s.normalize() - pd.Timedelta(days=1) if pd.notna(s) else pd.NaT for s in starts]
    if key == "v32":
        sig = pd.read_csv(root / SPOT_SIGNAL[key], parse_dates=["date"]).set_index("date")
        f, strong = sig["Fp"], None
    else:
        d = pd.read_csv(root / L0[key] / f"daily_1ETH_{mode}.csv", parse_dates=["date"]).set_index("date")
        f, strong = d["F"], d["strong"]
    before = pd.Series([pd.notna(x) and x < f.index[0] for x in decided], index=stamps)   # still in cash, nothing decided
    out = pd.DataFrame({"price": held.reindex(at).to_numpy(), "F": f.reindex(decided).to_numpy()}, index=stamps)
    out.loc[before, "F"] = 0.0
    if strong is not None:
        out["strong"] = strong.reindex(decided).to_numpy()
        out.loc[before, "strong"] = False
    if out["price"].isna().any() or out["F"].iloc[1:].isna().any():
        raise ValueError(f"{key} {mode}: missing price or F in the context frame")
    return out


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
            spot = spot_value(root, key, mode)
            df = pd.DataFrame({"strategy": r, "bench": b, "hodl": hodl, "fixf": rf, "spot": _aligned(spot, r, last)})
            if df.isna().any().any():
                raise ValueError(f"{key} {mode}: missing returns\n{df[df.isna().any(axis=1)]}")
            df.to_csv(out / f"{key}_{mode}.csv")
            context_frame(root, key, mode, r).to_csv(out / f"{key}_{mode}_context.csv")
            # alpha as the alpha / beta section: 00:00-to-00:00 returns (daily_simple_returns), hold from held_price
            rs = SL.daily_simple_returns(nv)
            hold = p.pct_change()
            rows = {"hold": SL.factor_row(rs, {"hold": hold}),
                    "fixf": SL.factor_row(rs, {"fixf": SL.daily_simple_returns(nvf)}),
                    "spot": SL.factor_row(rs, {"spot": spot.pct_change().dropna()})}
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
    series = {"Strategy": df["strategy"], bname: df["bench"], "50/50 HODL": df["hodl"], "Fixed F 0.5": df["fixf"],
              "Spot F (CLOB)": df["spot"]}
    style = {"Strategy": ("#348dc1", 1.6), bname: ("#fedd78", 1.2), "50/50 HODL": ("#ff9b74", 1.0), "Fixed F 0.5": ("#3bb273", 1.0),
             "Spot F (CLOB)": ("#7b4ea3", 1.2)}
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
    h, f, sp = a["hold"], a["fixf"], a["spot"]
    rows = [("benchmark", "beta", "alpha / excess a year (t)", "R^2", "beta up / down"),
            (f"{bname}: regression", f"{h['betas']['hold']:.2f}", f"alpha {_pct(h['alpha'])} ({h['alpha_t']:.2f})",
             f"{h['r2']:.2f}", f"{h['beta_up']:.2f} / {h['beta_down']:.2f}"),
            ("Fixed F 0.5: strategy − benchmark", "1 (held)", f"excess {_pct(f['excess'])} ({f['excess_t']:.2f})", "", ""),
            ("Fixed F 0.5: regression", f"{f['betas']['fixf']:.2f}", f"alpha {_pct(f['alpha'])} ({f['alpha_t']:.2f})",
             f"{f['r2']:.2f}", f"{f['beta_up']:.2f} / {f['beta_down']:.2f}"),
            ("Spot F (CLOB): strategy − benchmark", "1 (held)", f"excess {_pct(sp['excess'])} ({sp['excess_t']:.2f})", "", ""),
            ("Spot F (CLOB): regression", f"{sp['betas']['spot']:.2f}", f"alpha {_pct(sp['alpha'])} ({sp['alpha_t']:.2f})",
             f"{sp['r2']:.2f}", f"{sp['beta_up']:.2f} / {sp['beta_down']:.2f}")]
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
                   "Excess over Spot F = what the LP adds to the same decisions held as spot on a CLOB. "
                   "50/50 HODL has no alpha row: its daily return is close to 0.5 x the hold return.")
    div.append(note)
    return div


def context_svg(df: pd.DataFrame, ctx: pd.DataFrame, key: str, unit: str) -> str:
    """Two panels: the strategy's net value (left axis, x of its start) and the traded pair's own price (right axis, the pair's
    units), both on log scales tied so the two lines start at the same point; then the F in force each day (v2.2: strong-side
    days shaded), as an inline SVG."""
    import io
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, NullLocator
    pair = CONTEXT_PAIR[key][1]
    nv = pd.concat([pd.Series({ctx.index[0]: 1.0}), (1 + df["strategy"]).cumprod()])
    price = ctx["price"]
    p0 = float(price.iloc[0])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    a1.plot(nv.index, nv.values, color="#348dc1", lw=1.6, label=f"Strategy ({unit}, left axis) x{nv.iloc[-1]:.2f}")
    a1r = a1.twinx()
    fmt = (lambda v: f"\\${v:,.0f}") if key == "v32" else (lambda v: f"{v:.3g}")   # \$: not matplotlib mathtext
    a1r.plot(price.index, price.values, color="#d9480f", lw=1.3,
             label=f"{pair} (right axis) {fmt(p0)} → {fmt(float(price.iloc[-1]))}")
    for ax in (a1, a1r):
        ax.set_yscale("log")
        ax.yaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
    lo = min(nv.min(), price.min() / p0) / 1.15
    hi = max(nv.max(), price.max() / p0) * 1.15
    a1.set_ylim(lo, hi)
    a1r.set_ylim(lo * p0, hi * p0)          # same log scale: a move of x on one axis is x on the other
    steps = (1, 1.5, 2, 3, 4, 5, 7)

    def ticks(a, b):
        out = []
        for e in range(int(np.floor(np.log10(a))) - 1, int(np.ceil(np.log10(b))) + 1):
            out += [m * 10.0 ** e for m in steps if a <= m * 10.0 ** e <= b]
        return out
    a1.yaxis.set_major_locator(FixedLocator(ticks(lo, hi)))
    a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"x{v:g}"))
    a1r.yaxis.set_major_locator(FixedLocator(ticks(lo * p0, hi * p0)))
    a1r.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
    a1r.yaxis.set_minor_locator(NullLocator())
    a1r.tick_params(axis="y", colors="#d9480f", labelsize=8)
    a1.tick_params(axis="y", colors="#348dc1", labelsize=8)
    a1.axhline(1, color="#000", lw=0.6)
    handles = a1.get_legend_handles_labels()[0] + a1r.get_legend_handles_labels()[0]
    f = ctx["F"].iloc[1:]
    a2.fill_between(f.index, 0, f.values, step="pre", color="#348dc1", alpha=0.35, lw=0)
    a2.step(f.index, f.values, where="pre", color="#348dc1", lw=0.8)
    if "strong" in ctx:
        st = ctx["strong"].iloc[1:].astype(str) == "True"
        a2.fill_between(st.index, 0, 1, where=st.values, step="pre", color="#9775fa", alpha=0.25, lw=0,
                        transform=a2.get_xaxis_transform())
        handles.append(Patch(color="#9775fa", alpha=0.25, label="strong side (F panel)"))
    fig.suptitle(f"Strategy against {pair}, and the F it held", x=0.01, y=0.995, ha="left", fontsize=12, fontweight="bold")
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 0.94), ncol=len(handles), fontsize=8, frameon=False)
    a2.set_ylim(0, 1.05)
    a2.set_ylabel("F", fontsize=9)
    for ax in (a1, a2):
        ax.grid(alpha=0.3)
        ax.spines["top"].set_visible(False)
    a2.spines["right"].set_visible(False)
    a1r.spines["top"].set_visible(False)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    buf = io.StringIO()
    fig.savefig(buf, format="svg")
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


def clean(path: Path, alpha: dict, bname: str, pair: str, rs_svg: str, ctx_svg: str) -> None:
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
    left = soup.find("div", id="left")
    ctx = soup.new_tag("div")
    ctx["id"] = "price_context"
    ctx.append(BeautifulSoup(ctx_svg, "html.parser"))
    left.insert(0, ctx)
    right.insert(right.contents.index(metrics) + 1 if metrics in right.contents else 0, alpha_table(soup, alpha, bname))
    note = soup.new_tag("p")
    note["style"] = "font-size:12px;color:#666;margin:6px 0 0"
    note.string = (f"Benchmarks (QUAN-1216, pre-registered 2026-11-04): {bname} (benchmark column); 50/50 HODL = half "
                   f"{pair} at the close before the first return, never rebalanced; Fixed F 0.5 = the same script with F held "
                   "at 0.5 on every day (v3.2 divergence off, v2.2 weak side), prices, fees, range breaks and costs real; "
                   "Spot F (CLOB, added 2026-11-05) = the strategy's own decisions as spot on Binance daily closes, 0.1% on "
                   "every trade, no LP fees, no intraday stops (v3.2: ETH = F' x 0.7 / 0.5, the rest USDC; v2.2: the LP share "
                   "as 50/50 ETH / BTC). "
                   "Cleaned 2026-11-04: rows, columns and charts that a four-agent check found wrong or misleading for these "
                   "runs are removed (" + "; ".join(sorted(DROP_ROWS)) + "; EOY Multiplier; charts: "
                   + ", ".join(DROP_CHARTS) + f"). Rolling Sharpe ({RS_WINDOW} days) redrawn with the hold line. The first chart (added 2026-11-05) shows the "
                   "strategy against the pair it trades and the F in force each day (decided on the close before). Returns are labelled by the 00:00 UTC at which each day ends; v3.2 adds the "
                   "run's 2026-08-31 23:59 end value as its last return. Gas not charged.")
    soup.find("h4").insert_after(note)
    if soup.title:
        soup.title.string = path.stem.replace("_", " ") + " | QuantStats (cleaned, four benchmarks)"
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
            ctx = pd.read_csv(src / f"{key}_{mode}_context.csv", index_col=0, parse_dates=True)
            unit = "USD" if key == "v32" else "ETH"
            clean(out, alpha, bname, pair, rolling_sharpe_svg(df, bname), context_svg(df, ctx, key, unit))
            print(key, mode, out.name)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("export", "html"):
        sys.exit(__doc__)
    (export if sys.argv[1] == "export" else html)(Path(sys.argv[2]), Path(sys.argv[3]))
