"""
Overnight batch of reports/single_pool_loop.md (H5 - H10): the H2 - H4 machinery of pool_lp_windows.py on more pools,
chains and fee tiers. pool_lp_windows.py is left untouched (H4b runs from it); this file reuses its strategies.

Pools (token order and fee read on chain 2026-10-07; quote = the token results are counted in):
  99ac  Ethereum  WBTC / USDC 0.3%   quote USDC     88e6  Ethereum  USDC / WETH 0.05%  quote USDC
  c696  Arbitrum  WETH / USDC 0.05%  quote USDC     0e48  Arbitrum  WBTC / USDC 0.05%  quote USDC
  4585  Ethereum  WBTC / WETH 0.05%  quote WETH     2f5e  Arbitrum  WBTC / WETH 0.05%  quote WETH
  9db9  Ethereum  WBTC / USDT 0.3%   quote USDT
Capital $100k for stable-quoted pools, 40 WETH for WETH-quoted ones (single_pool_backtest.py's size).

Everything else is pool_lp_windows.py: hourly out-of-range re-centre, swaps in the same pool, swap fee + impact
N x N / (L sqrt(P)) + gas subtracted, 12-month windows from every quarter start (from the first quarter start on or
after the pool's first day, the last ending 2026-09-30), each from cash. Gas: Ethereum as before (in ETH for
WETH-quoted pools); Arbitrum $0.20 per LP action (add, remove, collect) and $0.05 per swap (arbitrum_check.py).

Gates (state on day d from the close of day d-1 vs its EMA, ewm adjust=False): stable pools use the BTC gate from
99ac (the live baseline's signal, also for ETH pools); WBTC/WETH pools use the ratio gate from 4585 (on = WBTC strong
against WETH; Arbitrum gets mainnet's signal). On = hold the base (WBTC or WETH), off = the quote.

Verdicts, fixed before the run (commit of this file). n = windows of the pool, halves = first and second half of
the windows in time order, rally windows = the pool's 50/50 hold above +50%.
  ungated version passes if its excess (over holding its first position's base share)
    1. median > 0,  2. > 0 in at least 75% of the windows,  3. median > 0 in both halves,
    4. if there are >= 2 rally windows, median >= -10% over them.
  gated LP passes if (LP net - its control's net) meets 1-3. Controls: same gate, on = spot at the LP's first share.
  H5   BTC/ETH: a version "works" if it passes on 4585 and on 2f5e.
  H6   down-skew elsewhere (88e6, c696, 0e48): holds on a pool if sd_33_10 passes, its matched excess has a median
       > 0, and at least 2 of sd_25_10, sd_33_10, sd_50_10 pass.
  H7   the BTC gate with ranges on 88e6 (ETH/USDC): as H4b, each gated LP against its control.
  H8   H4b at EMA50 and EMA200 on 99ac: a gated LP that passed H4b is robust if it also passes at both spans.
       Listed for every gated LP.
  H9   skew_down map on 99ac, k_down - 1 in {20, 40, 60}% x k_up - 1 in {3, 7, 20}%: a region if >= 6 of 9 have
       median excess > 0 and median matched excess > 0. Descriptive otherwise.
  H10  capital on 99ac: sd_33_10 and w20 at $10k and $1M. sd_33_10 scales if its $1M median excess > 0.
  H11  the gated set reproduced on 9db9, c696 and 0e48: a gated LP reproduces on a pool if it passes there.
  H6 is also run on 4585 and 2f5e, judged the same way.
At the end, digest.csv stacks every summary_<set>.csv.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python pool_lp_batch.py --set h5_4585 [--workers 4]
  PYTHONPATH=../.. python pool_lp_batch.py --test       # 10 days of one version per new pool
"""
import argparse
import glob
import math
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool
from pool_lp_windows import Config30, GatedPool, RangePool, eth_daily, share_of
from single_pool_backtest import KEY
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS, load_market, usdc, usdt, wbtc, weth

RESULT_DIR = "result/pool-lp-batch"
LAST_DAY = date(2026, 9, 30)
ARB_GAS_USD = {"AddLiquidityAction": 0.20, "RemoveLiquidityAction": 0.20, "CollectFeeAction": 0.20, "SwapAction": 0.05}


@dataclass(frozen=True)
class Pool:
    address: str
    chain: str
    token0: TokenInfo
    token1: TokenInfo
    quote: TokenInfo
    fee_pct: float  # 0.3 or 0.05
    spacing: int
    first: date


