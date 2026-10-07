"""
Proposal 1 of reports/next_backtest_plan.md: keep the spot BTC gate (BTC above its EMA100 -> 50% ETH + 50% BTC,
otherwise USDC) and only change where each sleeve sits while it is held.

  A  base        ETH, BTC, USDC
  B  park        idle USDC in USDC/USDT 0.01% +/- 0.5%, not while USDT/USDC is 0.3% or more off peg
  B' park DAI    the same in DAI/USDT 0.01%
  C  wstETH      B, with ETH held as wstETH
  D  full LP     B, with ETH in wstETH/WETH and BTC in WBTC/cbBTC LP, +/- 0.5 / 1 / 2%, re-centred daily when out

Every sleeve that is an LP runs on its own through Demeter first (--sleeves), over its whole window, daily check at
00:00 like tri_btc_eth_gate. Its net value in the quote token becomes a value index, and sleeve_sim combines the
indices with the gate. This assumes the LP position exists the whole time; in reality it is closed while the gate
keeps the sleeve out and re-placed around the new price. The swaps in and out are charged by sleeve_sim.

Periods (data quality, see --quality): FULL 2022-08-27 ~ 2025-11-30 for A, B, B', C, where wstETH/WETH barely traded
before mid-2023 and its ratio stays flat across the gaps. SHORT 2024-01-01 ~ 2025-11-09 for A to D; BTC is held
spot until WBTC/cbBTC has clean data on 2024-10-13.

Run from samples/strategy-example (the spot price cache of spot_btc_eth_gate.py must exist):
  PYTHONPATH=../.. python yield_layer.py --quality
  PYTHONPATH=../.. python yield_layer.py --sleeves            # Demeter LP runs, hourly bars
  PYTHONPATH=../.. python yield_layer.py --sleeves --minute   # the same on minute bars over 2025, as a check
  PYTHONPATH=../.. python yield_layer.py --combine
  PYTHONPATH=../.. python yield_layer.py --sleeves --holdout  # park_usdc and the D sleeves on to HOLDOUT_END
"""
import argparse
import glob
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

import spot_robustness as sr
from demeter import Actuator, MarketInfo, Snapshot, Strategy, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool
from sleeve_sim import mainnet_gas, simulate
from spot_btc_eth_gate import load_prices
# importing tri_btc_eth_gate also patches Demeter's fee share to count our own liquidity
from tri_btc_eth_gate import PARK_MAX_DEPEG, PARK_RANGE, STABLE_POOL, load_market, usdc, usdt, wbtc, weth

RESULT_DIR = "result/yield-layer"
DATA_DIR = "../real-data"
WSTETH_POOL = "0x109830a1AAaD605BbF02a9dFA7B0B92EC2FB7dAa"
CBBTC_POOL = "0xe8f7c89C5eFa061e340f2d2F206EC78FD8f7e124"
DAI_POOL = "0x48DA0965ab2d2cbf1C17C09cFB5Cbe67Ad5B1406"
dai = TokenInfo(name="dai", decimal=18)
wsteth = TokenInfo(name="wsteth", decimal=18)
cbbtc = TokenInfo(name="cbbtc", decimal=8)

FULL = ("2022-08-27", "2025-12-01")
SHORT = ("2024-01-01", "2025-11-10")
CBBTC_CLEAN = "2024-10-13"
CRASH_DAYS = ("2024-08-05", "2025-02-03")  # the wstETH/WETH LP's biggest fee days, found after the sleeve runs
MINUTE_WINDOW = (date(2025, 1, 1), date(2025, 11, 9))
HOLDOUT_END = date(2026, 9, 30)  # the backfilled data; same start, so the path up to 2025-11-30 must not change
HOLDOUT_TAG = "_to2026"
WIDTHS = (0.005, 0.01, 0.02)
WORKERS = 4
KEY = MarketInfo("lp")


@dataclass(frozen=True)
class Sleeve:
    name: str
    address: str
    token0: TokenInfo
    token1: TokenInfo
    quote: TokenInfo  # the unit of the net value; "price" is quote per base
    start: date
    end: date
    width: float
    initial: float  # in quote, about the size the sleeve has in a $100k portfolio
    guard: Decimal | None = None  # stay out while |price - 1| >= guard
    chain: str = "ethereum"  # the address must have the case of its data folder

    @property
    def base(self) -> TokenInfo:
        return self.token1 if self.quote == self.token0 else self.token0

    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=0.01, quote_token=self.quote, tick_spacing=1)


