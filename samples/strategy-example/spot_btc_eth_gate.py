"""
Spot version of the tri-pool gate. The decomposition (tri_btc_eth_gate.py --decompose, report section 10) showed the
LP layer lost to holding the same tokens, so this one only holds spot: ETH, BTC and USDC.

Rules, judged daily at 00:00 UTC on yesterday's close (same signals as tri_btc_eth_gate.build_signal):
  * gate: none / btc / eth / both above their EMA, with optional hysteresis `band`
  * when in, hold the (ETH, BTC) value shares of `mix`, the rest in USDC. A mix has a share for ETH strong and
    one for ETH weak (ETH/BTC close vs its EMA); fixed mixes use the same share for both
  * trade only when the target shares change; holdings drift with prices in between
  * every trade pays `--cost` bps on the notional moved, no gas (CEX taker or an L2/aggregator route)

Holdout: in-sample is 2022-2025, the period every earlier experiment looked at. 2026-01-01 onwards is only shown
for CANDIDATES (fixed below before the first run) and the walk-forward picks, never used to choose.

Data: the ETH/USDC and WBTC/WETH minute files under ../real-data/<pool>/ (on the backtest host, synced from the
demeter S3 bucket, which runs to 2026-09-30). Hourly prices are cached in RESULT_DIR after the first load.

Run from samples/strategy-example:
  PYTHONPATH=../.. python spot_btc_eth_gate.py            # grid, walk-forward, start months, holdout
  PYTHONPATH=../.. python spot_btc_eth_gate.py --cost 5   # same with 5 bps per trade
"""
import argparse
import os
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from tri_btc_eth_gate import (BANDS, DATA_START, EMA_SPANS, ETH_KEY, ETH_POOL, RATIO_KEY, RATIO_POOL, TILT_STRONG,
                              TILT_WEAK, Config, build_signal, eth_pool, load_market, ratio_pool, signal_column,
                              spot_mix)

END = date(2026, 9, 30)  # last day of both pools in the S3 data as of 2026-10-02
IN_SAMPLE = ("2022-01-01", "2026-01-01")
HOLDOUT = "2026-01-01"
RESULT_DIR = "result/spot-gate"
INITIAL_USDC = 100_000


def _lp(target) -> tuple:
    """(ETH, BTC) shares the LP version held right after placing `target`, see report 10.1."""
    mix = spot_mix(Config("lp", "btc"), target)
    return round(mix["eth"], 4), round(mix["btc"], 4)


# name -> ((eth, btc) when ETH is strong vs BTC, (eth, btc) when weak)
MIXES = {
    "lp_tilt": (_lp(TILT_STRONG), _lp(TILT_WEAK)),  # what the LP follow version held, ~60% / ~86% in crypto
    "lp_fixed": (_lp((0.5, 0.5)), _lp((0.5, 0.5))),
    "full_fixed": ((0.5, 0.5), (0.5, 0.5)),
    "full_tilt": (TILT_STRONG, TILT_WEAK),
    "btc_only": ((0.0, 1.0), (0.0, 1.0)),
    "switch": ((1.0, 0.0), (0.0, 1.0)),  # all ETH when ETH is strong, all BTC when weak
}
GATES = ("btc", "eth", "both")


@dataclass(frozen=True)
class SpotConfig:
    gate: str
    mix: str
    ema_span: int = 100
    band: float = 0.0

    @property
    def name(self) -> str:
        if self.gate == "none":
            return f"none_{self.mix}"
        return f"{self.gate}{self.ema_span}_b{self.band:g}_{self.mix}"


def build_grid() -> list[SpotConfig]:
    configs = [SpotConfig("none", mix) for mix in MIXES]
    for gate in GATES:
        for span in EMA_SPANS:
            for band in BANDS:
                for mix in MIXES:
                    configs.append(SpotConfig(gate, mix, span, band))
    return configs