POOLS = {
    "99ac": Pool("0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35", "ethereum", wbtc, usdc, usdc, 0.3, 60, date(2021, 5, 5)),
    "88e6": Pool("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "ethereum", usdc, weth, usdc, 0.05, 10, date(2021, 5, 5)),
    "c696": Pool("0xC6962004f452bE9203591991D15f6b388e09E8D0", "arbitrum", weth, usdc, usdc, 0.05, 10, date(2023, 6, 9)),
    "0e48": Pool("0x0E4831319A50228B9e450861297aB92dee15B44F", "arbitrum", wbtc, usdc, usdc, 0.05, 10, date(2023, 6, 28)),
    "4585": Pool("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", "ethereum", wbtc, weth, weth, 0.05, 10, date(2021, 5, 6)),
    "2f5e": Pool("0x2f5e87C9312fa29aed5c179E456625D79015299c", "arbitrum", wbtc, weth, weth, 0.05, 10, date(2023, 1, 1)),
    "9db9": Pool("0x9Db9e0e53058C89e5B94e29621a205198648425B", "ethereum", wbtc, usdt, usdt, 0.3, 60, date(2021, 5, 5)),
}
GATE_SOURCE = {"99ac": "99ac", "88e6": "99ac", "c696": "99ac", "0e48": "99ac", "4585": "4585", "2f5e": "4585",
               "9db9": "99ac"}


@dataclass(frozen=True)
class ConfigX(Config30):
    pool_key: str = "99ac"
    ema: int = 100

    def pool(self) -> UniV3Pool:
        p = POOLS[self.pool_key]
        return UniV3Pool(token0=p.token0, token1=p.token1, fee=p.fee_pct, quote_token=p.quote, tick_spacing=p.spacing)


def cfg(pool_key: str, name: str, width: float = 0.0, up: float = 0.0, initial: float | None = None,
        **kw) -> ConfigX:
    p = POOLS[pool_key]
    if initial is None:
        initial = 100_000 if p.quote != weth else 40.0
    return ConfigX(name, p.address, p.token0, p.token1, p.quote, initial, width, up=up, pool_key=pool_key, **kw)


def ungated(pool_key: str) -> list[ConfigX]:
    return [cfg(pool_key, "w20", 0.20), cfg(pool_key, "sd_33_10", 0.33, 0.10), cfg(pool_key, "su_10_33", 0.10, 0.33)]


def gated_set(pool_key: str, ema: int = 100) -> list[ConfigX]:
    g = dict(gated=True, ema=ema)
    return [cfg(pool_key, "g_up", 0.01, 0.40, on="range", **g), cfg(pool_key, "g_sd", 0.33, 0.10, on="range", **g),
            cfg(pool_key, "g_sym", 0.20, on="range", **g),
            cfg(pool_key, "g_down", on="spot", off="range", off_width=0.40, off_up=0.01, **g),
            cfg(pool_key, "g_spot97", on="spot", spot_weight=share_of(1.01, 1.40), **g),
            cfg(pool_key, "g_spot26", on="spot", spot_weight=share_of(1.33, 1.10), **g),
            cfg(pool_key, "g_spot50", on="spot", spot_weight=0.5, **g), cfg(pool_key, "g_spot100", on="spot", **g)]


def skew_family(pool_key: str) -> list[ConfigX]:
    return [cfg(pool_key, "w20", 0.20), cfg(pool_key, "sd_33_10", 0.33, 0.10), cfg(pool_key, "sd_25_10", 0.25, 0.10),
            cfg(pool_key, "sd_50_10", 0.50, 0.10)]


SETS = {
    "h5_4585": ungated("4585") + gated_set("4585"),
    "h6_88e6": skew_family("88e6"),
    "h7_88e6": gated_set("88e6"),
    "h5_2f5e": ungated("2f5e") + gated_set("2f5e"),
    "h6_c696": skew_family("c696"),
    "h6_0e48": skew_family("0e48"),
    "h8_ema50": gated_set("99ac", 50),
    "h8_ema200": gated_set("99ac", 200),
    "h9_map": [cfg("99ac", f"sd_{round(d * 100)}_{round(u * 100)}", d, u)
               for d in (0.20, 0.40, 0.60) for u in (0.03, 0.07, 0.20)],
    "h10_cap": [cfg("99ac", f"{n}_{tag}", w, u, initial=c) for c, tag in ((10_000, "10k"), (1_000_000, "1m"))
                for n, w, u in (("sd_33_10", 0.33, 0.10), ("w20", 0.20, 0.0))],
    "h11_9db9": gated_set("9db9"),
    "h6_4585": skew_family("4585"),
    "h6_2f5e": skew_family("2f5e"),
    "h11_c696": gated_set("c696"),
    "h11_0e48": gated_set("0e48"),
}
CONTROL = {"g_up": "g_spot97", "g_sd": "g_spot26", "g_sym": "g_spot50", "g_down": "g_spot100"}


def raw_price_scale(p: Pool) -> tuple[bool, float]:
    """(quote is token1, 10^(dec0 - dec1)): base price in quote = P_raw x scale, or 1 / (P_raw x scale)."""
    return p.quote == p.token1, 10.0 ** (p.token0.decimal - p.token1.decimal)


def gate(source: str, span: int) -> pd.Series:
    """On day d if the source pool's base price closed day d-1 above its EMA (every file from the pool's first day)."""
    os.makedirs(RESULT_DIR, exist_ok=True)
    path = f"{RESULT_DIR}/gate_{source}_ema{span}.csv"
    if not os.path.exists(path):
        p = POOLS[source]
        files = sorted(glob.glob(f"../real-data/{p.address}/*.minute.csv"))
        df = pd.concat((pd.read_csv(f, usecols=["timestamp", "closeTick"]) for f in files), ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        tick = pd.to_numeric(df.set_index("timestamp").sort_index()["closeTick"], errors="coerce").dropna()
        quote_is_1, scale = raw_price_scale(p)
        raw = np.power(1.0001, tick) * scale
        close = (raw if quote_is_1 else 1 / raw).resample("1D").last().ffill()
        ema = close.ewm(span=span, adjust=False).mean()
        on = (close > ema).shift(1, fill_value=False)
        pd.DataFrame({"close": close, "ema": ema, "gate": on}).to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)["gate"].astype(bool)


def window_starts(pool_key: str) -> list[date]:
    first = POOLS[pool_key].first
    return [s for s in (date(y, m, 1) for y in range(2022, 2026) for m in (1, 4, 7, 10)) if s >= first]


def window_end(start: date) -> date:
    end = (pd.Timestamp(start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()
    return min(end, LAST_DAY)


def run(c: ConfigX, start: date, end: date) -> dict:
    started = time.time()
    p = POOLS[c.pool_key]
    base = p.token1 if p.quote == p.token0 else p.token0
    data, _ = load_market(KEY, c.pool(), p.address, start, end, None, chain=p.chain)
    price = data["price"].astype(float)  # base in quote
    market = UniLpMarket(KEY, c.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(p.quote, Decimal(c.initial))
    actuator.set_price(pd.DataFrame({base.name: price, p.quote.name: 1.0}, index=price.index), p.quote)
    strategy = GatedPool(c, gate(GATE_SOURCE[c.pool_key], c.ema)) if c.gated else RangePool(c)
    actuator.strategy = strategy
    actuator.run(print_result=False)

    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    eth = eth_daily()
    liq = data["currentLiquidity"].astype(float)
    quote_is_1, scale = raw_price_scale(p)
    costs, swap_fee, impact = {}, 0.0, 0.0
    for a in actuator.actions:
        ts = pd.Timestamp(a.timestamp)
        name = type(a).__name__
        eth_usd = float(eth.asof(ts.normalize()))
        cost = 0.0
        if p.chain == "arbitrum":
            cost += ARB_GAS_USD.get(name, 0.0) / (eth_usd if p.quote == weth else 1.0)
        elif name in GAS_UNITS:
            in_eth = GAS_UNITS[name] * GAS_GWEI.get(ts.year, GAS_GWEI[2025]) * 1e-9
            cost += in_eth if p.quote == weth else in_eth * eth_usd
        if name == "SwapAction":
            px = float(price.asof(ts))
            notional = float(a.amount) * (px if a.amount.unit.upper() == base.name.upper() else 1.0)  # in quote
            swap_fee += float(a.fee) * (px if a.fee.unit.upper() == base.name.upper() else 1.0)
            p_raw = (px if quote_is_1 else 1 / px) / scale  # token1 raw per token0 raw
            raw1 = notional * (1.0 if quote_is_1 else 1 / px) * 10 ** p.token1.decimal
            hit = notional * raw1 / (float(liq.asof(ts)) * math.sqrt(p_raw))
            impact += hit
            cost += hit
        costs[ts] = costs.get(ts, 0.0) + cost
    paid = pd.Series(costs, dtype=float).sort_index().cumsum()
    net = nav - (paid.reindex(nav.index, method="ffill").fillna(0.0) if len(paid) else 0.0)
    weight = pd.Series(dict(strategy.weights), dtype=float)
    tag = f"{c.pool_key}_{c.name}_ema{c.ema}_{start}" if c.gated else f"{c.pool_key}_{c.name}_{start}"
    pd.DataFrame({"net": net, "price": price.reindex(net.index)}).to_csv(f"{RESULT_DIR}/nav_{tag}.csv")
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    ev.to_csv(f"{RESULT_DIR}/events_{tag}.csv", index=False)
    r = net.iloc[-1] / net.iloc[0] - 1
    move = price.iloc[-1] / price.iloc[0] - 1
    share = float("nan") if c.gated else c.wbtc_share()
    w_avg = float(weight.mean()) if len(weight) else float("nan")
    daily = price.resample("1D").last().pct_change().dropna()
    matched = float(np.prod(1 + w_avg * daily) - 1)
    gas = float(paid.iloc[-1]) - impact if len(paid) else 0.0
    return {"pool": c.pool_key, "version": c.name, "ema": c.ema, "start": start, "end": end, "net": r,
            "base_share": share, "hold": share * move, "hold5050": 0.5 * move, "excess": r - share * move,
            "w_avg": w_avg, "excess_matched": r - matched,
            "swap_fee": swap_fee / c.initial, "impact": impact / c.initial, "gas": gas / c.initial,
            "recentres": int((ev["kind"] == "recentre").sum()), "switches": int(ev["kind"].isin(["on", "off"]).sum()),
            "maxDD": float((net / net.cummax() - 1).min()), "secs": round(time.time() - started)}


def checks(x: pd.Series, hold5050: pd.Series | None = None) -> dict:
    """x and hold5050 indexed by window start."""
    x = x.sort_index()
    half = len(x) // 2
    c = {"median > 0": x.median() > 0, ">= 75% > 0": (x > 0).sum() >= math.ceil(0.75 * len(x)),
         "both halves median > 0": x.iloc[:half].median() > 0 and x.iloc[half:].median() > 0}
    if hold5050 is not None:
        rally = hold5050.reindex(x.index) > 0.5
        if rally.sum() >= 2:
            c["rally median >= -10%"] = x[rally].median() >= -0.10
    return c


def summarize(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    nets = t.pivot(index="start", columns="version", values="net")
    for v, g in t.groupby("version", sort=False):
        g = g.set_index("start")
        row = {"version": v, "n": len(g), "median_excess": g["excess"].median(),
               "median_matched": g["excess_matched"].median(), "w_avg": g["w_avg"].mean()}
        if v in CONTROL:
            x = nets[v] - nets[CONTROL[v]]
            c = checks(x)
            row.update(median_excess=x.median(), positive=int((x > 0).sum()), vs=CONTROL[v])
        elif v.startswith("g_"):
            c = {}
            row.update(vs="(control)", vs_5050=(g["net"] - g["hold5050"]).median(),
                       vs_base=(g["net"] - 2 * g["hold5050"]).median())
        else:
            c = checks(g["excess"], g["hold5050"])
            row["positive"] = int((g["excess"] > 0).sum())
        row["verdict"] = ("PASS" if all(c.values()) else "fail: " + "; ".join(k for k, ok in c.items() if not ok)) if c else ""
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=list(SETS))
    p.add_argument("--test", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    eth_daily()  # fill the caches before the workers read them
    for src in ("99ac", "4585"):
        for span in (50, 100, 200):
            gate(src, span)
    if a.test:
        for c in (SETS["h6_88e6"][1], SETS["h6_c696"][1], SETS["h6_0e48"][1], SETS["h5_4585"][1], SETS["h5_2f5e"][1],
                  SETS["h5_4585"][3], SETS["h10_cap"][2]):
            print(pd.Series(run(c, date(2024, 3, 1), date(2024, 3, 10))).to_string(), flush=True)
        return
    tasks = [(c, s, window_end(s)) for c in SETS[a.set] for s in window_starts(SETS[a.set][0].pool_key)]
    with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(run, tasks, chunksize=1)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/windows_{a.set}.csv", index=False)
    s = summarize(t)
    s.to_csv(f"{RESULT_DIR}/summary_{a.set}.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(s.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