def build_sleeves() -> list[Sleeve]:
    # USDC/USDT quoted in USDC as in tri_btc_eth_gate, so its price is USDC per USDT; DAI/USDT in USDT
    out = [Sleeve("park_usdc", STABLE_POOL, usdc, usdt, usdc, date(2022, 8, 26), date(2025, 11, 30), PARK_RANGE,
                  100_000, PARK_MAX_DEPEG),
           Sleeve("park_dai", DAI_POOL, dai, usdt, usdt, date(2022, 8, 26), date(2025, 11, 30), PARK_RANGE,
                  100_000, PARK_MAX_DEPEG)]
    for w in WIDTHS:
        out.append(Sleeve(f"wsteth_lp{w:g}", WSTETH_POOL, wsteth, weth, weth, date(2024, 1, 1), date(2025, 12, 1), w, 15))
        # quoted in WBTC: the BTC price of spot_btc_eth_gate is a WBTC price
        out.append(Sleeve(f"cbbtc_lp{w:g}", CBBTC_POOL, wbtc, cbbtc, wbtc, date(2024, 10, 13), date(2025, 11, 9), w, 0.5))
    return out


# ---- data quality ----

def pool_dir(address: str) -> str:
    """The data folder of a pool: folders keep the address's checksum case, which a lowercase address lacks."""
    return next(d for d in os.listdir(DATA_DIR) if d.lower() == address.lower())


def read_minutes(address: str, cols=("timestamp", "closeTick", "inAmount0", "inAmount1")) -> pd.DataFrame:
    files = sorted(glob.glob(f"{DATA_DIR}/{pool_dir(address)}/*.minute.csv"))
    df = pd.concat((pd.read_csv(f, usecols=list(cols)) for f in files), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in cols[1:]:  # 18-decimal amounts overflow int64 and load as str
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df.set_index("timestamp").sort_index()


def quality():
    pools = {WSTETH_POOL: ("wstETH/WETH", 18, 18), CBBTC_POOL: ("WBTC/cbBTC", 8, 8), DAI_POOL: ("DAI/USDT", 18, 6),
             STABLE_POOL: ("USDC/USDT", 6, 6)}
    rows = []
    for address, (name, d0, d1) in pools.items():
        df = read_minutes(address)
        price = (1.0001 ** df["closeTick"].ffill()) * 10 ** (d0 - d1)  # token1 per token0
        traded = (df["inAmount0"] > 0) | (df["inAmount1"] > 0)
        volume = df["inAmount1"] / 10 ** d1 + df["inAmount0"] / 10 ** d0 * price  # in token1
        days = pd.DatetimeIndex(df.index.normalize().unique())
        missing = pd.date_range(days.min(), days.max(), freq="D").difference(days)
        for year, idx in df.groupby(df.index.year).groups.items():
            tr = traded.loc[idx]
            gaps = np.diff(tr[tr].index.values) / np.timedelta64(1, "h")
            p = price.loc[idx]
            rows.append({"pool": name, "year": year, "days": int((days.year == year).sum()),
                         "missing days": int((missing.year == year).sum()),
                         "traded minutes %": round(100 * tr.mean(), 1),
                         "longest gap h": round(float(gaps.max()), 1) if len(gaps) else np.nan,
                         "price p1": p.quantile(0.01), "price median": p.median(), "price p99": p.quantile(0.99),
                         "price min": p.min(), "price max": p.max(),
                         "daily volume median": volume.loc[idx].resample("D").sum().median()})
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/data_quality.csv", index=False)
    print(table.to_string(index=False, float_format="{:.5f}".format))


# ---- wstETH ratio for holding wstETH (version C) ----

RATIO_MEDIAN_OF = 21  # traded minutes behind the causal ratio, fixed before the run


def wsteth_ratio(index: pd.DatetimeIndex, method: str = "causal", address: str = WSTETH_POOL) -> pd.Series:
    """
    WETH per wstETH on `index`, using only the trades before each timestamp (a price at t is what was known at t,
    the same as the spot prices):
      causal  the median of the last RATIO_MEDIAN_OF traded minutes before t. One bad print (0.78 on 2024-08-05)
              cannot move it; a discount that holds for most of the recent trades does (2022-11, about -3.3%).
      last    the last traded minute before t, uncleaned: the upper bound on what bad prints can do.
      centred the old series, kept only to compare against: hourly medians minus the hours more than 1.5% off the
              7-day centred median, log-interpolated across the gaps. Both use later prices, and the filter also
              drops the 2022-11 discount.
    Across hours without trades the ratio stays at its last value, so the staking yield of a long gap (the pool
    barely traded from 2022-08 to 2023-06) arrives in one step when trading resumes.
    """
    df = read_minutes(address)
    traded = df[(df["inAmount0"] > 0) | (df["inAmount1"] > 0)]
    minute = 1.0001 ** traded["closeTick"]
    if method == "centred":
        hourly = minute.resample("1h").median().dropna()
        ref = hourly.rolling("7D", center=True, min_periods=1).median()
        clean = hourly[(hourly / ref - 1).abs() <= 0.015]
        log = np.log(clean).reindex(index.union(clean.index)).interpolate(method="time").reindex(index)
        return np.exp(log.ffill().bfill())
    known = minute.rolling(RATIO_MEDIAN_OF, min_periods=1).median() if method == "causal" else minute
    known.index = known.index + pd.Timedelta(minutes=1)  # the close of minute m is known from m + 1 on
    out = known.reindex(index.union(known.index)).ffill().reindex(index)
    print(f"wstETH ratio ({method}): first known {known.index[0]}, {int(out.isna().sum())} hours before it")
    return out


# ---- Demeter LP sleeves ----

class SleeveLP(Strategy):
    """One LP position of +/- width around the price, checked at 00:00: out of range -> re-centre; off peg -> quote."""

    def __init__(self, s: Sleeve):
        super().__init__()
        self.s = s
        self.bounds = None
        self.started = False
        self.events = []  # every re-centre, guard exit and guard re-entry after the first placement

    def on_bar(self, snapshot: Snapshot):
        t = snapshot.timestamp
        if t.minute != 0 or t.hour != 0:
            return
        m: UniLpMarket = self.markets[KEY]
        price = m.market_status.data.price
        on_peg = self.s.guard is None or abs(price - 1) < self.s.guard
        was_placed = self.bounds is not None
        if was_placed and (not on_peg or not (self.bounds[0] <= price <= self.bounds[1])):
            m.remove_all_liquidity()
            base = self.broker.get_token_balance(self.s.base)
            if base > 0:
                m.swap(base, self.s.base, self.s.quote)
            self.bounds = None
            self.events.append(t)  # a re-centre or a guard exit
        if self.bounds is None and on_peg:
            lo, hi = price * Decimal(1 - self.s.width), price * Decimal(1 + self.s.width)
            t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
            m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)  # swaps part of the quote to the base
            self.bounds = (lo, hi)
            if self.started and not was_placed:
                self.events.append(t)  # re-entry after a guard exit
            self.started = True


