"""
Three-pool experiment, plan A: BTC/USD is derived from two pools, LP only in the two liquid pools.

  ETH/USDC  0x88e6... 0.05%  -> WETH price in USDC, LP leg 1
  WBTC/WETH 0x4585... 0.05%  -> WBTC price in WETH, LP leg 2
  BTC/USDC  = ETH/USDC x WBTC/WETH (synthetic, no BTC/stable pool needed)

Rules, judged daily at 00:00 UTC on yesterday's close:
  * gate decides whether capital is in the pools or parked in USDC
      none  : always in
      btc   : synthetic BTC close > its EMA
      eth   : ETH close > its EMA
      both  : both of the above
  * when in, equity is split between the ETH/USDC leg and the WBTC/WETH leg, either by fixed
    `weights`, or by `tilt` on the ETH/BTC trend (ETH/BTC close vs its EMA):
      follow: ETH stronger -> TILT_STRONG, weaker -> TILT_WEAK
      fade  : the opposite
    each leg placed +/- its range around the current price
  * rebuild when the target changes, or when a leg's price has left its range

Costs: swaps pay the pool fee (0.05%), no slippage. Gas is estimated afterwards from the action
log (GAS_UNITS x GAS_GWEI of that year x ETH price) and subtracted from net value. Both tables
are rough assumptions, edit them to taste.

Run from samples/strategy-example:
  PYTHONPATH=../.. python tri_btc_eth_gate.py                  # hourly sweep, 2022-2025
  PYTHONPATH=../.. python tri_btc_eth_gate.py --grid           # gate x span x tilt grid, for samples/research/walk_forward.py
  PYTHONPATH=../.. python tri_btc_eth_gate.py --minute mix_btc100,mix_none --window 2025-01-01
      # the same configs on minute bars and hourly bars over one window, to check the hourly approximation
"""
import argparse
import gc
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from demeter import Actuator, ChainType, MarketInfo, Snapshot, Strategy, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool
from demeter.uniswap.data import resample

DATA_START, END = date(2021, 5, 13), date(2025, 12, 31)  # WBTC/WETH has no file for 2021-05-12
TRADE_START = datetime(2022, 1, 1)  # the months before only warm up the EMA
INITIAL_USDC = 100_000
WORKERS = 4
RESULT_DIR = "result/tri-gate"

# gas per action on mainnet through the position manager / router, and yearly average gas price.
# Rough figures, not measured from these trades.
GAS_UNITS = {"AddLiquidityAction": 450_000, "RemoveLiquidityAction": 150_000, "CollectFeeAction": 120_000,
             "SwapAction": 130_000, "BuyAction": 130_000, "SellAction": 130_000}
GAS_GWEI = {2021: 50, 2022: 40, 2023: 30, 2024: 15, 2025: 3}

ETH_POOL = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
RATIO_POOL = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0"
usdc = TokenInfo(name="usdc", decimal=6)
weth = TokenInfo(name="weth", decimal=18)
wbtc = TokenInfo(name="wbtc", decimal=8)
eth_pool = UniV3Pool(token0=usdc, token1=weth, fee=0.05, quote_token=usdc)
ratio_pool = UniV3Pool(token0=wbtc, token1=weth, fee=0.05, quote_token=weth)
ETH_KEY, RATIO_KEY = MarketInfo("eth"), MarketInfo("ratio")
SAFETY = Decimal("0.999")  # leave a hair of balance so rounding never overdraws

EMA_SPANS = (50, 100, 150, 200)
TILT_STRONG, TILT_WEAK = (0.75, 0.25), (0.25, 0.75)  # (ETH/USDC leg, WBTC/WETH leg)


@dataclass(frozen=True)
class Config:
    name: str
    gate: str  # none / btc / eth / both
    weights: tuple = (0.5, 0.5)  # (ETH/USDC leg, WBTC/WETH leg), sums to 1
    eth_range: float = 0.20
    ratio_range: float = 0.10
    ema_span: int = 100
    tilt: str = "none"  # none / follow / fade


