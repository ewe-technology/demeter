"""
H46 - H48 of reports/plan_2026-10-19_gate_lp_options.md (registered in 3eeef95): a gate x one-pool LP, seven options.
H49 (added after H48, as the plan says): each H48 pick and its control in H47's n slices at $10k, $100k and $1M,
against 1 slice; the book is the mean of the slices. H50 is added once H49 has results.

  H46  the gate, on spot books only (no Demeter): BTC and ETH candidates, out of sample on Binance daily closes
       (2018-04-01 .. 2021-12-31) and in sample on the pools' hourly closes (2022-01-01 .. 2026-09-30, 24 decision
       hours). The rule of plan 2.3 picks one gate per asset; written to result/gate-lp-options/h46_choice.json.
  H47  1, 3 or 6 slices, on spot books with the H46 gate; the rule of plan 3.2; h47_choice.json.
  H48  the seven options in Demeter on hourly bars, 1 slice at UTC 00, out of range checked once a day at 00:00,
       each against its spot control with the same gate (plan 1.4); the rules of plan 1.6 and 4.3.

Gates (state known at day d + hour h, from the close of the day that ends then; pool_lp_batch.gate's convention):
  ema N   close > ewm(span=N, adjust=False)      sma N   close > mean of the last N closes
  ts N    close > the close N days before
A spec is "<pool>:<kind>:<N>"; 99ac is BTC in USD, 88e6 ETH in USD. An ETH book may use a BTC spec (cross-asset).

Spot books (H46, H47): on = 100% of the asset, off = stablecoin. A switch decided at t trades at the close before t;
costs 10 bps (BTC) or 11 bps (ETH) of the traded value, no gas (H43). Hourly marks for drawdowns.

Demeter runs (H48), costs as pool_lp_batch.run: Demeter's swap fee, impact N x N / (L sqrt P) uncapped, gas at each
year's gwei (2026: 3) converted into the quote (net_3gwei also kept). Pools quoted in a stablecoin are counted in it
(USDT taken as USD). Pools quoted in WBTC or WETH (A1, A2, B1) leave the pool for USDC while off: Demeter runs the
book in the quote with off = all quote token, and the USD book converts at each switch, paying 10 bps (WBTC) or 11
bps (WETH) plus one swap's gas; while off the USD value stays put. Their controls go through the same conversion.
B1 takes 4585 as its main pool and 0xCBCd as the replication pool, as C1 - C4 do with their 0.3% / other pools.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python gate_lp_options.py --cache          # closes and hourly market data, one pool at a time
  PYTHONPATH=../.. python gate_lp_options.py --accept         # must match H4b and H26 before anything else
  PYTHONPATH=../.. python gate_lp_options.py --h46            # then --h47
  PYTHONPATH=../.. python gate_lp_options.py --h48 --workers 2 [--only C1 C2] [--limit n]
  PYTHONPATH=../.. python gate_lp_options.py --report
  PYTHONPATH=../.. python gate_lp_options.py --h59-check      # then --h59 (reports/plan_2026-10-21_c1_drawdown.md)
"""
import argparse
import dataclasses
import glob
import json
import math
import multiprocessing
import os
import pickle
import time
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, TokenInfo
from demeter.uniswap import UniLpMarket
import pool_lp_batch as batch
import pool_lp_robust as robust
import pool_lp_windows as windows_mod
from pool_lp_batch import Pool
from pool_lp_windows import GatedPool, eth_daily, share_of
from single_pool_backtest import KEY
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS, load_market, usdc, usdt, wbtc, weth

RESULT_DIR = "result/gate-lp-options"
ROWS_DIR = f"{RESULT_DIR}/rows"
CACHE_DIR = f"{RESULT_DIR}/cache"
LAST_DAY = date(2026, 9, 30)
IN_FROM, IN_TO = "2022-01-01", "2026-09-30 23:00"
OOS_FROM, OOS_TO = "2018-04-01", "2021-12-31"
BINANCE = {"btc": "binance_btcusdt_1d.csv", "eth": "binance_ethusdt_1d.csv"}
SPOT_BPS = {"btc": 10, "eth": 11}
USD = 100_000

cbbtc = TokenInfo(name="cbbtc", decimal=8)
wsteth = TokenInfo(name="wsteth", decimal=18)
batch.POOLS.update({
    "8ad5": Pool("0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8", "ethereum", usdc, weth, usdc, 0.3, 60, date(2021, 5, 5)),
    "cbcd": Pool("0xCBCdF9626bC03E24f779434178A73a0B4bad62eD", "ethereum", wbtc, weth, weth, 0.3, 60, date(2021, 5, 5)),
    "e8f7": Pool("0xe8f7c89C5eFa061e340f2d2F206EC78FD8f7e124", "ethereum", wbtc, cbbtc, wbtc, 0.01, 1, date(2024, 10, 13)),
    "1098": Pool("0x109830a1AAaD605BbF02a9dFA7B0B92EC2FB7dAa", "ethereum", wsteth, weth, weth, 0.01, 1, date(2024, 1, 1)),
    "5653": Pool("0x56534741CD8B152df6d48AdF7ac51f75169A83b2", "ethereum", wbtc, usdt, usdt, 0.05, 10, date(2021, 6, 11)),
})
ROUTE_HOP_BPS = 1  # H63: USDC <-> USDT in a 0.01% pool, impact left out
ASSET_SRC = {"btc": "99ac", "eth": "88e6"}


# ---------------------------------------------------------------- closes and gates

def hourly_close(src: str) -> pd.Series:
    """Base price in the quote at the end of each hour (label = hour start), from closeTick as pool_lp_batch.gate."""
    path = f"{CACHE_DIR}/close_{src}.csv"
    if not os.path.exists(path):
        os.makedirs(CACHE_DIR, exist_ok=True)
        p = batch.POOLS[src]
        files = sorted(glob.glob(f"../real-data/{p.address}/*.minute.csv"))
        df = pd.concat((pd.read_csv(f, usecols=["timestamp", "closeTick"]) for f in files), ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        tick = pd.to_numeric(df.set_index("timestamp").sort_index()["closeTick"], errors="coerce").dropna()
        quote_is_1, scale = batch.raw_price_scale(p)
        raw = np.power(1.0001, tick) * scale
        (raw if quote_is_1 else 1 / raw).resample("1h").last().rename("close").to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)["close"]


def daily_close(src: str, hour: int) -> pd.Series:
    """The close of each day running from `hour`, labelled at the day's start (pool_lp_batch.gate's resample)."""
    return hourly_close(src).resample("1D", offset=f"{hour}h").last().ffill()


def signal(close: pd.Series, kind: str, n: int) -> pd.Series:
    if kind == "ema":
        ref = close.ewm(span=n, adjust=False).mean()
    elif kind == "sma":
        ref = close.rolling(n).mean()
    elif kind == "ts":
        ref = close.shift(n)
    elif kind == "all":  # always on: the fixed LP benchmark with no gate
        return pd.Series(True, index=close.index)
    else:
        raise ValueError(kind)
    return (close > ref).fillna(False).astype(bool)


def gate_series(spec: str, hour: int = 0) -> pd.Series:
    """On from the time the day's close is known (the next label), as pool_lp_batch.gate."""
    src, kind, n = spec.split(":")
    on = signal(daily_close(src, hour), kind, int(n))
    return on.shift(1, fill_value=False).astype(bool)


def binance_close(asset: str) -> pd.Series:
    df = pd.read_csv(BINANCE[asset], parse_dates=["date"]).set_index("date")
    return df["close"].astype(float)


# ---------------------------------------------------------------- spot books (H46, H47)

def spot_book_hourly(price: pd.Series, gate: pd.Series, bps: float, lo: str, hi: str) -> pd.Series:
    """Hourly NAV from 1 in cash. A state known at t holds from the hour labelled t; trades at the close before t."""
    p = price.loc[:hi].ffill()
    p = p.loc[pd.Timestamp(lo) - pd.Timedelta(hours=1):]
    hold = gate.reindex(p.index, method="ffill").fillna(False).astype(float).iloc[1:]
    r = (p / p.shift(1) - 1).iloc[1:]
    switch = hold.diff().abs().fillna(hold.iloc[0])
    return ((1 + r * hold) * (1 - switch * bps * 1e-4)).cumprod()


def spot_book_daily(close: pd.Series, on: pd.Series, bps: float, lo: str, hi: str) -> pd.Series:
    """Daily NAV from 1 in cash: day d holds on[d] (decided on the close of d-1), trading at that close (H43)."""
    c = close.loc[:hi]
    c = c.loc[pd.Timestamp(lo) - pd.Timedelta(days=1):]
    hold = on.reindex(c.index).fillna(False).astype(float).iloc[1:]
    r = (c / c.shift(1) - 1).iloc[1:]
    switch = hold.diff().abs().fillna(hold.iloc[0])
    return ((1 + r * hold) * (1 - switch * bps * 1e-4)).cumprod()


def max_dd(nav: pd.Series) -> float:
    return float((nav / nav.cummax() - 1).min())


def total(nav: pd.Series) -> float:
    """Spot books start from 1 before the first bar, so the last value minus 1 includes the entry cost."""
    return float(nav.iloc[-1] - 1)


def candidates(asset: str, btc_pick: str | None = None) -> dict[str, tuple[str, str, int]]:
    """name -> (signal asset, kind, n). ETH adds BTC EMA100 and BTC's pick (if it is not EMA100)."""
    own = {f"{k}{n}": (asset, k, n) for k, n in (("ema", 50), ("ema", 100), ("ema", 200), ("sma", 200),
                                                    ("ts", 30), ("ts", 90), ("ts", 180))}
    if asset == "eth":
        own["btc_ema100"] = ("btc", "ema", 100)
        if btc_pick and btc_pick != "ema100":
            k, n = split_name(btc_pick)
            own[f"btc_{btc_pick}"] = ("btc", k, n)
    return own


def split_name(name: str) -> tuple[str, int]:
    k = name.rstrip("0123456789")
    return k, int(name[len(k):])


def spec_of(cand: tuple[str, str, int]) -> str:
    sig_asset, k, n = cand
    return f"{ASSET_SRC[sig_asset]}:{k}:{n}"


def h46_metrics(asset: str, cands: dict) -> pd.DataFrame:
    bps = SPOT_BPS[asset]
    price = hourly_close(ASSET_SRC[asset])
    hold_h = price.loc[pd.Timestamp(IN_FROM) - pd.Timedelta(hours=1):IN_TO].ffill()
    hold_h = hold_h / hold_h.iloc[0]
    b = binance_close(asset)
    hold_d = b.loc[pd.Timestamp(OOS_FROM) - pd.Timedelta(days=1):OOS_TO]
    hold_d = hold_d / hold_d.iloc[0]
    ref = gate_series(f"{ASSET_SRC[asset]}:ema:100", 0).loc[IN_FROM:IN_TO]
    rows = []
    for name, cand in cands.items():
        oos_on = signal(binance_close(cand[0]), cand[1], cand[2]).shift(1, fill_value=False)
        oos = spot_book_daily(b, oos_on, bps, OOS_FROM, OOS_TO)
        books = {h: spot_book_hourly(price, gate_series(spec_of(cand), h), bps, IN_FROM, IN_TO) for h in range(24)}
        tot = pd.Series({h: total(n) for h, n in books.items()})
        dds = pd.Series({h: max_dd(n) for h, n in books.items()})
        g0 = gate_series(spec_of(cand), 0).loc[IN_FROM:IN_TO]
        rows.append({"asset": asset, "gate": name, "M1_oos_total": total(oos), "M2_oos_dd": max_dd(oos),
                     "M3_in_total_median": tot.median(), "M4_in_total_worst": tot.min(),
                     "M5_in_dd_median": dds.median(), "in_dd_worst": dds.min(), "in_total_h00": tot[0],
                     "switches_h00": int(g0.astype(int).diff().abs().sum()),
                     "same_state_as_own_ema100": float((g0 == ref.reindex(g0.index)).mean())})
    t = pd.DataFrame(rows)
    t["hold_oos_total"], t["hold_oos_dd"] = total(hold_d), max_dd(hold_d)
    t["hold_in_total"], t["hold_in_dd"] = total(hold_h), max_dd(hold_h)
    return t


METRICS = ["M1_oos_total", "M3_in_total_median", "M4_in_total_worst", "M5_in_dd_median"]  # higher is better


def h46_pick(t: pd.DataFrame, incumbent: str) -> tuple[str, pd.DataFrame]:
    """Plan 2.3: eligibility, mean rank over M1, M3, M4, M5, and the incumbent stays unless beaten on >= 3 of 4."""
    t = t.copy()
    t["eligible"] = ((t["M1_oos_total"] > t["hold_oos_total"]) & (t["M2_oos_dd"] >= t["hold_oos_dd"] + 0.10)
                     & (t["M5_in_dd_median"] >= t["hold_in_dd"] + 0.10))
    e = t[t["eligible"]].copy()
    t["rank"] = np.nan
    if e.empty:
        return incumbent, t
    e["rank"] = e[METRICS].rank(ascending=False, method="average").mean(axis=1)
    t.loc[e.index, "rank"] = e["rank"]
    e = e.sort_values(["rank", "switches_h00"])
    top = e.iloc[0]
    if top["gate"] == incumbent:
        return incumbent, t
    inc = t[t["gate"] == incumbent].iloc[0]
    if not inc["eligible"]:
        return str(top["gate"]), t
    better = sum(top[m] > inc[m] for m in METRICS)
    return (str(top["gate"]) if better >= 3 else incumbent), t


def run_h46():
    tb = h46_metrics("btc", candidates("btc"))
    btc_pick, tb = h46_pick(tb, "ema100")
    te = h46_metrics("eth", candidates("eth", btc_pick))
    eth_pick, te = h46_pick(te, "btc_ema100")
    t = pd.concat([tb, te], ignore_index=True)
    t.to_csv(f"{RESULT_DIR}/h46_metrics.csv", index=False)
    choice = {"btc": spec_of(candidates("btc")[btc_pick]), "eth": spec_of(candidates("eth", btc_pick)[eth_pick]),
              "btc_name": btc_pick, "eth_name": eth_pick}
    with open(f"{RESULT_DIR}/h46_choice.json", "w") as f:
        json.dump(choice, f, indent=1)
    show(t)
    print(choice)


def run_h47():
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        choice = json.load(f)
    rows, picks = [], {}
    for asset in ("btc", "eth"):
        price = hourly_close(ASSET_SRC[asset])
        books = {h: spot_book_hourly(price, gate_series(choice[asset], h), SPOT_BPS[asset], IN_FROM, IN_TO)
                 for h in range(24)}
        res = {}
        for n in (1, 3, 6):
            step = 24 // n
            g = []
            for h in range(step):
                nav = pd.concat([books[h + k * step] for k in range(n)], axis=1).mean(axis=1)
                g.append({"asset": asset, "n": n, "offset": h, "total": total(nav), "dd": max_dd(nav)})
            rows += g
            g = pd.DataFrame(g)
            res[n] = (g["total"].min(), g["dd"].min(), g["total"].median(), g["dd"].median())
        w6, d6 = res[6][0], res[6][1]
        picks[asset] = next(n for n in (1, 3, 6) if res[n][0] >= w6 - 0.05 and res[n][1] >= d6 - 0.02)
        for n, (w, d, tm, dm) in res.items():
            print(f"H47 {asset} n={n}: worst total {w:+.4f}, worst dd {d:+.4f}, median total {tm:+.4f}, "
                  f"median dd {dm:+.4f}")
        print(f"H47 {asset} -> {picks[asset]} slice(s)")
    pd.DataFrame(rows).to_csv(f"{RESULT_DIR}/h47_offsets.csv", index=False)
    with open(f"{RESULT_DIR}/h47_choice.json", "w") as f:
        json.dump(picks, f)