def run_sleeve(s: Sleeve, bar: str | None, start: date, end: date) -> tuple[str, pd.DataFrame, list, float]:
    started = time.time()
    data, _ = load_market(KEY, s.pool(), s.address, start, end, bar, s.chain)
    market = UniLpMarket(KEY, s.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(s.quote, s.initial)
    price = data["price"].astype(float)
    actuator.set_price(pd.DataFrame({s.base.name: price, s.quote.name: 1.0}, index=data.index), s.quote)
    strategy = SleeveLP(s)
    actuator.strategy = strategy
    actuator.run(print_result=False)
    nav = actuator.account_status_df[("net_value", "")].astype(float)
    out = pd.DataFrame({"nav": nav.to_numpy() / s.initial, "price": price.reindex(nav.index).to_numpy()},
                       index=pd.DatetimeIndex(nav.index))
    return s.name, out, strategy.events, time.time() - started


def sleeves(minute: bool, holdout: bool = False):
    jobs = []
    for s in build_sleeves():
        if holdout:
            if s.name == "park_usdc" or s.name.startswith(("wsteth_lp", "cbbtc_lp")):
                jobs.append((s, "1h", s.start, HOLDOUT_END))
        elif minute:
            jobs.append((s, None, max(s.start, MINUTE_WINDOW[0]), min(s.end, MINUTE_WINDOW[1])))
        else:
            jobs.append((s, "1h", s.start, s.end))
    tag = HOLDOUT_TAG if holdout else "_1min" if minute else ""
    with multiprocessing.Pool(WORKERS) as pool:
        results = pool.starmap(run_sleeve, jobs)
    rows = []
    for name, out, events, secs in results:
        out.to_csv(f"{RESULT_DIR}/sleeve_{name}{tag}.csv")
        pd.Series(pd.DatetimeIndex(events), name="t").to_csv(f"{RESULT_DIR}/events_{name}{tag}.csv", index=False)
        nav = out["nav"]
        years = (nav.index[-1] - nav.index[0]).days / 365.25
        daily = nav.resample("D").last().pct_change().dropna()
        rows.append({"sleeve": name, "from": nav.index[0].date(), "to": nav.index[-1].date(),
                     "total": nav.iloc[-1] / nav.iloc[0] - 1, "annual": (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1,
                     "worst day": daily.min(), "worst day at": daily.idxmin().date(), "best day": daily.max(),
                     "best day at": daily.idxmax().date(), "events": len(events), "secs": round(secs)})
    table = pd.DataFrame(rows).set_index("sleeve")
    table.to_csv(f"{RESULT_DIR}/sleeves{tag}.csv")
    shown = table.copy()
    for c in ("total", "annual", "worst day", "best day"):
        shown[c] = shown[c].map(lambda v: f"{v:+.3%}")
    pd.set_option("display.width", 250)
    print(shown.to_string())


# ---- combine with the gate ----

def load_sleeve(name: str, tag: str = "") -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    out = pd.read_csv(f"{RESULT_DIR}/sleeve_{name}{tag}.csv", index_col=0, parse_dates=True)
    events = pd.read_csv(f"{RESULT_DIR}/events_{name}{tag}.csv", parse_dates=["t"])["t"]
    return out, pd.DatetimeIndex(events)


def index_on(series: pd.Series, index: pd.DatetimeIndex, start: str) -> pd.Series:
    """`series` on `index`, forward filled, divided by its value at `start`; 1 before `start` or before it begins."""
    s = series.reindex(index.union(series.index)).ffill().reindex(index)
    s = s / s.asof(pd.Timestamp(start))
    s[s.index < pd.Timestamp(start)] = 1.0
    return s.fillna(1.0)


def flatten(index: pd.Series, lo: str, hi: str) -> pd.Series:
    """The same index with no return between lo and hi: the March 2023 depeg without the parking fees."""
    r = index.pct_change().fillna(0.0)
    r.loc[lo:hi] = 0.0
    return (1 + r).cumprod() * index.iloc[0]


def combine():
    prices, _, _ = load_prices()
    hours = prices.index
    w = sr.gate(prices)  # columns eth, btc
    ratios = {m: wsteth_ratio(hours, m) for m in ("causal", "last", "centred")}
    park_usdc, ev_usdc = load_sleeve("park_usdc")
    park_dai, ev_dai = load_sleeve("park_dai")
    usdc_per_usdt = park_usdc["price"]  # USDC/USDT pool, quote USDC: USDC per USDT

    cash = {
        "usdc": pd.Series(1.0, index=hours),
        "park_usdc": index_on(park_usdc["nav"], hours, FULL[0]),
        "park_dai": index_on(park_dai["nav"] * usdc_per_usdt.reindex(park_dai.index).ffill(), hours, FULL[0]),
    }
    cash["park_usdc_flat"] = flatten(cash["park_usdc"], "2023-03-10", "2023-03-31")
    cash["park_dai_flat"] = flatten(cash["park_dai"], "2023-03-10", "2023-03-31")
    eth, btc = prices["eth"], prices["btc"]

    def version(eth_v: pd.Series, btc_v: pd.Series, cash_v: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({"eth": eth_v, "btc": btc_v, "cash": cash_v}, index=hours)

    def run(name, period, values, cost, cash_bps, gas_on, lp_events, scale):
        lo, hi = period
        gas = {s: mainnet_gas(eth, scale, swap_only=(kind == "swap")) for s, kind in gas_on.items()} if scale else None
        nav, trades, paid = simulate(w, values, start=lo, cost_bps=cost, cash_cost_bps=cash_bps, gas=gas, lp=lp_events)
        nav = nav[nav.index < hi]
        st = sr.stats(nav, lo, hi)
        return {"run": name, "period": f"{lo}~{hi}", "total": st["total"], "annual": st["annual"], "maxDD": st["maxDD"],
                "calmar": st["calmar"], "trades": trades, "swap $": round(paid["swap"]), "gas $": round(paid["gas"])}

    spot = {"eth": 10, "btc": 10}
    rows = []
    # None: no gas at all, a low-cost case only; an L2 has its own pools, volume and liquidity
    for capital in (None, 10_000, 100_000, 1_000_000):
        scale = 0 if capital is None else 100_000 / capital
        label = "no gas" if capital is None else f"gas, ${capital:,}"
        versions = {
            "A base": (version(eth, btc, cash["usdc"]), spot, 0.0, {}, {}),
            "B park USDC/USDT": (version(eth, btc, cash["park_usdc"]), spot, 0.5, {"cash": "lp"}, {"cash": ev_usdc}),
            "B park, 2023/3 flat": (version(eth, btc, cash["park_usdc_flat"]), spot, 0.5, {"cash": "lp"},
                                    {"cash": ev_usdc}),
            "B' park DAI/USDT": (version(eth, btc, cash["park_dai"]), spot, 1.5, {"cash": "lp"}, {"cash": ev_dai}),
            "B' park DAI, 2023/3 flat": (version(eth, btc, cash["park_dai_flat"]), spot, 1.5, {"cash": "lp"},
                                         {"cash": ev_dai}),
        }
        # the causal ratio is the result; the uncleaned last trade and the old centred series are for comparison
        for method, suffix in (("causal", ""), ("last", ", raw last trade"), ("centred", ", old centred ratio")):
            versions[f"C wstETH + park{suffix}"] = (version(eth * ratios[method], btc, cash["park_usdc"]),
                                                     {"eth": 11, "btc": 10}, 0.5, {"eth": "swap", "cash": "lp"},
                                                     {"cash": ev_usdc})
        for vname, (values, cost, cash_bps, gas_on, lp_events) in versions.items():
            rows.append({"gas": label, **run(vname, FULL, values, cost, cash_bps, gas_on, lp_events, scale)})
            if not vname.endswith("flat"):
                rows.append({"gas": label, **run(vname, SHORT, values, cost, cash_bps, gas_on, lp_events, scale)})
        for width in WIDTHS:
            eth_lp, ev_eth = load_sleeve(f"wsteth_lp{width:g}")
            btc_lp, ev_btc = load_sleeve(f"cbbtc_lp{width:g}")
            # ETH in wstETH/WETH LP (value in WETH x ETH price); BTC spot until the cbBTC data is clean, then LP
            eth_index = index_on(eth_lp["nav"], hours, SHORT[0])
            btc_v = btc * index_on(btc_lp["nav"], hours, CBBTC_CLEAN)
            # the wstETH/WETH LP earns much of its edge on two crash days, picked after seeing the sleeve runs
            calm = eth_index
            for day in CRASH_DAYS:
                calm = flatten(calm, day, f"{day} 23:59")
            for suffix, idx in (("", eth_index), (", crash days flat", calm)):
                values = version(eth * idx, btc_v, cash["park_usdc"])
                rows.append({"gas": label, **run(f"D full LP +/-{width:.1%}{suffix}", SHORT, values,
                                                 {"eth": 11, "btc": 11}, 0.5, {"eth": "lp", "btc": "lp", "cash": "lp"},
                                                 {"eth": ev_eth, "btc": ev_btc, "cash": ev_usdc}, scale)})
    table = pd.DataFrame(rows)
    base = table[table["run"] == "A base"].set_index(["gas", "period"])["total"]
    table["vs A pt"] = [100 * (r.total - base[(r.gas, r.period)]) for r in table.itertuples()]
    table.to_csv(f"{RESULT_DIR}/combine.csv", index=False)
    shown = table.copy()
    for c in ("total", "annual", "maxDD"):
        shown[c] = shown[c].map(lambda v: f"{v:+.1%}")
    shown["vs A pt"] = shown["vs A pt"].map(lambda v: f"{v:+.1f}")
    shown["calmar"] = shown["calmar"].round(2)
    pd.set_option("display.width", 250)
    for (gas_label, period), part in shown.groupby(["gas", "period"], sort=False):
        print(f"\n== {period}, {gas_label} ==")
        print(part.drop(columns=["gas", "period"]).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--sleeves", action="store_true")
    parser.add_argument("--minute", action="store_true", help="with --sleeves: minute bars over MINUTE_WINDOW")
    parser.add_argument("--holdout", action="store_true", help="with --sleeves: park_usdc and the D sleeves, on to HOLDOUT_END")
    parser.add_argument("--combine", action="store_true")
    cli = parser.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if cli.quality:
        quality()
    if cli.sleeves:
        sleeves(cli.minute, cli.holdout)
    if cli.combine:
        combine()
    print("YIELD_DONE")