# fixed before the first run, the only configs whose holdout is reported besides the walk-forward picks
CANDIDATES = (
    SpotConfig("btc", "lp_tilt", 100, 0.0),  # the spot twin of the LP btc100_follow
    SpotConfig("btc", "full_tilt", 100, 0.0),
    SpotConfig("btc", "full_fixed", 100, 0.0),
    SpotConfig("btc", "btc_only", 100, 0.0),
)


def load_prices() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Hourly ETH and BTC prices in USD, plus the minute-level daily closes of ETH/USDC and WBTC/WETH."""
    cache = f"{RESULT_DIR}/prices_{END}.csv"
    if os.path.exists(cache):
        frame = pd.read_csv(cache, index_col=0, parse_dates=True)
        daily = pd.read_csv(f"{RESULT_DIR}/daily_{END}.csv", index_col=0, parse_dates=True)
        return frame, daily["eth"], daily["ratio"]
    eth, eth_close = load_market(ETH_KEY, eth_pool, ETH_POOL, DATA_START, END, "1h")
    ratio, ratio_close = load_market(RATIO_KEY, ratio_pool, RATIO_POOL, DATA_START, END, "1h")
    index = eth.index.intersection(ratio.index)
    p_eth = eth.loc[index, "price"].astype(float)
    frame = pd.DataFrame({"eth": p_eth, "btc": p_eth * ratio.loc[index, "price"].astype(float)})
    frame.to_csv(cache)
    pd.DataFrame({"eth": eth_close, "ratio": ratio_close}).to_csv(f"{RESULT_DIR}/daily_{END}.csv")
    return frame, eth_close, ratio_close


def target_shares(cfg: SpotConfig, signal: pd.DataFrame) -> pd.DataFrame:
    """(eth, btc) share per day, from that day's row of the shifted signal."""
    strong, weak = MIXES[cfg.mix]
    if cfg.gate == "none":
        gate = pd.Series(True, index=signal.index)
    else:
        col = lambda s: signal[signal_column(s, cfg.ema_span, cfg.band)]
        gate = {"btc": col("btc"), "eth": col("eth"), "both": col("btc") & col("eth")}[cfg.gate]
    eth_strong = signal[signal_column("ethbtc", cfg.ema_span, cfg.band)]
    eth = np.where(gate, np.where(eth_strong, strong[0], weak[0]), 0.0)
    btc = np.where(gate, np.where(eth_strong, strong[1], weak[1]), 0.0)
    return pd.DataFrame({"eth": eth, "btc": btc}, index=signal.index)


def simulate(cfg: SpotConfig, prices: pd.DataFrame, signal: pd.DataFrame, start: str, cost_bps: float) -> dict:
    """Hourly net value from `start`, trading at 00:00 only when the target shares change."""
    p = prices.loc[start:]
    days = pd.DatetimeIndex(p.index.normalize().unique())
    shares = target_shares(cfg, signal).reindex(days).ffill()
    open_px = p.groupby(p.index.normalize()).first()
    cost = cost_bps / 10_000
    q_eth, q_btc, usdc = 0.0, 0.0, float(INITIAL_USDC)
    last, trades, paid = None, 0, 0.0
    held = np.zeros((len(days), 3))
    for i, d in enumerate(days):
        want = (shares.at[d, "eth"], shares.at[d, "btc"])
        if want != last:
            pe, pb = open_px.at[d, "eth"], open_px.at[d, "btc"]
            value = q_eth * pe + q_btc * pb + usdc
            moved = abs(want[0] * value - q_eth * pe) + abs(want[1] * value - q_btc * pb)
            fee = moved * cost
            value -= fee
            q_eth, q_btc = want[0] * value / pe, want[1] * value / pb
            usdc = value * (1 - want[0] - want[1])
            last, trades, paid = want, trades + (moved > 1), paid + fee
        held[i] = (q_eth, q_btc, usdc)
    held = pd.DataFrame(held, index=days, columns=["eth", "btc", "usdc"]).reindex(p.index, method="ffill")
    nav = held["eth"] * p["eth"] + held["btc"] * p["btc"] + held["usdc"]
    in_market = (shares["eth"] + shares["btc"]).reindex(p.index, method="ffill")
    return {"nav": nav, "trades": trades, "cost $": paid, "in market": float((in_market > 0).mean())}