# ---------------------------------------------------------------- Demeter runs (H48)

@dataclasses.dataclass(frozen=True)
class ConfigG(robust.ConfigR):
    gate_spec: str = "99ac:ema:100"
    option: str = ""
    hourly_check: bool = False  # acceptance only: GatedPool's hourly out-of-range check (H4b)
    brake: bool = False  # H53: gate off and the price below the ladder at a check -> sell to the quote until gate on
    slow_spec: str = ""  # H54: gate off, the ladder only while this slower gate is on, else the quote
    dd_budget: float = 0.0  # H59: gate off, the ladder is the book x (1 - drawdown / dd_budget), clipped to [0, 1]
    time_cap: int = 0  # H60: gate off for this many days -> sell to the quote until gate on
    hourly_down: bool = False  # H62: below the ladder at any full hour -> re-centre (the upper edge stays daily)
    vol_target: float = 0.0  # H64: gate off, the ladder is the book x min(1, vol_target / 30-day vol)
    lp_budget: float = 0.0  # H66: C1 over the live gate (shadow books) this far below its high -> no ladder until a new high
    inv_cap: float = 0.0  # H67: gate off, the book's BTC share above this at a full hour -> trim the ladder back to it
    inv_refill: str = "recentre"  # H67: "recentre" re-places the whole book; "spell" keeps the trimmed quote out till gate off
    ladder_size: float = 0.0  # H67's fixed ladder: every gate-off placement holds the book x this
    route: str = ""  # H63: each swap at the cheaper of this pool and the LP pool (costs after the run)
    route_block: bool = False  # acceptance only: the route priced at infinity


def gcfg(option: str, pool_key: str, name: str, gate_spec: str, width: float = 0.0, up: float = 0.0,
         hourly_check: bool = False, **kw) -> ConfigG:
    p = batch.POOLS[pool_key]
    return ConfigG(name, p.address, p.token0, p.token1, p.quote, USD, width, up=up, pool_key=pool_key, gated=True,
                   daily_check=not hourly_check, hourly_check=hourly_check, gate_spec=gate_spec, option=option, **kw)


def quote_usd(token: TokenInfo) -> pd.Series | None:
    """USD per quote token by hour (label = hour start), None for stablecoins."""
    if token in (usdc, usdt):
        return None
    return hourly_close("99ac" if token == wbtc else "88e6").ffill()  # hours without a trade are NaN in the closes


def hourly_market(pool_key: str, start: date, end: date) -> pd.DataFrame:
    """Hourly Demeter data from a per-year cache (each year loaded alone from the minute files)."""
    p = batch.POOLS[pool_key]
    parts = []
    for y in range(start.year, end.year + 1):
        path = f"{CACHE_DIR}/market_{pool_key}_{y}.pkl"
        if not os.path.exists(path):
            os.makedirs(CACHE_DIR, exist_ok=True)
            lo, hi = max(date(y, 1, 1), p.first), min(date(y, 12, 31), LAST_DAY)
            pool = batch.ConfigX("x", p.address, p.token0, p.token1, p.quote, 1, 0, pool_key=pool_key).pool()
            data, _ = load_market(KEY, pool, p.address, lo, hi, "1h", chain=p.chain)
            tmp = f"{path}.{os.getpid()}"
            with open(tmp, "wb") as f:
                pickle.dump(data, f)
            os.replace(tmp, path)
        with open(path, "rb") as f:
            parts.append(pickle.load(f))
    d = pd.concat(parts)
    return d.loc[pd.Timestamp(start):pd.Timestamp(end) + pd.Timedelta(hours=23)]


def gas_quote(ts: pd.Timestamp, name: str, p: Pool, eth: pd.Series, q_usd: pd.Series | None,
              gwei: float | None) -> float:
    """One action's gas in the quote: ETH for WETH books (pool_lp_batch.run), USD / (USD per quote) otherwise."""
    units = GAS_UNITS.get(name)
    if not units:
        return 0.0
    in_eth = units * (gwei if gwei is not None else GAS_GWEI.get(ts.year, GAS_GWEI[2025])) * 1e-9
    if p.quote == weth:
        return in_eth
    usd_cost = in_eth * float(eth.asof(ts.normalize()))
    return usd_cost if q_usd is None else usd_cost / float(q_usd.asof(ts))