def build_configs() -> list[Config]:
    configs = [Config("mix_none", "none")]
    for span in EMA_SPANS:
        for gate in ("btc", "eth", "both"):
            configs.append(Config(f"mix_{gate}{span}", gate, ema_span=span))
    for eth_range, ratio_range in ((0.10, 0.05), (0.30, 0.15)):
        configs.append(Config(f"mix_btc100_r{round(eth_range * 100)}", "btc", eth_range=eth_range, ratio_range=ratio_range))
    configs.append(Config("tilt_follow_btc100", "btc", tilt="follow"))
    configs.append(Config("tilt_fade_btc100", "btc", tilt="fade"))
    return configs


def build_grid() -> list[Config]:
    """Every gate x EMA span x tilt, ranges fixed at the default. Input for walk-forward selection."""
    configs = [Config(f"none_{tilt}", "none", tilt=tilt) for tilt in ("none", "follow", "fade")]
    for gate in ("btc", "eth", "both"):
        for span in EMA_SPANS:
            for tilt in ("none", "follow", "fade"):
                configs.append(Config(f"{gate}{span}_{tilt}", gate, ema_span=span, tilt=tilt))
    return configs


def build_signal(eth_daily: pd.Series, ratio_daily: pd.Series) -> pd.DataFrame:
    """One bool column per (series, span). The row for day d holds what was known at d 00:00."""
    daily = pd.DataFrame({"eth": eth_daily, "btc": eth_daily * ratio_daily}).dropna()
    daily["ethbtc"] = daily["eth"] / daily["btc"]
    columns = {f"{col}{span}": daily[col] > daily[col].ewm(span=span, adjust=False).mean()
               for span in EMA_SPANS for col in daily.columns}
    return pd.DataFrame(columns).shift(1).dropna().astype(bool)


class TriGate(Strategy):
    def __init__(self, cfg: Config, signal: pd.DataFrame, trade_start: datetime):
        super().__init__()
        self.cfg = cfg
        self.signal = signal
        self.trade_start = trade_start
        self.target = None  # None = parked in USDC, else (ETH/USDC leg, WBTC/WETH leg)
        self.bounds = {}  # market key -> (low price, high price)
        self.rebuilds = 0

    def wanted(self, sig: pd.Series) -> tuple | None:
        span, gate = self.cfg.ema_span, self.cfg.gate
        if gate == "btc" and not sig[f"btc{span}"] or gate == "eth" and not sig[f"eth{span}"] \
                or gate == "both" and not (sig[f"btc{span}"] and sig[f"eth{span}"]):
            return None
        if self.cfg.tilt == "none":
            return self.cfg.weights
        eth_strong = bool(sig[f"ethbtc{span}"])
        return TILT_STRONG if eth_strong == (self.cfg.tilt == "follow") else TILT_WEAK

    def on_bar(self, snapshot: Snapshot):
        t = snapshot.timestamp
        if t < self.trade_start or t.hour != 0 or t.minute != 0:
            return
        target = self.wanted(self.signal.loc[pd.Timestamp(t.date())])
        left_range = any(not (lo <= self.markets[k].market_status.data.price <= hi) for k, (lo, hi) in self.bounds.items())
        if target != self.target or (target is not None and left_range):
            self.rebuild(target)

    @staticmethod
    def _swap(market: UniLpMarket, amount: Decimal, from_token: TokenInfo, to_token: TokenInfo):
        if amount > 0:
            market.swap(amount, from_token, to_token)

    def _place(self, market: UniLpMarket, width: float, value: Decimal | None):
        price = market.market_status.data.price
        lo, hi = price * Decimal(1 - width), price * Decimal(1 + width)
        t1, t2 = market.price_to_tick(lo), market.price_to_tick(hi)
        market.add_liquidity_by_value(min(t1, t2), max(t1, t2), value)
        self.bounds[market.market_info] = (lo, hi)

    def rebuild(self, target: tuple | None):
        m_eth: UniLpMarket = self.markets[ETH_KEY]
        m_ratio: UniLpMarket = self.markets[RATIO_KEY]
        self.rebuilds += 1
        self.target = target
        for m in (m_eth, m_ratio):
            m.remove_all_liquidity()
        self.bounds = {}
        # consolidate WBTC into WETH, so the only balances are USDC and WETH
        self._swap(m_ratio, self.broker.get_token_balance(wbtc), wbtc, weth)
        if target is None:
            self._swap(m_eth, self.broker.get_token_balance(weth), weth, usdc)
            return

        p_eth = m_eth.market_status.data.price  # USDC per WETH
        w_eth, w_ratio = (Decimal(str(w)) for w in target)
        equity = self.broker.get_token_balance(usdc) + self.broker.get_token_balance(weth) * p_eth
        if w_ratio > 0:
            # the WBTC/WETH leg is funded in WETH, add_liquidity_by_value then swaps part of it to WBTC
            weth_needed = equity * w_ratio / p_eth
            shortfall = weth_needed - self.broker.get_token_balance(weth)
            if shortfall > 0:
                self._swap(m_eth, min(shortfall * p_eth, self.broker.get_token_balance(usdc)), usdc, weth)
            self._place(m_ratio, self.cfg.ratio_range, min(weth_needed, self.broker.get_token_balance(weth)) * SAFETY)
        if w_eth > 0:
            self._place(m_eth, self.cfg.eth_range, None)  # everything left in USDC + WETH