YEARS = ("2022", "2023", "2024", "2025")


def stats(nav: pd.Series, lo: str, hi: str) -> dict:
    seg = nav.loc[lo:hi]
    seg = seg[seg.index < hi]
    years = (seg.index[-1] - seg.index[0]).days / 365.25
    total = seg.iloc[-1] / seg.iloc[0] - 1
    dd = (seg / seg.cummax() - 1).min()
    annual = (1 + total) ** (1 / years) - 1
    return {"total": total, "annual": annual, "maxDD": dd, "calmar": annual / -dd if dd < 0 else np.nan}


def yearly(nav: pd.Series) -> dict:
    return {y: stats(nav, f"{y}-01-01", f"{int(y) + 1}-01-01")["total"] for y in YEARS}


def holds(prices: pd.DataFrame, start: str) -> dict:
    p = prices.loc[start:]
    return {"hold_btc": p["btc"] / p["btc"].iloc[0], "hold_eth": p["eth"] / p["eth"].iloc[0],
            "hold_50eth_50btc": 0.5 * p["eth"] / p["eth"].iloc[0] + 0.5 * p["btc"] / p["btc"].iloc[0]}


def grid(prices, signal, cost_bps) -> tuple[pd.DataFrame, dict]:
    """Every config over the in-sample years. The holdout is cut off here on purpose."""
    rows, navs = [], {}
    for cfg in build_grid():
        res = simulate(cfg, prices, signal, IN_SAMPLE[0], cost_bps)
        nav = res["nav"][res["nav"].index < IN_SAMPLE[1]]
        navs[cfg.name] = nav
        rows.append({"run": cfg.name, "gate": cfg.gate, "span": cfg.ema_span, "band": cfg.band, "mix": cfg.mix,
                     **yearly(nav), **stats(nav, *IN_SAMPLE), "trades": res["trades"], "cost $": res["cost $"],
                     "in market": res["in market"]})
    for name, nav in holds(prices, IN_SAMPLE[0]).items():
        nav = nav[nav.index < IN_SAMPLE[1]]
        rows.append({"run": name, **yearly(nav), **stats(nav, *IN_SAMPLE)})
    return pd.DataFrame(rows).set_index("run"), navs


def walk_forward(table: pd.DataFrame, navs: dict, prices, signal, cost_bps) -> pd.DataFrame:
    """
    Expanding window: choose on 2022..y-1 by Calmar or total return, hold for year y.
    The 2026 pick is chosen on 2022-2025 and its test year is the holdout.
    """
    configs = {c.name: c for c in build_grid()}
    rows = []
    for test in ("2023", "2024", "2025", "2026"):
        train = ("2022-01-01", f"{test}-01-01")
        scores = {n: stats(nav, *train) for n, nav in navs.items()}
        for score in ("calmar", "total"):
            pick = max(scores, key=lambda n: scores[n][score])
            nav = simulate(configs[pick], prices, signal, f"{test}-01-01", cost_bps)["nav"]
            row = {"test": test, "score": score, "pick": pick,
                   **{f"test {k}": v for k, v in stats(nav, f"{test}-01-01", f"{int(test) + 1}-01-01").items()}}
            if test in YEARS:
                year = table.loc[list(navs), test]
                row.update({"rank": int(year.rank(ascending=False)[pick]), "of": len(year), "median config": year.median()})
            rows.append(row)
    return pd.DataFrame(rows)