def run(c: ConfigG, start: date, end: date, bar: str | None = "1h", kind: str = "window") -> dict:
    started = time.time()
    p = batch.POOLS[c.pool_key]
    base = p.token1 if p.quote == p.token0 else p.token0
    q_usd = quote_usd(p.quote)
    if bar is None:
        data, _ = load_market(KEY, c.pool(), p.address, start, end, None, chain=p.chain)
    else:
        data = hourly_market(c.pool_key, start, end)
    price = data["price"].astype(float)
    initial = c.initial if q_usd is None else c.initial / float(q_usd.asof(price.index[0]))
    market = UniLpMarket(KEY, c.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(p.quote, Decimal(initial))
    actuator.set_price(pd.DataFrame({base.name: price, p.quote.name: 1.0}, index=price.index), p.quote)
    gate = gate_series(c.gate_spec, c.gate_hour)  # H49's slices read and switch at their own hour (delay = gate_hour)
    if c.hourly_check:
        strategy = GatedPool(c, gate)
    else:
        if c.dd_budget or c.time_cap or c.hourly_down or c.vol_target or c.lp_budget or c.inv_cap or c.ladder_size:
            strategy = CapGated(c, gate, vol_30d() if c.vol_target else None,
                                rel_series(c.pool_key) if c.lp_budget else None)
        elif c.brake:
            strategy = BrakeGated(c, gate)
        elif c.slow_spec:
            strategy = SlowGated(c, gate, gate_series(c.slow_spec, c.gate_hour))
        else:
            strategy = (HalfRobust if c.off == "half" else robust.RobustGated)(c, gate)
    actuator.strategy = strategy
    actuator.run(print_result=False)

    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    eth = eth_daily()
    liq = data["currentLiquidity"].astype(float)
    quote_is_1, scale = batch.raw_price_scale(p)
    if c.route:  # H63: the route pool's liquidity; a hop USDC <-> USDT only for books with an LP in a USDC pool
        alt = batch.POOLS[c.route]
        alt_liq = hourly_market(c.route, start, end)["currentLiquidity"].astype(float)
        hop = alt.quote != p.quote and "range" in (c.on, c.off)
    costs, costs3, swap_fee, impact = {}, {}, 0.0, 0.0
    routed = swaps = 0
    saved = paid_main = paid_chosen = traded = gas_paid = 0.0
    for a in actuator.actions:
        ts = pd.Timestamp(a.timestamp)
        name = type(a).__name__
        cost = gas_quote(ts, name, p, eth, q_usd, None)
        cost3 = gas_quote(ts, name, p, eth, q_usd, 3)
        gas_paid += cost
        if name == "SwapAction":
            px = float(price.asof(ts))
            notional = float(a.amount) * (px if a.amount.unit.upper() == base.name.upper() else 1.0)  # in quote
            fee_q = float(a.fee) * (px if a.fee.unit.upper() == base.name.upper() else 1.0)
            swap_fee += fee_q
            p_raw = (px if quote_is_1 else 1 / px) / scale  # token1 raw per token0 raw
            raw1 = notional * (1.0 if quote_is_1 else 1 / px) * 10 ** p.token1.decimal
            hit = notional * raw1 / (float(liq.asof(ts)) * math.sqrt(p_raw))
            impact += hit
            extra, extra3 = hit, hit  # on top of the pool fee Demeter already took
            if c.route:
                swaps += 1
                main = fee_q + hit
                lq = float(alt_liq.asof(ts)) if ts >= alt_liq.index[0] else float("nan")
                alt_cost = alt_cost3 = math.inf
                if not c.route_block and lq > 0:  # NaN fails too: no data, no route
                    alt_cost = notional * alt.fee_pct / 100 + notional * raw1 / (lq * math.sqrt(p_raw))
                    alt_cost3 = alt_cost
                    if hop:
                        alt_cost += notional * ROUTE_HOP_BPS * 1e-4 + gas_quote(ts, name, p, eth, q_usd, None)
                        alt_cost3 += notional * ROUTE_HOP_BPS * 1e-4 + gas_quote(ts, name, p, eth, q_usd, 3)
                if alt_cost < main:
                    routed += 1
                    saved += main - alt_cost
                    extra, extra3 = alt_cost - fee_q, alt_cost3 - fee_q
                    gas_paid += gas_quote(ts, name, p, eth, q_usd, None) if hop else 0.0
                traded += notional
                paid_main += main
                paid_chosen += min(main, alt_cost)
            cost += extra
            cost3 += extra3
        costs[ts] = costs.get(ts, 0.0) + cost
        costs3[ts] = costs3.get(ts, 0.0) + cost3

    def after(cs: dict) -> pd.Series:
        paid = pd.Series(cs, dtype=float).sort_index().cumsum()
        return nav - (paid.reindex(nav.index, method="ffill").fillna(0.0) if len(paid) else 0.0)

    net_q, net_q3 = after(costs), after(costs3)
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    if q_usd is None:
        usd, usd3 = net_q, net_q3
    else:
        state = on_state(ev, net_q.index)
        asset = "btc" if p.quote == wbtc else "eth"
        usd = to_usd(net_q, state, q_usd, asset, eth, None, initial)
        usd3 = to_usd(net_q3, state, q_usd, asset, eth, 3, initial)
    tag = f"{c.option}_{c.pool_key}_{c.name}_{kind}_{start}"  # a continuous book starts on its first window's day
    os.makedirs(f"{RESULT_DIR}/nav", exist_ok=True)
    pd.DataFrame({"usd": usd, "usd_3gwei": usd3, "price": price.reindex(usd.index)}).to_parquet(
        f"{RESULT_DIR}/nav/{tag}.parquet")
    ev.to_csv(f"{RESULT_DIR}/nav/events_{tag}.csv", index=False)
    if getattr(strategy, "lp_shares", None):  # H67: the LP's share of the book at every gate-off full hour
        pd.DataFrame(strategy.lp_shares, columns=["t", "lp_share", "btc_share"]).to_csv(
            f"{RESULT_DIR}/nav/lpshare_{tag}.csv", index=False)
    paid_all = sum(costs.values())
    out = {}
    if c.route:
        out = {"swaps": swaps, "routed": routed, "route_saved": saved / initial,
               "bps_main": paid_main / traded * 1e4 if traded else 0.0,
               "bps_chosen": paid_chosen / traded * 1e4 if traded else 0.0}
    return {**out, "option": c.option, "pool": c.pool_key, "version": c.name, "gate": c.gate_spec, "start": str(start),
            "end": str(end), "net": float(usd.iloc[-1] / usd.iloc[0] - 1),
            "net_3gwei": float(usd3.iloc[-1] / usd3.iloc[0] - 1),
            "swap_fee": swap_fee / initial, "impact": impact / initial,
            "gas": (gas_paid if c.route else paid_all - impact) / initial,
            "recentres": int(ev["kind"].isin(["recentre", "recentre_h"]).sum()),
            "switches": int(ev["kind"].isin(["on", "off"]).sum()),
            "maxDD": max_dd(usd), "secs": round(time.time() - started)}


def on_state(ev: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    sw = ev[ev["kind"].isin(["on", "off"])].copy()
    s = pd.Series((sw["kind"] == "on").to_numpy(), index=pd.DatetimeIndex(pd.to_datetime(sw["t"])))
    s = s.groupby(level=0).last()
    return s.reindex(index, method="ffill").fillna(False).astype(bool)


def to_usd(net_q: pd.Series, on: pd.Series, q_usd: pd.Series, asset: str, eth: pd.Series, gwei: float | None,
           initial: float) -> pd.Series:
    """
    The USD book of a pool quoted in WBTC or WETH: while on it follows net_q x USD per quote; a switch converts at that
    bar, paying the spot bps and one swap's gas; while off it stays put (net_q's own costs still come off).
    """
    idx = net_q.index
    q = q_usd.reindex(idx, method="ffill").to_numpy()
    eth_px = eth.reindex(idx.normalize(), method="ffill").to_numpy()
    g = np.array([gwei if gwei is not None else GAS_GWEI.get(y, GAS_GWEI[2025]) for y in idx.year], dtype=float)
    swap_gas = GAS_UNITS["SwapAction"] * g * 1e-9 * eth_px
    nq, st = net_q.to_numpy(), on.to_numpy()
    out = np.empty(len(nq))
    usd_prev, nq_prev, was_on, scale = float(initial * q[0]), float(initial), False, 1.0  # the run's own capital
    bps = SPOT_BPS[asset] * 1e-4
    for i in range(len(nq)):
        if st[i]:
            if not was_on:  # USDC -> quote token at this bar; Demeter's book scaled from its value before the entry
                scale = (usd_prev * (1 - bps) - swap_gas[i]) / (q[i] * nq_prev)
            out[i] = nq[i] * q[i] * scale
        elif was_on:  # quote token -> USDC at this bar
            out[i] = nq[i] * q[i] * scale * (1 - bps) - swap_gas[i]
        else:
            out[i] = usd_prev * (nq[i] / nq_prev if nq_prev else 1.0)
        usd_prev, nq_prev, was_on = out[i], nq[i], bool(st[i])
    return pd.Series(out, index=idx)


# ---------------------------------------------------------------- H48 grid

MAIN_REP = {"A1": ("e8f7", None), "A2": ("1098", None), "B1": ("4585", "cbcd"), "C1": ("99ac", "9db9"),
            "C2": ("99ac", "9db9"), "C3": ("8ad5", "88e6"), "C4": ("8ad5", "88e6")}
CENTRED = {"A1": ["w0.1", "w0.25", "w0.5", "w1"], "A2": ["w0.25", "w0.5", "w1"], "B1": ["w10", "w20", "w50"],
           "C1": ["w10", "w20", "w30"], "C2": ["w10", "w20", "w30"], "C3": ["w10", "w20"],
           "C4": ["w10", "w20", "w30"]}
SHAPES = {"A2": ["up_02_08"], "C1": ["sd_33_10", "ladder"], "C2": ["sd_33_10"], "C4": ["sd_33_10"]}
LISTED = {("C3", "ladder"), ("A2", "hold_wsteth")}


def ladder(w_down: float, w_up: float) -> dict:
    """Gate-off range [p / (1 + w_down), p (1 + w_up)]; w_up is set even when equal (RobustGated reads 0 as p x 1.00)."""
    return dict(off="range", off_width=w_down, off_up=w_up)


def h48_configs(btc_gate: str, eth_gate: str) -> list[ConfigG]:
    out = []
    for w in (0.001, 0.0025, 0.005, 0.01):  # A1 WBTC/cbBTC: on LP, off USDC; control on WBTC (cash in the quote)
        out.append(gcfg("A1", "e8f7", f"w{w * 100:g}", btc_gate, width=w, on="range"))
    out.append(gcfg("A1", "e8f7", "ctl", btc_gate, on="cash"))
    for w in (0.0025, 0.005, 0.01):  # A2 wstETH/WETH: on LP, off USDC; control on WETH; listed: on wstETH
        out.append(gcfg("A2", "1098", f"w{w * 100:g}", eth_gate, width=w, on="range"))
    out.append(gcfg("A2", "1098", "up_02_08", eth_gate, width=0.002, up=0.008, on="range"))
    out.append(gcfg("A2", "1098", "ctl", eth_gate, on="cash"))
    out.append(gcfg("A2", "1098", "hold_wsteth", eth_gate, on="spot"))
    for pk in ("4585", "cbcd"):  # B1 WBTC/WETH: on LP, off USDC; control on the LP's first mix (0.5 WBTC)
        for w in (0.10, 0.20, 0.50):
            out.append(gcfg("B1", pk, f"w{w * 100:g}", btc_gate, width=w, on="range"))
        out.append(gcfg("B1", pk, "ctl", btc_gate, on="spot", spot_weight=0.5))
    for pk in MAIN_REP["C1"]:
        for w in (0.10, 0.20, 0.30):  # C1 on WBTC, off an LP in the pool; control g_spot100
            out.append(gcfg("C1", pk, f"w{w * 100:g}", btc_gate, on="spot", **ladder(w, w)))
        out.append(gcfg("C1", pk, "sd_33_10", btc_gate, on="spot", **ladder(0.33, 0.10)))
        out.append(gcfg("C1", pk, "ladder", btc_gate, on="spot", **ladder(0.40, 0.01)))
        out.append(gcfg("C1", pk, "ctl", btc_gate, on="spot"))
        for w in (0.10, 0.20, 0.30):  # C2 on an LP in the pool, off the stablecoin; controls at the LP's WBTC share
            out.append(gcfg("C2", pk, f"w{w * 100:g}", btc_gate, width=w, on="range"))
        out.append(gcfg("C2", pk, "sd_33_10", btc_gate, width=0.33, up=0.10, on="range"))
        out.append(gcfg("C2", pk, "ctl50", btc_gate, on="spot", spot_weight=0.5))
        out.append(gcfg("C2", pk, "ctl26", btc_gate, on="spot", spot_weight=share_of(1.33, 1.10)))
    for pk in MAIN_REP["C3"]:
        for w in (0.10, 0.20):  # C3 on WETH, off an LP in the pool
            out.append(gcfg("C3", pk, f"w{w * 100:g}", eth_gate, on="spot", **ladder(w, w)))
        out.append(gcfg("C3", pk, "ladder", eth_gate, on="spot", **ladder(0.40, 0.01)))
        out.append(gcfg("C3", pk, "ctl", eth_gate, on="spot"))
        for w in (0.10, 0.20, 0.30):  # C4 on an LP in the pool, off the stablecoin
            out.append(gcfg("C4", pk, f"w{w * 100:g}", eth_gate, width=w, on="range"))
        out.append(gcfg("C4", pk, "sd_33_10", eth_gate, width=0.33, up=0.10, on="range"))
        out.append(gcfg("C4", pk, "ctl50", eth_gate, on="spot", spot_weight=0.5))
        out.append(gcfg("C4", pk, "ctl26", eth_gate, on="spot", spot_weight=share_of(1.33, 1.10)))
    return out


def control_of(option: str, version: str) -> str:
    if option in ("C2", "C4"):
        return "ctl26" if version == "sd_33_10" else "ctl50"
    return "ctl"


def six_months(start: date) -> date:
    return min((pd.Timestamp(start) + pd.DateOffset(months=6) - pd.Timedelta(days=1)).date(), LAST_DAY)


def windows(option: str) -> list[tuple[date, date]]:
    if option in ("A1", "A2"):
        first = date(2024, 10, 13) if option == "A1" else date(2024, 1, 1)
        starts = [s for s in (date(y, m, 1) for y in (2024, 2025, 2026) for m in (1, 4, 7, 10))
                  if first <= s <= date(2026, 4, 1)]
        if option == "A1":
            starts = [first] + starts
        return [(s, six_months(s)) for s in starts]
    return [(s, batch.window_end(s)) for s in batch.window_starts("99ac")]


def continuous(option: str) -> tuple[date, date]:
    return {"A1": date(2024, 10, 13), "A2": date(2024, 1, 1)}.get(option, date(2022, 1, 1)), LAST_DAY


def row_path(c: ConfigG, start: date, kind: str) -> str:
    return f"{ROWS_DIR}/{c.option}_{c.pool_key}_{c.name}_{kind}_{start}.json"


def task(c: ConfigG, start: date, end: date, kind: str) -> dict:
    path = row_path(c, start, kind)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    r = run(c, start, end, None if kind == "minute" else "1h", kind)
    r["kind"] = kind
    os.makedirs(ROWS_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(r, f)
    print(f"{time.strftime('%H:%M:%S')} {c.option} {c.pool_key} {c.name} {kind} {start} net {r['net']:+.4f} "
          f"{r['secs']}s", flush=True)
    return r


def h48_tasks(only: list[str] | None) -> list[tuple]:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        ch = json.load(f)
    out = []
    for c in h48_configs(ch["btc"], ch["eth"]):
        if only and c.option not in only:
            continue
        out += [(c, s, e, "window") for s, e in windows(c.option)]
        s, e = continuous(c.option)
        out.append((c, s, e, "continuous"))
    order = ["C1", "C2", "C3", "C4", "B1", "A1", "A2"]  # plan 7
    return sorted(out, key=lambda t: order.index(t[0].option))


def judge(x: pd.Series, dd_lp: float, dd_ctl: float) -> dict:
    n, h = len(x), math.ceil(len(x) / 2)
    return {"median > 0": x.median() > 0, ">= 75% > 0": (x > 0).sum() >= math.ceil(0.75 * n),
            "halves > 0": x.iloc[:h].median() > 0 and x.iloc[h:].median() > 0,
            "dd within 2 pt": dd_lp >= dd_ctl - 0.02}


def report_h48():
    rows = [json.load(open(f)) for f in glob.glob(f"{ROWS_DIR}/*.json")]
    if not rows:
        print("no H48 rows")
        return
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/h48_rows.csv", index=False)
    w = t[t["kind"] == "window"]
    cont = t[t["kind"] == "continuous"].set_index(["option", "pool", "version"])
    out = []
    for (opt, pk), g in w.groupby(["option", "pool"]):
        nets = g.pivot(index="start", columns="version", values="net").sort_index()
        nets3 = g.pivot(index="start", columns="version", values="net_3gwei").sort_index()
        for v in nets.columns:
            ctl = control_of(opt, v)
            if v.startswith("ctl") or ctl not in nets:
                continue
            x = (nets[v] - nets[ctl]).dropna()
            h = math.ceil(len(x) / 2)
            dd_lp, dd_c = cont["maxDD"].get((opt, pk, v), np.nan), cont["maxDD"].get((opt, pk, ctl), np.nan)
            c = judge(x, dd_lp, dd_c)
            gv = g[g["version"] == v]
            out.append({"option": opt, "pool": pk, "version": v, "vs": ctl, "n": len(x), "median": x.median(),
                        "positive": int((x > 0).sum()), "first_half": x.iloc[:h].median(),
                        "second_half": x.iloc[h:].median(), "cont_lp": cont["net"].get((opt, pk, v), np.nan),
                        "cont_ctl": cont["net"].get((opt, pk, ctl), np.nan), "dd_lp": dd_lp, "dd_ctl": dd_c,
                        "pass": all(c.values()), "failed": "; ".join(k for k, ok in c.items() if not ok),
                        "listed": (opt, v) in LISTED, "recentres_med": gv["recentres"].median(),
                        "gas_med": gv["gas"].median(), "impact_med": gv["impact"].median(),
                        "swap_fee_med": gv["swap_fee"].median(),
                        "median_3gwei": (nets3[v] - nets3[ctl]).median()})
    s = pd.DataFrame(out)
    s.to_csv(f"{RESULT_DIR}/h48_summary.csv", index=False)
    show(s)
    picks = h48_pick(s)
    with open(f"{RESULT_DIR}/h48_picks.json", "w") as f:
        json.dump(picks, f, indent=1)
    print(json.dumps(picks, indent=1))


def first3(r) -> bool:
    return bool(r["median"] > 0 and r["positive"] >= math.ceil(0.75 * r["n"]) and r["first_half"] > 0
                and r["second_half"] > 0)


def no_worse(a, b) -> bool:
    """a no worse than b on the four checks of plan 1.6 (A2's up-skew against the centred pick)."""
    return bool(a["median"] >= b["median"] and a["positive"] >= b["positive"] and a["first_half"] >= b["first_half"]
                and a["second_half"] >= b["second_half"] and a["dd_lp"] - a["dd_ctl"] >= b["dd_lp"] - b["dd_ctl"])


def h48_pick(s: pd.DataFrame) -> dict:
    """Plan 4.3: centred widths need a run of >= 2 passing on the main pool (its middle, the wider of two) and the
    replication pool's first three checks on that cell; shapes need a pass on both pools; then the best continuous
    total among what passes."""
    picks = {}
    for opt, (main, rep) in MAIN_REP.items():
        sub = s[s["option"] == opt]
        if sub.empty:
            continue
        r = {(x.pool, x.version): x for _, x in sub.iterrows()}
        best, run_ = [], []
        for v in CENTRED[opt]:
            run_ = run_ + [v] if (main, v) in r and r[(main, v)]["pass"] else []
            if len(run_) > len(best):
                best = run_
        passing = []
        if len(best) >= 2:
            mid = best[len(best) // 2]
            if rep is None or ((rep, mid) in r and first3(r[(rep, mid)])):
                passing.append(mid)
        for v in SHAPES.get(opt, []):
            if (main, v) not in r or not r[(main, v)]["pass"]:
                continue
            if opt == "A2":
                if passing and no_worse(r[(main, v)], r[(main, passing[0])]):
                    passing = [v]
                elif not passing:
                    passing.append(v)
                continue
            if rep is not None and (rep, v) in r and r[(rep, v)]["pass"]:
                passing.append(v)
        pick = max(passing, key=lambda v: r[(main, v)]["cont_lp"]) if passing else None
        picks[opt] = {"pick": pick, "passing": passing, "centred_run": best}
    return picks


# ---------------------------------------------------------------- H49: slices on what H48 picked

CAPITALS = {"10k": 10_000, "100k": 100_000, "1m": 1_000_000}
ASSET_OF = {"A1": "btc", "B1": "btc", "C1": "btc", "C2": "btc", "A2": "eth", "C3": "eth", "C4": "eth"}


def h49_configs() -> list[tuple[ConfigG, int, str]]:
    """(config, slices, capital tag) for each H48 pick and its control: n slices at UTC h, h + 24/n, ... (each its own
    run with 1/n of the capital, gate read and the book switched at its hour), plus 1 slice at $10k and $1M."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        ch = json.load(f)
    with open(f"{RESULT_DIR}/h47_choice.json") as f:
        nsl = json.load(f)
    with open(f"{RESULT_DIR}/h48_picks.json") as f:
        picks = json.load(f)
    base = {(c.option, c.pool_key, c.name): c for c in h48_configs(ch["btc"], ch["eth"])}
    out = []
    for opt, p in picks.items():
        if not p["pick"]:
            continue
        n = int(nsl[ASSET_OF[opt]])
        pk = MAIN_REP[opt][0]
        for v in (p["pick"], control_of(opt, p["pick"])):
            c0 = base[(opt, pk, v)]
            for tag, cap in CAPITALS.items():
                if n > 1:
                    for k in range(n):
                        h = k * 24 // n
                        out.append((dataclasses.replace(c0, name=f"{v}_n{n}_h{h:02d}_{tag}", initial=cap / n,
                                                        gate_hour=h, delay=h, option=f"H49{opt}"), n, tag))
                if tag != "100k":
                    out.append((dataclasses.replace(c0, name=f"{v}_n1_h00_{tag}", initial=cap, option=f"H49{opt}"),
                                1, tag))
    return out


def h49_tasks() -> list[tuple]:
    out = []
    for c, _, _ in h49_configs():
        opt = c.option[3:]
        out += [(c, s, e, "window") for s, e in windows(opt)]
        s, e = continuous(opt)
        out.append((c, s, e, "continuous"))
    return out


def book_nav(option: str, pool: str, names: list[str], start: date, kind: str = "window") -> pd.Series:
    """The book of equal slices: the mean of each slice's USD NAV normalised to its first bar."""
    navs = [pd.read_parquet(f"{RESULT_DIR}/nav/{option}_{pool}_{v}_{kind}_{start}.parquet")["usd"] for v in names]
    return pd.concat([n / n.iloc[0] for n in navs], axis=1).ffill().mean(axis=1)


def report_h49():
    with open(f"{RESULT_DIR}/h48_picks.json") as f:
        picks = json.load(f)
    with open(f"{RESULT_DIR}/h47_choice.json") as f:
        nsl = json.load(f)
    out = {}
    for opt, p in picks.items():
        if not p["pick"]:
            continue
        n = int(nsl[ASSET_OF[opt]])
        if n == 1:
            continue
        pk, v, ctl = MAIN_REP[opt][0], p["pick"], control_of(opt, p["pick"])
        ws = windows(opt)
        cs, _ = continuous(opt)
        for tag in CAPITALS:
            res = {}
            for k in (n, 1):
                if k == 1 and tag == "100k":
                    names = {v: [v], ctl: [ctl]}
                    o = opt
                else:
                    names = {x: ([f"{x}_n{k}_h{h * 24 // k:02d}_{tag}" for h in range(k)] if k > 1
                                 else [f"{x}_n1_h00_{tag}"]) for x in (v, ctl)}
                    o = f"H49{opt}"
                x = pd.Series({s: total(book_nav(o, pk, names[v], s)) - total(book_nav(o, pk, names[ctl], s))
                               for s, _ in ws})
                dd_lp = max_dd(book_nav(o, pk, names[v], cs, "continuous"))
                dd_c = max_dd(book_nav(o, pk, names[ctl], cs, "continuous"))
                c = judge(x, dd_lp, dd_c)
                h = math.ceil(len(x) / 2)
                res[k] = {"median": x.median(), "positive": int((x > 0).sum()), "n": len(x),
                          "halves": (x.iloc[:h].median(), x.iloc[h:].median()), "dd": (dd_lp, dd_c),
                          "pass": all(c.values()), "failed": [kk for kk, ok in c.items() if not ok]}
                print(f"H49 {opt} {v} {k} slice(s) ${tag}: median {x.median():+.4f}, {(x > 0).sum()}/{len(x)}, "
                      f"halves {x.iloc[:h].median():+.4f} / {x.iloc[h:].median():+.4f}, dd {dd_lp:+.4f} vs "
                      f"{dd_c:+.4f} -> {'PASS' if all(c.values()) else 'fail: ' + '; '.join(res[k]['failed'])}")
            out[f"{opt}_{tag}"] = res
        use = n if out[f"{opt}_100k"][n]["pass"] else 1
        out[f"{opt}_use"] = use
        print(f"H49 {opt} -> {use} slice(s)")
    with open(f"{RESULT_DIR}/h49_result.json", "w") as f:
        json.dump(out, f, indent=1, default=float)


# ---------------------------------------------------------------- H50: robustness of what passed H49

H50_NEIGHBOURS = {"A2": {"up_01_09": (0.001, 0.009), "up_03_07": (0.003, 0.007), "up_01_04": (0.001, 0.004),
                         "up_04_16": (0.004, 0.016)}}  # A1's neighbours (w0.1, w0.5) are H48 cells


def h50_items() -> list[tuple[str, str, str]]:
    """(option, pick, control) for every H48 pick that H49 kept (at its slice count; 1 slice here)."""
    with open(f"{RESULT_DIR}/h48_picks.json") as f:
        picks = json.load(f)
    out = []
    for opt, p in picks.items():
        if p["pick"]:
            out.append((opt, p["pick"], control_of(opt, p["pick"])))
    return out


def h50_configs() -> list[tuple[ConfigG, str]]:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        ch = json.load(f)
    base = {(c.option, c.pool_key, c.name): c for c in h48_configs(ch["btc"], ch["eth"])}
    out = []
    for opt, v, ctl in h50_items():
        pk = MAIN_REP[opt][0]
        for x in (v, ctl):
            c0 = base[(opt, pk, x)]
            for k in robust.placebo_shifts():
                out.append((dataclasses.replace(c0, name=f"{x}_s{k:+d}", shift=k, option=f"H50{opt}"), "window"))
            out.append((dataclasses.replace(c0, name=f"{x}_d1", delay=1, option=f"H50{opt}"), "window"))
            out.append((dataclasses.replace(c0, name=f"{x}_min", option=f"H50{opt}"), "minute"))
        for name, (lo, hi) in H50_NEIGHBOURS.get(opt, {}).items():
            out.append((dataclasses.replace(base[(opt, pk, v)], name=name, width=lo, up=hi, option=f"H50{opt}"),
                        "window"))
    return out


def h50_tasks() -> list[tuple]:
    out = []
    for c, kind in h50_configs():
        ws = windows(c.option[3:])
        if kind == "minute":
            out += [(c, s, e, "minute") for s, e in (ws[0], ws[-1])]
        else:
            out += [(c, s, e, "window") for s, e in ws]
    return out


def h50_net(option: str, pool: str, name: str, kind: str, starts: list[date]) -> pd.Series:
    rows = {}
    for s in starts:
        with open(f"{ROWS_DIR}/{option}_{pool}_{name}_{kind}_{s}.json") as f:
            rows[s] = json.load(f)["net"]
    return pd.Series(rows)


def bootstrap(opt: str, pk: str, v: str, ctl: str, draws: int = 10_000, block: int = 30) -> tuple[float, float, float]:
    """H28's block bootstrap on the continuous books' daily returns: annualised (LP - control), 90% interval."""
    s, _ = continuous(opt)
    r = pd.concat([book_nav(opt, pk, [x], s, "continuous").resample("1D").last().pct_change() for x in (v, ctl)],
                  axis=1)
    r = r.dropna().to_numpy()
    n = len(r)

    def ann(a: np.ndarray) -> float:
        g = np.prod(1 + a, axis=0) ** (365 / len(a)) - 1
        return float(g[0] - g[1])

    rng = np.random.default_rng(28)
    k = -(-n // block)
    stats = np.array([ann(r[((rng.integers(0, n, k)[:, None] + np.arange(block)).ravel()[:n]) % n])
                      for _ in range(draws)])
    lo, hi = np.percentile(stats, [5, 95])
    return ann(r), float(lo), float(hi)


def report_h50():
    out = {}
    for opt, v, ctl in h50_items():
        pk = MAIN_REP[opt][0]
        o = f"H50{opt}"
        ws = windows(opt)
        starts = [s for s, _ in ws]
        real = (h50_net(opt, pk, v, "window", starts) - h50_net(opt, pk, ctl, "window", starts)).median()
        meds = pd.Series({k: (h50_net(o, pk, f"{v}_s{k:+d}", "window", starts)
                              - h50_net(o, pk, f"{ctl}_s{k:+d}", "window", starts)).median()
                          for k in robust.placebo_shifts()})
        d1 = h50_net(o, pk, f"{v}_d1", "window", starts) - h50_net(o, pk, f"{ctl}_d1", "window", starts)
        ends = [starts[0], starts[-1]]
        x_min = h50_net(o, pk, f"{v}_min", "minute", ends) - h50_net(o, pk, f"{ctl}_min", "minute", ends)
        x_hour = h50_net(opt, pk, v, "window", ends) - h50_net(opt, pk, ctl, "window", ends)
        gap = (x_hour - x_min).abs().max()
        ann, lo, hi = bootstrap(opt, pk, v, ctl)
        nb = {}
        for name in H50_NEIGHBOURS.get(opt, {}):
            x = h50_net(o, pk, name, "window", starts) - h50_net(opt, pk, ctl, "window", starts)
            nb[name] = (float(x.median()), int((x > 0).sum()))
        for name in CENTRED[opt]:
            if name != v:
                x = h50_net(opt, pk, name, "window", starts) - h50_net(opt, pk, ctl, "window", starts)
                nb[name] = (float(x.median()), int((x > 0).sum()))
        print(f"H50 {opt} {v}: real median {real:+.4f}; placebos >= real {int((meds >= real).sum())}/20, "
              f"median of placebo medians {meds.median():+.4f}")
        print("  placebo medians:", " ".join(f"{k:+d}:{m * 100:+.2f}" for k, m in meds.sort_index().items()))
        print(f"  delay 1 h: median {d1.median():+.4f}, {(d1 > 0).sum()}/{len(d1)} (vs {real:+.4f})")
        print(f"  neighbours (median, > 0): {nb}")
        print(f"  bootstrap: annualised {ann:+.4f}, 90% [{lo:+.4f}, {hi:+.4f}]")
        print(f"  minute vs hourly (LP - control) on {ends}: minute {list(x_min.round(4))}, hourly "
              f"{list(x_hour.round(4))}, max gap {gap:.4f} -> {'within 2 pt' if gap <= 0.02 else 'OVER 2 pt'}")
        out[opt] = {"real": real, "placebo_ge": int((meds >= real).sum()), "placebo_median": meds.median(),
                    "delay1_median": d1.median(), "delay1_pos": int((d1 > 0).sum()), "neighbours": nb,
                    "boot": [ann, lo, hi], "minute_gap": gap}
    with open(f"{RESULT_DIR}/h50_result.json", "w") as f:
        json.dump(out, f, indent=1, default=float)


# ---------------------------------------------------------------- H51, H52: slices with gas, C1's half ladder

class HalfRobust(robust.RobustGated):
    """RobustGated whose gate-off range (off == "half") holds half the book, the rest in the quote; every off placement
    first sells any WBTC (pool_lp_gdown.HalfGated on the daily check)."""

    def go(self, on: bool, price: Decimal, t):
        cfg = self.cfg
        if on or cfg.off != "half":
            return super().go(on, price, t)
        if self.bounds is not None:
            self.remove()
        self.state, self.mode = on, "range"
        self.k = (1 + cfg.off_width, 1 + (cfg.off_up or cfg.off_width))
        self.place(price, 0.0, "off", t)

    def place(self, price: Decimal, width: float, kind: str, t):
        cfg = self.cfg
        if self.state is not False or cfg.off != "half":
            return super().place(price, width, kind, t)
        m = self.markets[KEY]
        btc = self.broker.get_token_balance(cfg.base)
        if btc > 0:
            m.swap(btc, cfg.base, cfg.quote)
        lo, hi = price / Decimal(self.k[0]), price * Decimal(self.k[1])
        t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), self.broker.get_token_balance(cfg.quote) / 2)
        self.bounds = (lo, hi)
        self.events.append((t, kind))


SLICES = (1, 3, 6)


def h51_bases() -> list[tuple[str, str, str, ConfigG]]:
    """(option, pool, version, config at 1 slice, 00 h, $100k): H48's A1, A2 picks, C1's two shapes, H52's half
    ladder, and their controls."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        ch = json.load(f)
    base = {(c.option, c.pool_key, c.name): c for c in h48_configs(ch["btc"], ch["eth"])}
    out = [("A1", "e8f7", v, base[("A1", "e8f7", v)]) for v in ("w0.25", "ctl")]
    out += [("A2", "1098", v, base[("A2", "1098", v)]) for v in ("up_02_08", "ctl")]
    for pk in ("99ac", "9db9"):
        out += [("C1", pk, v, base[("C1", pk, v)]) for v in ("sd_33_10", "ladder", "ctl")]
        out.append(("C1", pk, "half", gcfg("C1", pk, "half", ch["btc"], on="spot", off="half", off_width=0.40,
                                           off_up=0.01)))
    return out


def slice_hours(n: int, h0: int) -> list[int]:
    return [h0 + k * 24 // n for k in range(n)]


def h51_name(v: str, n: int, h: int, tag: str) -> str:
    return f"{v}_n{n}_h{h:02d}_{tag}"


def h51_tasks() -> list[tuple]:
    out = []
    for opt, pk, v, c0 in h51_bases():
        ws = windows(opt)
        cs, ce = continuous(opt)
        for tag, cap in CAPITALS.items():
            for n in SLICES:
                hours = range(24) if tag == "100k" else slice_hours(n, 0)
                for h in hours:
                    c = dataclasses.replace(c0, name=h51_name(v, n, h, tag), initial=cap / n, gate_hour=h, delay=h,
                                            option=f"H51{opt}")
                    out.append((c, cs, ce, "continuous"))
                    if h in slice_hours(n, 0):
                        out += [(c, s, e, "window") for s, e in ws]
    return out


def cagr(nav: pd.Series) -> float:
    days = (nav.index[-1] - nav.index[0]).total_seconds() / 86400
    return float((nav.iloc[-1] / nav.iloc[0]) ** (365.25 / days) - 1)


def h51_stats(opt: str, pk: str, v: str, ctl: str, n: int, tag: str = "100k") -> dict:
    o = f"H51{opt}"
    cs, _ = continuous(opt)
    starts = [s for s, _ in windows(opt)]
    rets = []
    if tag == "100k":
        for h0 in range(24 // n):
            rets.append(cagr(book_nav(o, pk, [h51_name(v, n, h, tag) for h in slice_hours(n, h0)], cs, "continuous")))
    names_v = [h51_name(v, n, h, tag) for h in slice_hours(n, 0)]
    names_c = [h51_name(ctl, n, h, tag) for h in slice_hours(n, 0)]
    x = pd.Series({s: total(book_nav(o, pk, names_v, s)) - total(book_nav(o, pk, names_c, s)) for s in starts})
    lp0, ctl0 = book_nav(o, pk, names_v, cs, "continuous"), book_nav(o, pk, names_c, cs, "continuous")
    c = judge(x, max_dd(lp0), max_dd(ctl0))
    h = math.ceil(len(x) / 2)
    gas = np.mean([json.load(open(f"{ROWS_DIR}/{o}_{pk}_{nm}_continuous_{cs}.json"))["gas"] for nm in names_v])
    return {"opt": opt, "pool": pk, "version": v, "n": n, "capital": tag,
            "W": min(rets) if rets else np.nan, "M": float(np.median(rets)) if rets else np.nan,
            "best": max(rets) if rets else np.nan, "cagr_h0": cagr(lp0), "cagr_ctl_h0": cagr(ctl0),
            "median": x.median(), "positive": int((x > 0).sum()), "windows": len(x),
            "first_half": x.iloc[:h].median(), "second_half": x.iloc[h:].median(),
            "dd_lp": max_dd(lp0), "dd_ctl": max_dd(ctl0), "four_checks": all(c.values()),
            "failed": "; ".join(k for k, ok in c.items() if not ok), "gas_per_slice": float(gas)}


def report_h51():
    rows = []
    for opt, pk, v, _ in h51_bases():
        if v == "ctl":
            continue
        for tag in CAPITALS:
            for n in SLICES:
                rows.append(h51_stats(opt, pk, v, "ctl", n, tag))
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/h51_summary.csv", index=False)
    show(t)
    verdict = {}
    for (opt, pk, v), g in t[t["capital"] == "100k"].groupby(["opt", "pool", "version"], sort=False):
        g = g.set_index("n")
        ok = {n: bool(g.loc[n, "W"] >= g.loc[1, "W"] + 0.01 and g.loc[n, "M"] >= g.loc[1, "M"] - 0.005
                      and g.loc[n, "four_checks"]) for n in (3, 6)}
        verdict[f"{opt}_{pk}_{v}"] = {"use": 3 if ok[3] else 6 if ok[6] else 1, "qualifies": ok,
                                      "one_slice_four_checks": bool(g.loc[1, "four_checks"])}
    for v in ("sd_33_10", "ladder", "half"):  # C1 / H52 turn over only on both pools at the chosen n
        main = verdict[f"C1_99ac_{v}"]
        n = main["use"]
        rep = t[(t["capital"] == "100k") & (t["pool"] == "9db9") & (t["version"] == v) & (t["n"] == n)].iloc[0]
        main["passes"] = bool(n > 1 and rep["four_checks"])
        main["rep_four_checks_at_n"] = bool(rep["four_checks"])
    print(json.dumps(verdict, indent=1))
    with open(f"{RESULT_DIR}/h51_verdict.json", "w") as f:
        json.dump(verdict, f, indent=1)


# ---------------------------------------------------------------- H53 - H55: C1's drawdown

def to_quote(strategy, t, kind: str):
    """Remove the position and sell every base token: the book holds only the quote."""
    if strategy.bounds is not None:
        strategy.remove()
    base = strategy.broker.get_token_balance(strategy.cfg.base)
    if base > 0:
        strategy.markets[KEY].swap(base, strategy.cfg.base, strategy.cfg.quote)
    strategy.mode = "cash"
    strategy.events.append((t, kind))


class BrakeGated(robust.RobustGated):
    """H53: while the gate is off, a daily check that finds the price below the ladder sells to the quote and waits
    for the gate to turn on; the next gate-off spell places a fresh ladder."""

    def on_bar(self, snapshot):
        t = snapshot.timestamp
        price = self.markets[KEY].market_status.data.price
        gate_bar = t.hour == self.cfg.delay and t.minute == 0
        if (self.state is False and self.mode == "range" and gate_bar and self.bounds is not None
                and price < self.bounds[0] and not bool(self.gate.asof(pd.Timestamp(t).normalize()))):
            to_quote(self, t, "brake")
        super().on_bar(snapshot)


class SlowGated(robust.RobustGated):
    """H54: while the gate is off, the ladder only while the slow gate is on; else the quote. Checked daily."""

    def __init__(self, cfg, gate: pd.Series, slow: pd.Series):
        super().__init__(cfg, gate)
        self.slow = slow

    def slow_on(self, t) -> bool:
        return bool(self.slow.asof(pd.Timestamp(t).normalize()))

    def go(self, on: bool, price: Decimal, t):
        if on or self.slow_on(t):
            return super().go(on, price, t)
        self.state = False
        to_quote(self, t, "off")

    def on_bar(self, snapshot):
        t = snapshot.timestamp
        price = self.markets[KEY].market_status.data.price
        gate_bar = t.hour == self.cfg.delay and t.minute == 0
        if (self.state is False and gate_bar and not bool(self.gate.asof(pd.Timestamp(t).normalize()))):
            if self.slow_on(t) and self.mode == "cash":
                self.k = (1 + self.cfg.off_width, 1 + (self.cfg.off_up or self.cfg.off_width))
                self.place(price, 0.0, "slow_on", t)
                self.mode = "range"
            elif not self.slow_on(t) and self.mode == "range":
                to_quote(self, t, "slow_off")
        super().on_bar(snapshot)


def h53_configs() -> list[ConfigG]:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    out = []
    for pk in MAIN_REP["C1"]:
        out.append(gcfg("H53", pk, "brake", btc, on="spot", brake=True, **ladder(0.40, 0.01)))
        out.append(gcfg("H54", pk, "slow200", btc, on="spot", slow_spec="99ac:ema:200", **ladder(0.40, 0.01)))
        for tag, spec in (("ema50", "99ac:ema:50"), ("ema200", "99ac:ema:200"), ("ts30", "99ac:ts:30")):
            out.append(gcfg("H55", pk, f"ladder_{tag}", spec, on="spot", **ladder(0.40, 0.01)))
            out.append(gcfg("H55", pk, f"ctl_{tag}", spec, on="spot"))
    return out


def h53_tasks() -> list[tuple]:
    out = []
    for c in h53_configs():
        out += [(c, s, e, "window") for s, e in windows("C1")]
        s, e = continuous("C1")
        out.append((c, s, e, "continuous"))
    return out


def rows_of(option: str, pool: str, version: str) -> tuple[pd.Series, dict]:
    starts = [s for s, _ in windows("C1")]
    w = pd.Series({s: json.load(open(f"{ROWS_DIR}/{option}_{pool}_{version}_window_{s}.json"))["net"] for s in starts})
    cs, _ = continuous("C1")
    return w, json.load(open(f"{ROWS_DIR}/{option}_{pool}_{version}_continuous_{cs}.json"))


def report_h53():
    out = []
    cases = [("H53", "brake", "C1", "ctl"), ("H54", "slow200", "C1", "ctl"), ("C1", "ladder", "C1", "ctl")]
    cases += [("H55", f"ladder_{t}", "H55", f"ctl_{t}") for t in ("ema50", "ema200", "ts30")]
    cs, _ = continuous("C1")
    for opt, v, copt, ctl in cases:
        for pk in MAIN_REP["C1"]:
            xw, xc = rows_of(opt, pk, v)
            cw, cc = rows_of(copt, pk, ctl)
            x = xw - cw
            c = judge(x, xc["maxDD"], cc["maxDD"])
            h = math.ceil(len(x) / 2)
            evf = f"{RESULT_DIR}/nav/events_{opt}_{pk}_{v}_continuous_{cs}.csv"
            # H48's C1 runs predate the kind in file names; their brake / slow counts are 0 anyway
            ev = pd.read_csv(evf) if os.path.exists(evf) else pd.DataFrame({"t": [], "kind": []})
            out.append({"case": opt, "version": v, "pool": pk, "median": x.median(), "positive": int((x > 0).sum()),
                        "first_half": x.iloc[:h].median(), "second_half": x.iloc[h:].median(),
                        "cont_lp": xc["net"], "cont_ctl": cc["net"], "dd_lp": xc["maxDD"], "dd_ctl": cc["maxDD"],
                        "dd_gap": xc["maxDD"] - cc["maxDD"], "four_checks": all(c.values()),
                        "failed": "; ".join(k for k, ok in c.items() if not ok), "recentres": xc["recentres"],
                        "switches": xc["switches"], "gas": xc["gas"], "brakes": int((ev["kind"] == "brake").sum()),
                        "slow_offs": int((ev["kind"] == "slow_off").sum()) + int((ev["kind"] == "off").sum())
                        if v == "slow200" else 0})
    t = pd.DataFrame(out)
    t.to_csv(f"{RESULT_DIR}/h53_summary.csv", index=False)
    show(t)
    for case in ("H53", "H54"):
        s = t[t["case"] == case].set_index("pool")
        print(f"{case}: 99ac four checks {bool(s.loc['99ac', 'four_checks'])}, 9db9 {bool(s.loc['9db9', 'four_checks'])} -> "
              f"{'C1 turns over' if s['four_checks'].all() else 'only on the main pool' if s.loc['99ac', 'four_checks'] else 'no'}")
    h55 = t[(t["case"] == "H55") & (t["pool"] == "99ac")]
    within = h55[h55["dd_gap"] >= -0.02]["version"].tolist()
    print("H55 reading:", "the drawdown is not the gate's parameter" if not within else f"within 2 pt: {within} (not adopted)")


# ---------------------------------------------------------------- H59 - H62: C1's gate-off exposure capped
# reports/plan_2026-10-21_c1_drawdown.md (registered in 22db440)

class CapGated(robust.RobustGated):
    """H59 - H62 on C1's ladder while the gate is off. dd_budget: every placement (the gate-off one and each re-centre)
    holds the book x s, s = 1 - drawdown / dd_budget clipped to [0, 1], never more than the ladder just removed; the
    rest stays in the quote, and s = 0 holds the quote until the gate turns on. time_cap: N days after the gate-off
    switch, at 00:00, sell to the quote until the gate turns on. lp_budget (H66): at a full hour where the shadow
    books' C1 / live gate ratio (previous bar) is lp_budget below its high, stop: pull the ladder to the quote and
    place none while off, until the ratio makes a new high. hourly_down: a full hour below the lower edge
    re-centres as the daily check does. inv_cap (H67): at a gate-off full hour, the book's BTC share above inv_cap
    trims every position by the share of liquidity that brings it back and sells the WBTC; inv_refill "spell" keeps
    the trimmed quote out of re-centres until the next gate-off. ladder_size (H67's fixed ladder): every gate-off
    placement holds the book x ladder_size. vol_target (H64, H65 with dd_budget): s = min(1, vol_target / 30-day vol)
    (times the dd_budget share), sized from the whole book at every placement. The book and its peak are Demeter's
    own (before gas and impact)."""

    def __init__(self, cfg, gate: pd.Series, vol: pd.Series | None = None, rel: pd.Series | None = None):
        super().__init__(cfg, gate)
        self.vol = vol  # H64: 30-day vol by day, known at that day's 00:00
        self.rel = rel  # H66: C1 / live gate shadow NAVs by hour, the previous bar's value
        self.rel_peak = 0.0
        self.stopped = False
        self.peak = 0.0
        self.outside = 0.0  # quote kept beside a sized ladder in this gate-off spell
        self.off_since = None
        self.lp_shares = []  # H67: (time, LP / book, BTC / book) at gate-off full hours

    def book(self, price: Decimal) -> float:
        btc = self.broker.get_token_balance(self.cfg.base)
        quote = self.broker.get_token_balance(self.cfg.quote)
        if self.bounds is not None:
            s = self.markets[KEY].get_market_balance()
            btc += s.base_in_position + s.base_uncollected
            quote += s.quote_in_position + s.quote_uncollected
        return float(btc * price + quote)

    def go(self, on: bool, price: Decimal, t):
        if not on:
            self.off_since, self.outside = pd.Timestamp(t).normalize(), 0.0
            if self.stopped:  # H66: gate off while stopped holds the quote (as SlowGated)
                self.state = False
                to_quote(self, t, "off")
                return
        return super().go(on, price, t)

    def place(self, price: Decimal, width: float, kind: str, t):
        c = self.cfg
        spell = c.inv_cap and c.inv_refill == "spell"
        if self.state is not False or not (c.dd_budget or c.vol_target or c.ladder_size or spell):
            return super().place(price, width, kind, t)
        v = self.book(price)
        s = 1.0
        if c.vol_target:  # H64 / H65 size from the whole book every time, no cap
            sig = float(self.vol.asof(pd.Timestamp(t).normalize()))
            s = min(1.0, c.vol_target / sig) if sig > 0 else 1.0
        if c.ladder_size:  # H67's fixed ladder, from the whole book every time
            s = c.ladder_size
        if c.dd_budget:
            s *= min(1.0, max(0.0, 1 - (1 - v / self.peak) / c.dd_budget))
        if c.vol_target:
            self.events.append((t, f"s:{s:.4f}"))  # every gate-off placement's share, sized or not
        # H59's dd_budget and H67's spell refill never grow the ladder from the quote within a spell
        lad = v * s if (c.vol_target or c.ladder_size) else min(v * s, v - self.outside)
        if lad >= v:
            return super().place(price, width, kind, t)
        m = self.markets[KEY]
        btc = self.broker.get_token_balance(c.base)
        if btc > 0:
            m.swap(btc, c.base, c.quote)
        if lad <= 0:
            self.mode, self.outside = "cash", v
            self.events.append((t, "zero"))
            return
        # the swap's fee came off the book, and a float back in Decimal can land a hair above the balance
        lad = min(Decimal(lad), self.broker.get_token_balance(c.quote))
        lo, hi = price / Decimal(self.k[0]), price * Decimal(self.k[1])
        t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), lad)
        self.bounds, self.outside = (lo, hi), float(self.broker.get_token_balance(c.quote))
        self.events.append((t, kind))
        self.events.append((t, f"cut:{float(lad) / v:.4f}"))

    def on_bar(self, snapshot):
        c = self.cfg
        t = snapshot.timestamp
        price = self.markets[KEY].market_status.data.price
        if t.minute == 0:
            self.peak = max(self.peak, self.book(price))
        if c.lp_budget and t.minute == 0:
            r = float(self.rel.asof(pd.Timestamp(t)))
            if r == r:  # NaN before the shadow books start
                self.rel_peak = max(self.rel_peak, r)
                if not self.stopped and 1 - r / self.rel_peak >= c.lp_budget:
                    self.stopped = True
                    self.events.append((t, "budget_stop"))
                    if self.state is False and self.mode == "range":
                        to_quote(self, t, "budget_cut")
                elif self.stopped and r >= self.rel_peak:
                    self.stopped = False
                    self.events.append((t, "budget_resume"))
                    if self.state is False and self.mode == "cash":
                        self.k = (1 + c.off_width, 1 + (c.off_up or c.off_width))
                        self.mode = "range"
                        self.place(price, 0.0, "budget_place", t)
        gate_bar = t.hour == c.delay and t.minute == 0
        off_now = self.state is False and not bool(self.gate.asof(pd.Timestamp(t).normalize()))
        if (c.time_cap and gate_bar and off_now and self.mode == "range"
                and (pd.Timestamp(t).normalize() - self.off_since).days >= c.time_cap):
            to_quote(self, t, "timecap")
        if (c.hourly_down and not gate_bar and t.minute == 0 and self.state is False and self.mode == "range"
                and self.bounds is not None and price < self.bounds[0]):
            self.remove()
            self.place(price, 0.0, "recentre_h", t)
        if c.inv_cap and t.minute == 0 and self.state is False and self.mode == "range" and self.bounds is not None:
            self.trim(price, t)
        super().on_bar(snapshot)
        if (c.inv_cap or c.ladder_size) and t.minute == 0 and self.state is False:
            v = self.book(price)
            lp = btc = 0.0
            if self.bounds is not None:
                s = self.markets[KEY].get_market_balance()
                lp = float((s.base_in_position + s.base_uncollected) * price + s.quote_in_position + s.quote_uncollected)
                btc = float((s.base_in_position + s.base_uncollected) * price)
            btc += float(self.broker.get_token_balance(c.base) * price)
            self.lp_shares.append((t, lp / v if v > 0 else 0.0, btc / v if v > 0 else 0.0))

    def trim(self, price: Decimal, t):
        """H67: the book's BTC share above inv_cap -> remove k of every position's liquidity, k = 1 - cap x book / the
        positions' BTC value, collect, and sell every WBTC on the book; the rest of the ladder stays in its range."""
        c = self.cfg
        m = self.markets[KEY]
        s = m.get_market_balance()
        v = self.book(price)
        in_pos = float((s.base_in_position + s.base_uncollected) * price)
        btc = in_pos + float(self.broker.get_token_balance(c.base) * price)
        if v <= 0 or btc <= c.inv_cap * v or in_pos <= 0:
            return
        k = min(1.0, max(0.0, 1 - c.inv_cap * v / in_pos))  # the book's other WBTC is sold below anyway
        for key, pos in list(m.positions.items()):
            part = int(int(pos.liquidity) * k)
            if 0 < part < pos.liquidity:
                m.remove_liquidity(key, part)
        held = self.broker.get_token_balance(c.base)
        if held > 0:
            m.swap(held, c.base, c.quote)
        self.outside = float(self.broker.get_token_balance(c.quote))
        # trim:<BTC share before>:<after>:<WBTC sold, in the quote>
        self.events.append((t, f"trim:{btc / v:.4f}:{self.book_btc_share(price):.4f}:{float(held * price):.2f}"))

    def book_btc_share(self, price: Decimal) -> float:
        v = self.book(price)
        s = self.markets[KEY].get_market_balance() if self.bounds is not None else None
        btc = float(self.broker.get_token_balance(self.cfg.base) * price)
        if s is not None:
            btc += float((s.base_in_position + s.base_uncollected) * price)
        return btc / v if v > 0 else 0.0


H59_VERSIONS = {"H59": {"dd20": dict(dd_budget=0.20), "dd30": dict(dd_budget=0.30), "dd40": dict(dd_budget=0.40)},
                "H60": {"tc30": dict(time_cap=30), "tc60": dict(time_cap=60), "tc90": dict(time_cap=90)},
                "H61": {"dd30_tc60": dict(dd_budget=0.30, time_cap=60)},
                "H62": {"hdown": dict(hourly_down=True)}}
H59_NB = {"dd20": ["dd30"], "dd30": ["dd20", "dd40"], "dd40": ["dd30"], "tc30": ["tc60"], "tc60": ["tc30", "tc90"],
          "tc90": ["tc60"], "dd30_tc60": [], "hdown": []}
WORST_C1 = ("2025-08-14", "2026-06-05")  # H53: the deepest drawdown of H48's C1 ladder
CONT_YEARS = ((LAST_DAY - date(2022, 1, 1)).days + 1) / 365.25


def h59_configs() -> list[ConfigG]:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    return [gcfg(opt, pk, v, btc, on="spot", **kw, **ladder(0.40, 0.01))
            for pk in MAIN_REP["C1"] for opt, vs in H59_VERSIONS.items() for v, kw in vs.items()]


def h59_tasks() -> list[tuple]:
    out = []
    for c in h59_configs():
        out += [(c, s, e, "window") for s, e in windows("C1")]
        s, e = continuous("C1")
        out.append((c, s, e, "continuous"))
    return out


def check_h59():
    """Plan 5: dd40 on the 2022-01 window equals H48's ladder unless it sized a placement (then the first one is
    shown); tc90 on the 2023-04 window (no gate-off spell of 90 days) equals it."""
    cs = {(c.pool_key, c.name): c for c in h59_configs()}
    for v, s in (("dd40", date(2022, 1, 1)), ("tc90", date(2023, 4, 1))):
        r = task(cs[("99ac", v)], s, batch.window_end(s), "window")
        ref = json.load(open(f"{ROWS_DIR}/C1_99ac_ladder_window_{s}.json"))["net"]
        ev = pd.read_csv(f"{RESULT_DIR}/nav/events_{cs[('99ac', v)].option}_99ac_{v}_window_{s}.csv")
        cuts = ev[ev["kind"].str.startswith("cut:") | ev["kind"].isin(["zero", "timecap"])]
        print(f"{v} {s}: {r['net']:.10f} vs C1 ladder {ref:.10f} diff {r['net'] - ref:+.2e}; "
              f"sized / cash events {len(cuts)}" + (f", first {cuts.iloc[0].tolist()}" if len(cuts) else ""))


def calmar_of(row: dict) -> float:
    return ((1 + row["net"]) ** (1 / CONT_YEARS) - 1) / -row["maxDD"]


def nav_of(opt: str, pk: str, v: str) -> pd.Series:
    if opt == "C1":  # H51's single-slice books are H48's C1 bit for bit and keep the run kind in the file name
        opt, v = "H51C1", f"{v}_n1_h00_100k"
    cs, _ = continuous("C1")
    return pd.read_parquet(f"{RESULT_DIR}/nav/{opt}_{pk}_{v}_continuous_{cs}.parquet")["usd"]


def span(nav: pd.Series, a: str, b: str) -> dict:
    cur = nav.loc[a:f"{b} 23:00"]
    before = nav[nav.index < pd.Timestamp(a)]
    x = np.concatenate([[before.iloc[-1] if len(before) else cur.iloc[0]], cur.to_numpy()])
    return {"ret": float(x[-1] / x[0] - 1), "mdd": float((x / np.maximum.accumulate(x) - 1).min())}


def case_table(cases: list[tuple[str, str]], ctl: tuple[str, str], c1: tuple[str, str]) -> pd.DataFrame:
    """One row per (case, pool): the windows against `ctl`, the continuous book, Calmar against `ctl` and `c1`, and
    the listed counts and spans (plan 2026-10-21 section 4)."""
    cs, _ = continuous("C1")
    out = []
    for pk in MAIN_REP["C1"]:
        cw, cc = rows_of(ctl[0], pk, ctl[1])
        lw, lc = rows_of(c1[0], pk, c1[1])
        for opt, v in cases:
            xw, xc = rows_of(opt, pk, v)
            x = xw - cw
            c = judge(x, xc["maxDD"], cc["maxDD"])
            h = math.ceil(len(x) / 2)
            nav = nav_of(opt, pk, v)
            evf = f"{RESULT_DIR}/nav/events_{opt}_{pk}_{v}_continuous_{cs}.csv"
            ev = pd.read_csv(evf) if os.path.exists(evf) else pd.DataFrame({"t": [], "kind": []})
            kind = ev["kind"].astype(str)
            shares = [float(k[2:]) for k in kind if k.startswith("s:")]
            row = {"case": opt, "version": v, "pool": pk, "median": x.median(), "positive": int((x > 0).sum()),
                   "first_half": x.iloc[:h].median(), "second_half": x.iloc[h:].median(),
                   "vs_c1_median": (xw - lw).median(), "cont": xc["net"], "dd": xc["maxDD"], "dd_ctl": cc["maxDD"],
                   "dd_gap": xc["maxDD"] - cc["maxDD"], "calmar": calmar_of(xc), "calmar_ctl": calmar_of(cc),
                   "calmar_c1": calmar_of(lc), "four": all(c.values()),
                   "three": all(ok for k, ok in c.items() if k != "dd within 2 pt"),
                   "failed": "; ".join(k for k, ok in c.items() if not ok), "recentres": xc["recentres"],
                   "switches": xc["switches"], "gas": xc["gas"], "impact": xc["impact"],
                   "cuts": sum(k.startswith("cut:") and float(k[4:]) < 0.9995 for k in kind),  # s < 1 at 4 places
                   "zeros": int((kind == "zero").sum()),
                   "timecaps": int((kind == "timecap").sum()), "hourly_moves": int((kind == "recentre_h").sum())}
            if shares:
                row.update({"placements": len(shares), "s_below_1": sum(s < 0.9995 for s in shares),
                            "s_median": float(np.median(shares))})
            if "routed" in xc:
                row.update({k: xc[k] for k in ("swaps", "routed", "route_saved", "bps_main", "bps_chosen")})
            w = span(nav, *WORST_C1)
            y26 = span(nav, "2026-01-01", "2026-09-30")
            row.update({"worst_ret": w["ret"], "worst_mdd": w["mdd"], "y2026_ret": y26["ret"], "y2026_mdd": y26["mdd"]})
            for y in range(2022, 2027):
                s_ = span(nav, f"{y}-01-01", f"{y}-12-31")
                row[f"ret_{y}"], row[f"mdd_{y}"] = s_["ret"], s_["mdd"]
            out.append(row)
    return pd.DataFrame(out)


def verdict_of(t: pd.DataFrame, nb: dict[str, list[str]]) -> dict:
    """Plan 2026-10-21 section 4: four checks on 99ac, Calmar above both bases, four checks on 9db9, a neighbour."""
    m = t[t["pool"] == "99ac"].set_index("version")
    r = t[t["pool"] == "9db9"].set_index("version")
    verdict = {}
    for v in nb:
        c1 = bool(m.loc[v, "four"])
        c2 = bool(m.loc[v, "calmar"] > m.loc[v, "calmar_ctl"] and m.loc[v, "calmar"] > m.loc[v, "calmar_c1"])
        c3 = bool(r.loc[v, "four"])
        c4 = not nb[v] or any(bool(m.loc[n, "three"] and m.loc[n, "calmar"] > m.loc[n, "calmar_ctl"]) for n in nb[v])
        verdict[v] = {"99ac four": c1, "calmar": c2, "9db9 four": c3, "neighbour": c4, "passes": c1 and c2 and c3 and c4,
                      "main pool only": c1 and c2 and c4 and not c3}
    passing = [v for v, d in verdict.items() if d["passes"]]
    return {"verdict": verdict, "pick": max(passing, key=lambda v: m.loc[v, "calmar"]) if passing else None}


SUMMARY_COLS = ["case", "version", "pool", "median", "positive", "first_half", "second_half", "vs_c1_median", "cont",
                "dd", "dd_gap", "calmar", "four", "failed", "recentres", "cuts", "zeros", "timecaps", "hourly_moves"]


def report_h59():
    cases = [("C1", "ladder"), ("C1", "ctl")] + [(o, v) for o, vs in H59_VERSIONS.items() for v in vs]
    t = case_table(cases, ("C1", "ctl"), ("C1", "ladder"))
    t.to_csv(f"{RESULT_DIR}/h59_summary.csv", index=False)
    show(t[SUMMARY_COLS])
    res = verdict_of(t, H59_NB)
    print(json.dumps(res, indent=1))
    with open(f"{RESULT_DIR}/h59_result.json", "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- H63 - H65: swap route, ladder sized by vol
# reports/plan_2026-10-21_c1_cost_vol.md (registered in 8276d01)

H64_VERSIONS = {"H64": {"vol30": dict(vol_target=0.30), "vol40": dict(vol_target=0.40), "vol50": dict(vol_target=0.50)},
                "H65": {"vol40_dd30": dict(vol_target=0.40, dd_budget=0.30)}}
H64_NB = {"vol30": ["vol40"], "vol40": ["vol30", "vol50"], "vol50": ["vol40"], "vol40_dd30": []}
ROUTE = "5653"


def vol_30d() -> pd.Series:
    """Annualised std of the last 30 daily log returns of 99ac's 00 h close, known at the next day's 00:00."""
    close = daily_close("99ac", 0)
    return (np.log(close).diff().rolling(30).std() * math.sqrt(365)).shift(1)


def h63_configs() -> list[ConfigG]:
    """H64 and H65 at H48's costs, then the bases, H64 and H65 with the route (H63, names ending in _rt)."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    lad = ladder(0.40, 0.01)
    out = [gcfg(opt, pk, v, btc, on="spot", **kw, **lad)
           for pk in MAIN_REP["C1"] for opt, vs in H64_VERSIONS.items() for v, kw in vs.items()]
    for pk in MAIN_REP["C1"]:
        out.append(gcfg("H63", pk, "ladder_rt", btc, on="spot", route=ROUTE, **lad))
        out.append(gcfg("H63", pk, "ctl_rt", btc, on="spot", route=ROUTE))
        for vs in H64_VERSIONS.values():
            for v, kw in vs.items():
                out.append(gcfg("H63", pk, f"{v}_rt", btc, on="spot", route=ROUTE, **kw, **lad))
    return out


def h63_tasks() -> list[tuple]:
    out = []
    for c in h63_configs():
        out += [(c, s, e, "window") for s, e in windows("C1")]
        s, e = continuous("C1")
        out.append((c, s, e, "continuous"))
    return out


def check_h63():
    """Plan cost_vol section 5: T = 1000% equals H48's ladder on 99ac 2022-01; so does the route priced at infinity;
    the real route lists how many swaps it takes and what it saves."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    s = date(2022, 1, 1)
    ref = json.load(open(f"{ROWS_DIR}/C1_99ac_ladder_window_{s}.json"))["net"]
    lad = ladder(0.40, 0.01)
    for c in (gcfg("chk", "99ac", "vol1000", btc, on="spot", vol_target=10.0, **lad),
              gcfg("chk", "99ac", "ladder_rt_block", btc, on="spot", route=ROUTE, route_block=True, **lad),
              gcfg("chk", "99ac", "ladder_rt", btc, on="spot", route=ROUTE, **lad)):
        r = task(c, s, batch.window_end(s), "window")
        extra = {k: r[k] for k in ("swaps", "routed", "route_saved", "bps_main", "bps_chosen") if k in r}
        print(f"{c.name} {s}: {r['net']:.10f} vs C1 ladder {ref:.10f} diff {r['net'] - ref:+.2e} {extra}", flush=True)


def report_h63():
    h64 = [(o, v) for o, vs in H64_VERSIONS.items() for v in vs]
    t48 = case_table([("C1", "ladder"), ("C1", "ctl")] + h64, ("C1", "ctl"), ("C1", "ladder"))
    trt = case_table([("H63", "ladder_rt"), ("H63", "ctl_rt")] + [("H63", f"{v}_rt") for _, v in h64],
                     ("H63", "ctl_rt"), ("H63", "ladder_rt"))
    t48.to_csv(f"{RESULT_DIR}/h64_summary.csv", index=False)
    trt.to_csv(f"{RESULT_DIR}/h63_summary.csv", index=False)
    print("H64, H65 at H48's costs:")
    show(t48[SUMMARY_COLS + [c for c in ("s_below_1", "s_median") if c in t48]])
    print("with the route (H63):")
    show(trt[SUMMARY_COLS + [c for c in ("s_below_1", "s_median", "routed", "swaps", "route_saved", "bps_main",
                                         "bps_chosen") if c in trt]])
    res = {"h48_costs": verdict_of(t48, H64_NB),
           "route": verdict_of(trt, {"ladder_rt": [], **{f"{v}_rt": [f"{n}_rt" for n in ns] for v, ns in H64_NB.items()}})}
    print(json.dumps(res, indent=1))
    with open(f"{RESULT_DIR}/h63_result.json", "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- H66: LP excess-loss budget
# reports/plan_2026-10-21_c1_lp_budget.md (registered in 8ba303f)

H66_VERSIONS = {"lp5": 0.05, "lp10": 0.10, "lp15": 0.15}


def shadow_navs(pk: str) -> tuple[pd.Series, pd.Series]:
    """H51's single-slice C1 ladder and live-gate continuous books (H48 bit for bit): H66's shadow books."""
    return nav_of("C1", pk, "ladder"), nav_of("C1", pk, "ctl")


def rel_series(pk: str) -> pd.Series:
    """C1 / live gate on the shadow books, indexed so that bar t holds bar t - 1's value."""
    lad, ctl = shadow_navs(pk)
    return (lad / ctl.reindex(lad.index)).shift(1)


def h66_configs() -> list[ConfigG]:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    return [gcfg("H66", pk, v, btc, on="spot", lp_budget=b, **ladder(0.40, 0.01))
            for pk in MAIN_REP["C1"] for v, b in H66_VERSIONS.items()]


def h66_tasks() -> list[tuple]:
    out = []
    for c in h66_configs():
        out += [(c, s, e, "window") for s, e in windows("C1")]
        s, e = continuous("C1")
        out.append((c, s, e, "continuous"))
    return out


def check_h66():
    """Plan lp_budget 4: a budget of 1000% never stops and equals H48's ladder on 99ac 2022-01."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    s = date(2022, 1, 1)
    ref = json.load(open(f"{ROWS_DIR}/C1_99ac_ladder_window_{s}.json"))["net"]
    r = task(gcfg("chk", "99ac", "lp1000", btc, on="spot", lp_budget=10.0, **ladder(0.40, 0.01)), s,
             batch.window_end(s), "window")
    print(f"lp1000 {s}: {r['net']:.10f} vs C1 ladder {ref:.10f} diff {r['net'] - ref:+.2e}", flush=True)


def h66_stops(pk: str, v: str) -> list[dict]:
    """Each stop of the continuous book: R at the trigger, its low after, the resume, days stopped (and off), the
    shadow C1's fees missed, and the version over C1 across the stop."""
    from lp_attribution import decompose, segments
    cs, _ = continuous("C1")
    ev = pd.read_csv(f"{RESULT_DIR}/nav/events_H66_{pk}_{v}_continuous_{cs}.csv")
    ev["t"] = pd.to_datetime(ev["t"])
    lad, ctl = shadow_navs(pk)
    rel = lad / ctl.reindex(lad.index)
    mine = nav_of("H66", pk, v)
    tag = f"H51C1_{pk}_ladder_n1_h00_100k_continuous_{cs}"
    sev = pd.read_csv(f"{RESULT_DIR}/nav/events_{tag}.csv")
    df = pd.read_parquet(f"{RESULT_DIR}/nav/{tag}.parquet")
    nav, price = df["usd"].to_numpy(), df["price"].astype(float).ffill().to_numpy()
    _, fe, _, on, _ = decompose(nav, price, segments(df.index, nav, price, sev,
                                                     {"on": ["spot", 1.0], "off": ["range", 1.40, 1.01]}))
    fees = pd.Series(fe, index=df.index)
    off = pd.Series(~on, index=df.index)
    out = []
    stops = ev[ev["kind"] == "budget_stop"]["t"].tolist()
    resumes = ev[ev["kind"] == "budget_resume"]["t"].tolist()
    for t0 in stops:
        t1 = next((t for t in resumes if t > t0), None)
        end = t1 if t1 is not None else rel.index[-1]
        seg = rel.loc[t0:end]
        i0 = rel.index.get_loc(t0)
        r0 = float(rel.iloc[i0 - 1])  # the value the stop read
        lo_t = seg.idxmin()
        out.append({"stop": str(t0), "resume": str(t1) if t1 is not None else None,
                    "days": (end - t0).total_seconds() / 86400,
                    "off_days": float(off.loc[t0:end].sum() / 24),
                    "r_low_vs_trigger": float(seg.min() / r0 - 1), "r_low_at": str(lo_t),
                    "r_rebound_to_resume": float(seg.iloc[-1] / seg.min() - 1),
                    "fees_missed": float(fees.loc[t0:end].sum() / lad.asof(t0)),
                    "vs_c1": float((mine.asof(end) / lad.asof(end)) / (mine.asof(t0) / lad.asof(t0)) - 1)})
    return out


def report_h66():
    cases = [("C1", "ladder"), ("C1", "ctl"), ("H59", "dd30")] + [("H66", v) for v in H66_VERSIONS]
    t = case_table(cases, ("C1", "ctl"), ("C1", "ladder"))
    t.to_csv(f"{RESULT_DIR}/h66_summary.csv", index=False)
    show(t[["case", "version", "pool", "median", "positive", "cont", "dd", "dd_gap", "calmar", "recentres",
            "switches", "worst_ret", "worst_mdd", "y2026_ret"]])
    by = t.set_index(["pool", "version"])
    verdict = {}
    for v in H66_VERSIONS:
        risk = all(by.loc[(pk, v), "dd_gap"] >= -0.02 for pk in MAIN_REP["C1"])
        ret = all(by.loc[(pk, v), "cont"] > by.loc[(pk, "dd30"), "cont"] for pk in MAIN_REP["C1"])
        verdict[v] = {"dd within 2 pt (both)": bool(risk), "return above dd30 (both)": bool(ret),
                      "passes": bool(risk and ret)}
    passing = [v for v, d in verdict.items() if d["passes"]]
    pick = max(passing, key=lambda v: by.loc[("99ac", v), "cont"]) if passing else None
    stops = {f"{pk}_{v}": h66_stops(pk, v) for pk in MAIN_REP["C1"] for v in H66_VERSIONS}
    for k, ss in stops.items():
        print(f"{k}: {len(ss)} stops")
        for s in ss:
            print(f"  {s['stop'][:16]} -> {(s['resume'] or 'end')[:16]} {s['days']:6.1f}d (off {s['off_days']:5.1f}d) "
                  f"R low {s['r_low_vs_trigger']:+.1%}, rebound to resume {s['r_rebound_to_resume']:+.1%}, "
                  f"fees missed {s['fees_missed']:+.1%}, vs C1 {s['vs_c1']:+.1%}")
    res = {"verdict": verdict, "pick": pick, "stops": stops}
    print(json.dumps({"verdict": verdict, "pick": pick}, indent=1))
    with open(f"{RESULT_DIR}/h66_result.json", "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- H67: the ladder's BTC inventory cap
# reports/plan_2026-10-21_c1_inventory.md (registered in 4812bd2)

H67_VERSIONS = {"inv30": dict(inv_cap=0.30), "inv50": dict(inv_cap=0.50), "inv70": dict(inv_cap=0.70),
                "inv50_spell": dict(inv_cap=0.50, inv_refill="spell")}
D1_LOSERS = (("2022-04-07", "2022-11-04"), ("2026-01-16", "2026-04-17"))  # D1's losing gate-off spells


def h67_cfg(option: str, pk: str, name: str, **kw) -> ConfigG:
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        btc = json.load(f)["btc"]
    return gcfg(option, pk, name, btc, on="spot", **kw, **ladder(0.40, 0.01))


def fix_name(s: float) -> str:
    return f"fix{round(s * 100):02d}"


def tasks_of(cs: list[ConfigG]) -> list[tuple]:
    out = []
    for c in cs:
        out += [(c, s, e, "window") for s, e in windows("C1")]
        s, e = continuous("C1")
        out.append((c, s, e, "continuous"))
    return out


def lp_shares(option: str, pk: str, v: str) -> pd.DataFrame:
    cs, _ = continuous("C1")
    return pd.read_csv(f"{RESULT_DIR}/nav/lpshare_{option}_{pk}_{v}_continuous_{cs}.csv")


def matched_size(v: str) -> float:
    """Plan inventory 2: the version's time-weighted LP share of the book over every gate-off hour on 99ac's continuous
    book (the hours are equal steps), rounded to 0.05."""
    return round(float(lp_shares("H67", "99ac", v)["lp_share"].mean()) / 0.05) * 0.05


def check_h67():
    """Plan inventory 4: a 1000% cap and a fixed ladder of 1.0 equal H48's ladder on 99ac 2022-01; inv50's first
    trim there."""
    s = date(2022, 1, 1)
    ref = json.load(open(f"{ROWS_DIR}/C1_99ac_ladder_window_{s}.json"))["net"]
    for c in (h67_cfg("chk", "99ac", "inv1000", inv_cap=10.0), h67_cfg("chk", "99ac", "fix100", ladder_size=1.0)):
        r = task(c, s, batch.window_end(s), "window")
        print(f"{c.name} {s}: {r['net']:.10f} vs C1 ladder {ref:.10f} diff {r['net'] - ref:+.2e}", flush=True)
    c = h67_cfg("chk", "99ac", "inv50", **H67_VERSIONS["inv50"])
    r = task(c, s, batch.window_end(s), "window")
    ev = pd.read_csv(f"{RESULT_DIR}/nav/events_chk_99ac_inv50_window_{s}.csv")
    trims = ev[ev["kind"].str.startswith("trim:")]
    print(f"inv50 {s}: net {r['net']:+.4f}, {len(trims)} trims; first {trims.head(3).values.tolist()}", flush=True)


def run_h67(workers: int):
    inv = [h67_cfg("H67", pk, v, **kw) for pk in MAIN_REP["C1"] for v, kw in H67_VERSIONS.items()]
    run_tasks(tasks_of(inv), workers)
    sizes = {v: matched_size(v) for v in H67_VERSIONS}
    print("matched fixed ladder sizes:", sizes, flush=True)
    fixed = [h67_cfg("H67F", pk, fix_name(s), ladder_size=s) for pk in MAIN_REP["C1"] for s in sorted(set(sizes.values()))]
    run_tasks(tasks_of(fixed), workers)
    report_h67(sizes)


def report_h67(sizes: dict):
    cases = ([("C1", "ladder"), ("C1", "ctl"), ("H59", "dd30")] + [("H67", v) for v in H67_VERSIONS]
             + [("H67F", fix_name(s)) for s in sorted(set(sizes.values()))])
    t = case_table(cases, ("C1", "ctl"), ("C1", "ladder"))
    cs, _ = continuous("C1")
    extra = []
    for r in t.itertuples():
        e = {}
        if r.case in ("H67", "H67F"):
            sh = lp_shares(r.case, r.pool, r.version)
            e["lp_share_off"], e["btc_share_max"] = float(sh["lp_share"].mean()), float(sh["btc_share"].max())
            ev = pd.read_csv(f"{RESULT_DIR}/nav/events_{r.case}_{r.pool}_{r.version}_continuous_{cs}.csv")
            tr = [k.split(":") for k in ev["kind"].astype(str) if k.startswith("trim:")]
            e["trims"], e["trim_sold"] = len(tr), sum(float(x[3]) for x in tr) / USD
        nav = nav_of(r.case, r.pool, r.version)
        for i, (a, b) in enumerate(D1_LOSERS):
            e[f"d1_{i}"] = span(nav, a, b)["ret"]
        extra.append(e)
    t = pd.concat([t, pd.DataFrame(extra)], axis=1)
    t.to_csv(f"{RESULT_DIR}/h67_summary.csv", index=False)
    show(t[["case", "version", "pool", "median", "positive", "cont", "dd", "dd_gap", "calmar", "recentres", "trims",
            "trim_sold", "lp_share_off", "btc_share_max", "worst_ret", "y2026_ret", "d1_0", "d1_1"]])
    by = t.set_index(["pool", "version"])
    pools = MAIN_REP["C1"]
    verdict = {}
    for v in H67_VERSIONS:
        risk = all(by.loc[(pk, v), "dd_gap"] >= -0.02 for pk in pools)
        ret = all(by.loc[(pk, v), "cont"] > by.loc[(pk, "dd30"), "cont"] for pk in pools)
        f = fix_name(sizes[v])
        value = all(by.loc[(pk, v), "cont"] >= by.loc[(pk, f), "cont"] and by.loc[(pk, v), "dd"] >= by.loc[(pk, f), "dd"]
                    for pk in pools)
        verdict[v] = {"dd within 2 pt (both)": bool(risk), "return above dd30 (both)": bool(ret),
                      "passes": bool(risk and ret), "matched fixed ladder": f,
                      "beats its fixed ladder (both)": bool(value)}
    passing = [v for v, d in verdict.items() if d["passes"]]
    res = {"sizes": sizes, "verdict": verdict,
           "pick": max(passing, key=lambda v: by.loc[("99ac", v), "cont"]) if passing else None}
    print(json.dumps(res, indent=1))
    with open(f"{RESULT_DIR}/h67_result.json", "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- H68: gate-on and gate-off shares set apart
# reports/plan_2026-10-21_c1_split.md (registered in 0be6653)

H68_VERSIONS = {"w80_s40": (0.8, 0.4), "w80_s60": (0.8, 0.6), "w90_s40": (0.9, 0.4), "w90_s60": (0.9, 0.6)}
H68_NB = {"w80_s40": ["w80_s60", "w90_s40"], "w80_s60": ["w80_s40", "w90_s60"],
          "w90_s40": ["w90_s60", "w80_s40"], "w90_s60": ["w90_s40", "w80_s60"]}


def h68_configs() -> list[ConfigG]:
    """WBTC share while on (spot_weight, set at each gate-on switch) and the ladder share while off (ladder_size)."""
    return [h67_cfg("H68", pk, v, spot_weight=w, ladder_size=s)
            for pk in MAIN_REP["C1"] for v, (w, s) in H68_VERSIONS.items()]


def check_h68():
    """Plan split 4: w_on 1.0 and s_off 1.0 equal H48's ladder on 99ac 2022-01."""
    s = date(2022, 1, 1)
    ref = json.load(open(f"{ROWS_DIR}/C1_99ac_ladder_window_{s}.json"))["net"]
    r = task(h67_cfg("chk", "99ac", "w100_s100", spot_weight=1.0, ladder_size=1.0), s, batch.window_end(s), "window")
    print(f"w100_s100 {s}: {r['net']:.10f} vs C1 ladder {ref:.10f} diff {r['net'] - ref:+.2e}", flush=True)


def report_h68():
    cases = [("C1", "ladder"), ("C1", "ctl"), ("H59", "dd30")] + [("H68", v) for v in H68_VERSIONS]
    t = case_table(cases, ("C1", "ctl"), ("C1", "ladder"))
    t.to_csv(f"{RESULT_DIR}/h68_summary.csv", index=False)
    show(t[["case", "version", "pool", "median", "positive", "cont", "dd", "dd_gap", "calmar", "recentres", "gas",
            "impact", "worst_ret", "worst_mdd", "y2026_ret", "y2026_mdd"]])
    by = t.set_index(["pool", "version"])
    pools = MAIN_REP["C1"]
    verdict = {}
    for v in H68_VERSIONS:
        risk = all(by.loc[(pk, v), "dd_gap"] >= -0.02 for pk in pools)
        ret = all(by.loc[(pk, v), "cont"] > by.loc[(pk, "dd30"), "cont"] for pk in pools)
        verdict[v] = {"dd within 2 pt (both)": bool(risk), "return above dd30 (both)": bool(ret),
                      "passes": bool(risk and ret)}
    for v in H68_VERSIONS:
        verdict[v]["neighbours passing"] = [n for n in H68_NB[v] if verdict[n]["passes"]]
    passing = [v for v, d in verdict.items() if d["passes"]]
    res = {"verdict": verdict, "pick": max(passing, key=lambda v: by.loc[("99ac", v), "cont"]) if passing else None}
    print(json.dumps(res, indent=1))
    with open(f"{RESULT_DIR}/h68_result.json", "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- H56, H57: gate x range together, 2026 held out

IS_FROM, IS_TO = date(2022, 1, 1), date(2025, 12, 31)
OOS_FROM_D, OOS_TO_D = date(2026, 1, 1), date(2026, 9, 30)
H56_ORDER = ["C1", "C3", "C2", "C4", "B1"]
GATES = {"btc": {"ema50": "99ac:ema:50", "ema100": "99ac:ema:100", "ema200": "99ac:ema:200", "sma200": "99ac:sma:200",
                 "ts30": "99ac:ts:30", "ts90": "99ac:ts:90", "ts180": "99ac:ts:180"},
         "eth": {"ema50": "88e6:ema:50", "ema100": "88e6:ema:100", "ema200": "88e6:ema:200", "sma200": "88e6:sma:200",
                 "ts30": "88e6:ts:30", "ts90": "88e6:ts:90", "ts180": "88e6:ts:180", "btcema100": "99ac:ema:100"}}
GATE_NB = {"ema50": ["ema100"], "ema100": ["ema50", "ema200", "btcema100"], "ema200": ["ema100", "sma200"],
           "sma200": ["ema200"], "ts30": ["ts90"], "ts90": ["ts30", "ts180"], "ts180": ["ts90"], "btcema100": ["ema100"]}
OFF_SHAPES = {"l120": (0.20, 0.01), "l140": (0.40, 0.01), "l160": (0.60, 0.01), "sd": (0.33, 0.10), "w20": (0.20, 0.20)}
ON_SHAPES = {"w10": (0.10, 0.0), "w20": (0.20, 0.0), "w30": (0.30, 0.0), "sd": (0.33, 0.10)}
B1_SHAPES = {"w10": (0.10, 0.0), "w20": (0.20, 0.0), "w50": (0.50, 0.0)}
SHAPE_NB = {"C": {"l120": ["l140"], "l140": ["l120", "l160", "sd"], "l160": ["l140"], "sd": ["l140", "w20"],
                  "w20": ["sd"]},
            "O": {"w10": ["w20"], "w20": ["w10", "w30", "sd"], "w30": ["w20"], "sd": ["w20"]},
            "B": {"w10": ["w20"], "w20": ["w10", "w50"], "w50": ["w20"]}}


def h56_shapes(opt: str) -> tuple[dict, dict]:
    if opt in ("C1", "C3"):
        return OFF_SHAPES, SHAPE_NB["C"]
    if opt in ("C2", "C4"):
        return ON_SHAPES, SHAPE_NB["O"]
    return B1_SHAPES, SHAPE_NB["B"]


def h56_ctl_of(opt: str, shape: str) -> str:
    if opt in ("C2", "C4"):
        return "ctl26" if shape == "sd" else "ctl50"
    return "ctl"


def h56_configs(opt: str, pool: str, shift: int = 0) -> list[ConfigG]:
    """Every gate x shape of an option in one pool, plus each gate's control(s); shift rolls the gate (placebo)."""
    gates = GATES[ASSET_OF[opt]]
    shapes, _ = h56_shapes(opt)
    sfx = f"_s{shift:+d}" if shift else ""
    o = f"H56{opt}"
    out = []
    for gt, spec in gates.items():
        kw = dict(shift=shift) if shift else {}
        for sh, (w, u) in shapes.items():
            if opt in ("C1", "C3"):
                out.append(gcfg(o, pool, f"{gt}_{sh}{sfx}", spec, on="spot", **ladder(w, u), **kw))
            else:
                out.append(gcfg(o, pool, f"{gt}_{sh}{sfx}", spec, width=w, up=u, on="range", **kw))
        if opt in ("C1", "C3"):
            out.append(gcfg(o, pool, f"{gt}_ctl{sfx}", spec, on="spot", **kw))
        elif opt in ("C2", "C4"):
            out.append(gcfg(o, pool, f"{gt}_ctl50{sfx}", spec, on="spot", spot_weight=0.5, **kw))
            out.append(gcfg(o, pool, f"{gt}_ctl26{sfx}", spec, on="spot", spot_weight=share_of(1.33, 1.10), **kw))
        else:
            out.append(gcfg(o, pool, f"{gt}_ctl{sfx}", spec, on="spot", spot_weight=0.5, **kw))
    return out


def is_windows() -> list[tuple[date, date]]:
    starts = [date(y, m, 1) for y in range(2022, 2026) for m in (1, 4, 7, 10) if date(y, m, 1) <= date(2025, 1, 1)]
    return [(s, (pd.Timestamp(s) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()) for s in starts]


def run_tasks(tasks: list[tuple], workers: int):
    tasks = [t for t in tasks if not os.path.exists(row_path(t[0], t[1], t[3]))]
    print(f"{time.strftime('%H:%M:%S')} {len(tasks)} tasks", flush=True)
    if tasks:
        with multiprocessing.Pool(workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)


def row_of(c: ConfigG, start: date, kind: str) -> dict:
    with open(row_path(c, start, kind)) as f:
        return json.load(f)


def h56_table(opt: str) -> pd.DataFrame:
    """In-sample checks of every combo in both pools."""
    shapes, _ = h56_shapes(opt)
    rows = []
    for pk in MAIN_REP[opt]:
        cs = {c.name: c for c in h56_configs(opt, pk)}
        for gt in GATES[ASSET_OF[opt]]:
            for sh in shapes:
                lp, ctl = cs[f"{gt}_{sh}"], cs[f"{gt}_{h56_ctl_of(opt, sh)}"]
                x = pd.Series({s: row_of(lp, s, "window")["net"] - row_of(ctl, s, "window")["net"] for s, _ in is_windows()})
                rl, rc = row_of(lp, IS_FROM, "continuous"), row_of(ctl, IS_FROM, "continuous")
                ch = judge(x, rl["maxDD"], rc["maxDD"])
                h = math.ceil(len(x) / 2)
                rows.append({"option": opt, "pool": pk, "gate": gt, "shape": sh, "median": x.median(),
                             "positive": int((x > 0).sum()), "first_half": x.iloc[:h].median(),
                             "second_half": x.iloc[h:].median(), "cont_lp": rl["net"], "cont_ctl": rc["net"],
                             "cont_diff": rl["net"] - rc["net"], "dd_lp": rl["maxDD"], "dd_ctl": rc["maxDD"],
                             "four": all(ch.values()), "three": all(v for k, v in ch.items() if k != "dd within 2 pt")})
    return pd.DataFrame(rows)


def h56_pick(t: pd.DataFrame, opt: str) -> tuple[str | None, pd.DataFrame]:
    main, rep = MAIN_REP[opt]
    _, snb = h56_shapes(opt)
    m = t[t["pool"] == main].set_index(["gate", "shape"])
    r = t[t["pool"] == rep].set_index(["gate", "shape"])
    gates = list(GATES[ASSET_OF[opt]])
    cand = []
    for (gt, sh), row in m.iterrows():
        if not row["four"]:
            continue
        gnb = [g_ for g_ in GATE_NB[gt] if g_ in gates]
        ok_g = not gnb or any(m.loc[(g_, sh), "three"] for g_ in gnb)
        ok_s = not snb[sh] or any(m.loc[(gt, s_), "three"] for s_ in snb[sh])
        if ok_g and ok_s and r.loc[(gt, sh), "three"]:
            cand.append((gt, sh, row["cont_diff"]))
    t = t.copy()
    t["candidate"] = [(row.pool == main and (row.gate, row.shape) in {(a, b) for a, b, _ in cand}) for row in t.itertuples()]
    if not cand:
        return None, t
    gt, sh, _ = max(cand, key=lambda z: z[2])
    return f"{gt}_{sh}", t


def h56_luck(opt: str, pick: str, workers: int) -> dict:
    main = MAIN_REP[opt][0]
    shifts = robust.placebo_shifts()
    tasks = [(c, IS_FROM, IS_TO, "continuous") for k in shifts for c in h56_configs(opt, main, k)]
    run_tasks(tasks, workers)
    shapes, _ = h56_shapes(opt)
    maxima = {}
    for k in shifts:
        cs = {c.name: c for c in h56_configs(opt, main, k)}
        sfx = f"_s{k:+d}"
        best = max(row_of(cs[f"{gt}_{sh}{sfx}"], IS_FROM, "continuous")["net"]
                   - row_of(cs[f"{gt}_{h56_ctl_of(opt, sh)}{sfx}"], IS_FROM, "continuous")["net"]
                   for gt in GATES[ASSET_OF[opt]] for sh in shapes)
        maxima[k] = best
    cs = {c.name: c for c in h56_configs(opt, main)}
    gt, sh = pick.split("_", 1)
    real = (row_of(cs[pick], IS_FROM, "continuous")["net"]
            - row_of(cs[f"{gt}_{h56_ctl_of(opt, sh)}"], IS_FROM, "continuous")["net"])
    med = float(np.median(list(maxima.values())))
    return {"real": real, "placebo_maxima": maxima, "median_of_maxima": med, "passes": real > med}


def h57_run(opt: str, combo: str, workers: int) -> dict:
    """2026-01-01 .. 09-30 from cash, the combo and its control, both pools."""
    gt, sh = combo.split("_", 1)
    out = {}
    tasks = []
    for pk in MAIN_REP[opt]:
        cs = {c.name: c for c in h56_configs(opt, pk)}
        for v in (combo, f"{gt}_{h56_ctl_of(opt, sh)}"):
            tasks.append((cs[v], OOS_FROM_D, OOS_TO_D, "oos"))
    run_tasks(tasks, workers)
    for pk in MAIN_REP[opt]:
        cs = {c.name: c for c in h56_configs(opt, pk)}
        lp, ctl = row_of(cs[combo], OOS_FROM_D, "oos"), row_of(cs[f"{gt}_{h56_ctl_of(opt, sh)}"], OOS_FROM_D, "oos")
        out[pk] = {"lp": lp["net"], "ctl": ctl["net"], "dd_lp": lp["maxDD"], "dd_ctl": ctl["maxDD"],
                   "passes": bool(lp["net"] > ctl["net"] and lp["maxDD"] >= ctl["maxDD"] - 0.02)}
    return out


def h57_listed(workers: int) -> dict:
    """Listed only: A2's pick and C1's H48 ladder (EMA100, p/1.40) in 2026, from cash."""
    with open(f"{RESULT_DIR}/h46_choice.json") as f:
        ch = json.load(f)
    base = {(c.option, c.pool_key, c.name): c for c in h48_configs(ch["btc"], ch["eth"])}
    pairs = {"A2": [base[("A2", "1098", "up_02_08")], base[("A2", "1098", "ctl")]]}
    for pk in MAIN_REP["C1"]:
        pairs[f"C1_{pk}"] = [base[("C1", pk, "ladder")], base[("C1", pk, "ctl")]]
    run_tasks([(c, OOS_FROM_D, OOS_TO_D, "oos") for v in pairs.values() for c in v], workers)
    out = {}
    for k, (lp, ctl) in pairs.items():
        a, b = row_of(lp, OOS_FROM_D, "oos"), row_of(ctl, OOS_FROM_D, "oos")
        out[k] = {"lp": a["net"], "ctl": b["net"], "dd_lp": a["maxDD"], "dd_ctl": b["maxDD"]}
    return out


def run_h56(workers: int, only: list[str] | None):
    result = {}
    path = f"{RESULT_DIR}/h56_result.json"
    if os.path.exists(path):
        with open(path) as f:
            result = json.load(f)
    for opt in H56_ORDER:
        if only and opt not in only:
            continue
        tasks = []
        for pk in MAIN_REP[opt]:
            for c in h56_configs(opt, pk):
                tasks += [(c, s, e, "window") for s, e in is_windows()]
                tasks.append((c, IS_FROM, IS_TO, "continuous"))
        run_tasks(tasks, workers)
        t = h56_table(opt)
        pick, t = h56_pick(t, opt)
        t.to_csv(f"{RESULT_DIR}/h56_{opt}.csv", index=False)
        r = {"pick": pick, "candidates": t[t["candidate"]][["gate", "shape", "cont_diff"]].values.tolist()}
        print(f"H56 {opt}: candidates {r['candidates']}, pick {pick}", flush=True)
        if pick:
            r["luck"] = h56_luck(opt, pick, workers)
            print(f"H56 {opt} luck: real {r['luck']['real']:+.4f} vs median of placebo maxima "
                  f"{r['luck']['median_of_maxima']:+.4f} -> {'pass' if r['luck']['passes'] else 'luck'}", flush=True)
            if r["luck"]["passes"]:
                r["oos"] = h57_run(opt, pick, workers)
                print(f"H57 {opt}: {r['oos']}", flush=True)
        result[opt] = r
        with open(path, "w") as f:
            json.dump(result, f, indent=1, default=float)
    result["listed_2026"] = h57_listed(workers)
    print("H57 listed:", result["listed_2026"], flush=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=1, default=float)


# ---------------------------------------------------------------- acceptance

def accept():
    """H4b's g_down, g_spot100 and g_sym on 2023-01 (minute bars, hourly check) and H26's g_down_d1x on 2022-07."""
    ref = {("g_down", "2023-01-01"): 0.7236676732498697, ("g_spot100", "2023-01-01"): 0.6959534051126905,
           ("g_sym", "2023-01-01"): 0.164677232801288, ("g_down_d1x", "2022-07-01"): 0.6069492293916303}
    g_new, g_old = gate_series("99ac:ema:100"), batch.gate("99ac", 100)
    same = bool((g_new.reindex(g_old.index).fillna(False) == g_old).all())
    print(f"gate 99ac ema100 equals pool_lp_batch.gate: {same}")
    spec = "99ac:ema:100"
    cfgs = {"g_down": gcfg("acc", "99ac", "g_down", spec, on="spot", hourly_check=True, **ladder(0.40, 0.01)),
            "g_spot100": gcfg("acc", "99ac", "g_spot100", spec, on="spot", hourly_check=True),
            "g_sym": gcfg("acc", "99ac", "g_sym", spec, width=0.20, on="range", hourly_check=True),
            "g_down_d1x": gcfg("acc", "99ac", "g_down_d1x", spec, on="spot", **ladder(0.40, 0.01))}
    args = [(cfgs[v], date.fromisoformat(s), batch.window_end(date.fromisoformat(s)), None) for v, s in ref]
    with multiprocessing.Pool(2, maxtasksperchild=1) as pool:
        res = pool.starmap(run, args, chunksize=1)
    ok = same
    for (v, s), r in zip(ref, res):
        d = r["net"] - ref[(v, s)]
        ok &= abs(d) < 1e-9
        print(f"{v} {s}: {r['net']:.10f} vs {ref[(v, s)]:.10f} diff {d:+.2e} {r['secs']}s")
    print("ACCEPT" if ok else "MISMATCH")


def show(t: pd.DataFrame):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"), flush=True)


def build_cache():
    os.makedirs(windows_mod.RESULT_DIR, exist_ok=True)
    for src in ("99ac", "88e6"):
        hourly_close(src)
    eth_daily()
    for pk in ("e8f7", "1098", "4585", "cbcd", "99ac", "9db9", "8ad5", "88e6"):
        p = batch.POOLS[pk]
        for y in range(max(2022, p.first.year), 2027):
            s = max(date(y, 1, 1), p.first)
            hourly_market(pk, s, s)
            print(f"{time.strftime('%H:%M:%S')} cached {pk} {y}", flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cache", action="store_true")
    a.add_argument("--accept", action="store_true")
    a.add_argument("--h46", action="store_true")
    a.add_argument("--h47", action="store_true")
    a.add_argument("--h48", action="store_true")
    a.add_argument("--h49", action="store_true")
    a.add_argument("--h50", action="store_true")
    a.add_argument("--h51", action="store_true", help="H51 and H52 (the half ladder is a C1 version)")
    a.add_argument("--h53", action="store_true", help="H53, H54 and H55 (C1's drawdown)")
    a.add_argument("--h56", action="store_true", help="H56 and H57 (gate x range together, 2026 held out)")
    a.add_argument("--h59-check", action="store_true", help="plan 2026-10-21 section 5's checks, before H59")
    a.add_argument("--h59", action="store_true", help="H59 - H62 (C1's gate-off exposure capped)")
    a.add_argument("--h63-check", action="store_true", help="plan cost_vol section 5's checks, before H63")
    a.add_argument("--h63", action="store_true", help="H63 - H65 (swap route, ladder sized by vol)")
    a.add_argument("--h66-check", action="store_true", help="plan lp_budget section 4's check, before H66")
    a.add_argument("--h66", action="store_true", help="H66 (LP excess-loss budget)")
    a.add_argument("--h67-check", action="store_true", help="plan inventory section 4's checks, before H67")
    a.add_argument("--h67", action="store_true", help="H67 (BTC inventory cap), then its fixed ladders")
    a.add_argument("--h68-check", action="store_true", help="plan split section 4's check, before H68")
    a.add_argument("--h68", action="store_true", help="H68 (gate-on and gate-off shares set apart)")
    a.add_argument("--report", action="store_true")
    a.add_argument("--only", nargs="*", default=None)
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--limit", type=int, default=0, help="run only the first n tasks (timing)")
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    os.makedirs(windows_mod.RESULT_DIR, exist_ok=True)
    if a.cache:
        build_cache()
    if a.accept:
        accept()
    if a.h46:
        run_h46()
    if a.h47:
        run_h47()
    if a.h48:
        tasks = h48_tasks(a.only)
        if a.limit:
            tasks = tasks[:a.limit]
        print(f"{len(tasks)} tasks", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)
    if a.report or a.h48:
        report_h48()
    if a.h49:
        tasks = h49_tasks()
        print(f"{len(tasks)} tasks", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)
        report_h49()
    if a.h50:
        tasks = h50_tasks()
        print(f"{len(tasks)} tasks", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)
        report_h50()
    if a.h51:
        tasks = h51_tasks()
        if a.limit:
            tasks = tasks[:a.limit]
        print(f"{len(tasks)} tasks", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)
        if not a.limit:
            report_h51()
    if a.h53:
        tasks = h53_tasks()
        print(f"{len(tasks)} tasks", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.starmap(task, tasks, chunksize=1)
        report_h53()
    if a.h56:
        run_h56(a.workers, a.only)
    if a.h59_check:
        check_h59()
    if a.h59:
        run_tasks(h59_tasks(), a.workers)
        report_h59()
    if a.h63_check:
        check_h63()
    if a.h63:
        run_tasks(h63_tasks(), a.workers)
        report_h63()
    if a.h66_check:
        check_h66()
    if a.h66:
        run_tasks(h66_tasks(), a.workers)
        report_h66()
    if a.h67_check:
        check_h67()
    if a.h67:
        run_h67(a.workers)
    if a.h68_check:
        check_h68()
    if a.h68:
        run_tasks(tasks_of(h68_configs()), a.workers)
        report_h68()


if __name__ == "__main__":
    main()