def load_market(key: MarketInfo, pool: UniV3Pool, address: str, start: date, end: date, bar: str | None):
    """Market data resampled to `bar` (None keeps minutes), plus minute-level daily closes."""
    market = UniLpMarket(key, pool)
    market.data_path = f"../real-data/{address}"
    market.load_data(ChainType.ethereum.name, address, start, end)
    daily_close = market.data["price"].astype(float).resample("1D").last()
    data = resample(market.data, bar) if bar else market.data
    del market
    gc.collect()
    return data, daily_close


def load_pair(start: date, end: date, bar: str | None):
    eth_d, eth_close = load_market(ETH_KEY, eth_pool, ETH_POOL, start, end, bar)
    ratio_d, ratio_close = load_market(RATIO_KEY, ratio_pool, RATIO_POOL, start, end, bar)
    index = eth_d.index.intersection(ratio_d.index)
    eth_d, ratio_d = eth_d.loc[index], ratio_d.loc[index]
    p_eth, p_ratio = eth_d["price"].astype(float), ratio_d["price"].astype(float)
    prices = pd.DataFrame({weth.name: p_eth, wbtc.name: p_eth * p_ratio, usdc.name: 1.0}, index=index)
    return eth_d, ratio_d, prices, eth_close, ratio_close


def gas_usd(actions, prices: pd.DataFrame) -> pd.Series:
    """Cumulative estimated gas in USD, indexed by action time."""
    rows = {}
    for a in actions:
        units = GAS_UNITS.get(type(a).__name__)
        if units:
            ts = pd.Timestamp(a.timestamp)
            rows[ts] = rows.get(ts, 0.0) + units * GAS_GWEI[ts.year] * 1e-9 * prices.loc[ts, weth.name]
    return pd.Series(rows, index=pd.DatetimeIndex(list(rows)), dtype=float).sort_index().cumsum()


def run_one(cfg: Config, eth_d: pd.DataFrame, ratio_d: pd.DataFrame, prices: pd.DataFrame, signal: pd.DataFrame,
            trade_start: datetime):
    started = time.time()
    actuator = Actuator()
    for key, pool, data in ((ETH_KEY, eth_pool, eth_d), (RATIO_KEY, ratio_pool, ratio_d)):
        market = UniLpMarket(key, pool)
        market.data = data
        actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, INITIAL_USDC)
    actuator.set_price(prices, usdc)
    strategy = TriGate(cfg, signal, trade_start)
    actuator.strategy = strategy
    actuator.run(print_result=False)
    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    # every swap, including the ones add_liquidity_by_value makes, leaves an action with its fee
    swap_fee = sum(float(a.fee) * prices.loc[pd.Timestamp(a.timestamp), a.fee.unit]
                   for a in actuator.actions if type(a).__name__ in ("SwapAction", "BuyAction", "SellAction"))
    gas = gas_usd(actuator.actions, prices)
    nav_net = nav - gas.reindex(nav.index, method="ffill").fillna(0.0)
    return cfg.name, nav_net, strategy.rebuilds, swap_fee, float(gas.iloc[-1]) if len(gas) else 0.0, time.time() - started