def start_months(prices, signal, cost_bps, first="2022-01-01", last="2025-01-01") -> pd.DataFrame:
    """CANDIDATES started on the first of every month, run to the end of the in-sample period."""
    rows = []
    for s in pd.date_range(first, last, freq="MS"):
        s = str(s.date())
        for cfg in CANDIDATES:
            nav = simulate(cfg, prices, signal, s, cost_bps)["nav"]
            rows.append({"start": s, "run": cfg.name, **stats(nav, s, IN_SAMPLE[1])})
        for name, nav in holds(prices, s).items():
            rows.append({"start": s, "run": name, **stats(nav, s, IN_SAMPLE[1])})
    return pd.DataFrame(rows)


def holdout(prices, signal, cost_bps) -> pd.DataFrame:
    rows = []
    for cfg in CANDIDATES:
        res = simulate(cfg, prices, signal, HOLDOUT, cost_bps)
        rows.append({"run": cfg.name, **stats(res["nav"], HOLDOUT, "2100-01-01"), "trades": res["trades"]})
    for name, nav in holds(prices, HOLDOUT).items():
        rows.append({"run": name, **stats(nav, HOLDOUT, "2100-01-01")})
    return pd.DataFrame(rows).set_index("run")


PCT = set(YEARS) | {"total", "annual", "maxDD", "in market", "test total", "test annual", "test maxDD", "median config",
                    "min", "25%", "50%", "75%", "max"}


def pct(frame: pd.DataFrame) -> str:
    shown = frame.copy()
    for c in shown.columns:
        if c in PCT:
            shown[c] = shown[c].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    return shown.round(2).to_string()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cost", type=float, default=10, help="cost per trade in bps of the notional moved")
    cli = parser.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    tag = f"c{cli.cost:g}"
    prices, eth_close, ratio_close = load_prices()
    signal = build_signal(eth_close, ratio_close)
    print(f"prices {prices.index[0]} ~ {prices.index[-1]}, signal ~ {signal.index[-1].date()}, cost {cli.cost:g} bps")

    table, navs = grid(prices, signal, cli.cost)
    table.to_csv(f"{RESULT_DIR}/grid_{tag}.csv")
    pd.DataFrame(navs).resample("1D").last().to_csv(f"{RESULT_DIR}/nav_grid_{tag}.csv")
    cols = ["2022", "2023", "2024", "2025", "total", "annual", "maxDD", "calmar", "trades", "in market"]
    body = table[table["gate"].notna()]
    with pd.option_context("display.width", 250):
        print("\n== in-sample 2022-2025, top 25 by calmar ==")
        print(pct(body.sort_values("calmar", ascending=False)[cols].head(25)))
        print("\n== candidates and holds ==")
        print(pct(table.loc[[c.name for c in CANDIDATES] + ["hold_btc", "hold_eth", "hold_50eth_50btc"], cols]))
        print("\n== median by mix / gate (in-sample) ==")
        print(pct(body.groupby("mix")[["total", "maxDD", "calmar"]].median()))
        print(pct(body.groupby("gate")[["total", "maxDD", "calmar"]].median()))

        starts = start_months(prices, signal, cli.cost)
        starts.to_csv(f"{RESULT_DIR}/starts_{tag}.csv", index=False)
        print("\n== start months 2022-01 ~ 2025-01, annualised to 2025-12-31 ==")
        print(pct(starts.groupby("run")["annual"].describe()[["min", "25%", "50%", "75%", "max"]]))

        wf = walk_forward(table, navs, prices, signal, cli.cost)
        wf.to_csv(f"{RESULT_DIR}/walk_forward_{tag}.csv", index=False)
        print("\n== walk-forward (2026 row is holdout) ==")
        print(pct(wf.set_index(["test", "score"])))

        ho = holdout(prices, signal, cli.cost)
        ho.to_csv(f"{RESULT_DIR}/holdout_{tag}.csv")
        print(f"\n== HOLDOUT {HOLDOUT} ~ {prices.index[-1].date()} ==")
        print(pct(ho))