YEARS = [("2022", "2022-01-01", "2023-01-01"), ("2023", "2023-01-01", "2024-01-01"),
         ("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01")]


def period_stats(nav: pd.Series, start: str) -> dict:
    out = {}
    for label, lo, hi in YEARS:
        seg = nav.loc[max(lo, start):hi]
        if hi > start and len(seg) > 1:
            out[label] = seg.iloc[-1] / seg.iloc[0] - 1
    seg = nav.loc[start:]
    out["total"] = seg.iloc[-1] / seg.iloc[0] - 1
    out["maxDD"] = (seg / seg.cummax() - 1).min()
    return out


def show(table: pd.DataFrame) -> str:
    shown = table.copy()
    pct = [c for c in shown.columns if c[0].isdigit() or c in ("total", "maxDD")]
    shown[pct] = shown[pct].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    return shown.fillna("").to_string()


def run_all(configs, eth_d, ratio_d, prices, signal, trade_start, workers):
    args = [(c, eth_d, ratio_d, prices, signal, trade_start) for c in configs]
    if workers == 1:
        return [run_one(*a) for a in args]
    with multiprocessing.Pool(workers) as pool:
        return pool.starmap(run_one, args)


def summarise(results, start: str) -> tuple[pd.DataFrame, dict]:
    rows, navs = [], {}
    for name, nav, rebuilds, swap_fee, gas, secs in results:
        rows.append({"run": name, **period_stats(nav, start), "rebuilds": rebuilds,
                     "swap $": round(swap_fee), "gas $": round(gas), "secs": round(secs)})
        navs[name] = nav
    return pd.DataFrame(rows).set_index("run"), navs


def sweep(configs: list[Config], tag: str):
    eth_d, ratio_d, prices, eth_close, ratio_close = load_pair(DATA_START, END, "1h")
    signal = build_signal(eth_close, ratio_close)
    results = run_all(configs, eth_d, ratio_d, prices, signal, TRADE_START, WORKERS)
    table, navs = summarise(results, "2022-01-01")

    base = prices.loc["2022-01-01"].iloc[0]
    holds = {"hold_usdc": pd.Series(1.0, index=prices.index), "hold_eth": prices[weth.name], "hold_btc": prices[wbtc.name],
             "hold_50eth_50btc": 0.5 * prices[weth.name] / base[weth.name] + 0.5 * prices[wbtc.name] / base[wbtc.name]}
    table = pd.concat([table, pd.DataFrame([{"run": k, **period_stats(v, "2022-01-01")} for k, v in holds.items()]).set_index("run")])
    pd.DataFrame({**navs, **holds}).to_csv(f"{RESULT_DIR}/nav_{tag}.csv")
    table.to_csv(f"{RESULT_DIR}/summary_{tag}.csv")
    print(show(table))


def minute_check(names: list[str], window_start: str):
    """Same configs on minute and hourly bars over [window_start, END], signal from the full history."""
    configs = [c for c in build_configs() if c.name in names]
    start = datetime.fromisoformat(window_start)
    _, _, _, eth_close, ratio_close = load_pair(DATA_START, END, "1D")  # only for the daily closes
    signal = build_signal(eth_close, ratio_close)
    rows = []
    for bar in ("1h", None):
        eth_d, ratio_d, prices, _, _ = load_pair(start.date(), END, bar)
        table, _ = summarise(run_all(configs, eth_d, ratio_d, prices, signal, start, 1), window_start)
        table.index = [f"{n} [{bar or '1min'}]" for n in table.index]
        rows.append(table)
        del eth_d, ratio_d, prices
        gc.collect()
    table = pd.concat(rows).sort_index()
    table.to_csv(f"{RESULT_DIR}/minute_check_{window_start}.csv")
    print(show(table))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minute", help="comma separated config names to rerun on minute bars")
    parser.add_argument("--window", default="2025-01-01", help="start of the minute-check window")
    parser.add_argument("--grid", action="store_true", help="run build_grid() for walk-forward selection")
    cli = parser.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if cli.minute:
        minute_check(cli.minute.split(","), cli.window)
    elif cli.grid:
        sweep(build_grid(), "grid")
    else:
        sweep(build_configs(), "sweep")
