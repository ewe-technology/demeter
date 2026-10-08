"""
H23 of reports/single_pool_loop.md (registered 2026-10-08, a colleague's idea): the live BTC gate, but while it is on
the book sits in a WBTC/WETH LP instead of 50% ETH + 50% BTC spot, and while it is off in the USDC/USDT parking LP.

  B   control: on 50% ETH + 50% BTC spot, off parked in USDC/USDT (yield_layer.py's "B park USDC/USDT")
  L   on: all of the book in a WBTC/WETH LP of +/- width, off: parked as in B

Gate: spot_robustness.gate (BTC above its EMA100 at 00:00 UTC, the live rule), on sleeve_sim.simulate like
yield_layer.combine. The LP is a value index from its own Demeter run (yield_layer.SleeveLP: one position always open,
re-centred at 00:00 when out, hourly bars, 40 WETH), in WETH, times the ETH price. Costs as yield_layer: spot 10 bps,
the LP 11 bps (one more hop), parking 0.5 bp; mainnet gas through sleeve_sim.mainnet_gas for the LP (enter, exit,
every re-centre while held) and the parking LP.

Pools and periods:
  4585  WBTC/WETH 0.05%, mainnet   2022-01-01 .. 2026-09-30
  cbcd  WBTC/WETH 0.3%,  mainnet   2022-01-01 .. 2024-09-30 (data ends 2024-10-01; rerun when it is filled)
Widths: +/- 10% (the old LP version's width, section 8 of spot_yield_and_basket.md) judged, +/- 20% listed.

Verdict, fixed before the run (commit of this file), per pool at +/- 10% and $100k:
  L passes if (L - B) total return over the period is > 0 and (L - B) is > 0 in at least two thirds of the calendar
  years (2022 .. 2026, 2026 to 09-30: >= 4 of 5 for 4585; 2022 .. 2024, 2024 to 09-30: >= 2 of 3 for cbcd).
Listed: +/- 20%, no gas and $1M, max drawdown.
Prior evidence (before the run): section 8 found the 4585 LP at +/- 10% about 5.8% a year behind holding its coins,
and H5 failed on 4585, so 4585 is expected to fail; cbcd has never been tested.

Run from samples/strategy-example (spot price cache of spot_btc_eth_gate.py and yield_layer's park_usdc_to2026 must
exist; sync 0xCBCd... from S3 first):
  PYTHONPATH=../.. python ratio_lp_gate.py --sleeves     # 4 Demeter runs
  PYTHONPATH=../.. python ratio_lp_gate.py --combine
"""
import argparse
import math
import multiprocessing
import os
from dataclasses import dataclass
from datetime import date

import pandas as pd

import spot_robustness as sr
import yield_layer as yl
from demeter.uniswap import UniV3Pool
from sleeve_sim import mainnet_gas, simulate
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import wbtc, weth

RESULT_DIR = "result/ratio-lp-gate"
POOLS = {"4585": ("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, 10, "2022-01-01", "2026-10-01"),
         "cbcd": ("0xCBCdF9626bC03E24f779434178A73a0B4bad62eD", 0.3, 60, "2022-01-01", "2024-10-01")}
WIDTHS = (0.10, 0.20)
JUDGED_WIDTH = 0.10
INITIAL_WETH = 40


@dataclass(frozen=True)
class RatioSleeve(yl.Sleeve):
    fee: float = 0.05
    spacing: int = 10

    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=self.fee, quote_token=self.quote,
                         tick_spacing=self.spacing)


def sleeves() -> list[RatioSleeve]:
    out = []
    for key, (address, fee, spacing, lo, hi) in POOLS.items():
        for w in WIDTHS:
            out.append(RatioSleeve(f"{key}_w{round(w * 100)}", address, wbtc, weth, weth, date.fromisoformat(lo),
                                   date.fromisoformat(hi), w, INITIAL_WETH, fee=fee, spacing=spacing))
    return out


def run_sleeves(workers: int):
    jobs = [(s, "1h", s.start, s.end) for s in sleeves()]
    with multiprocessing.Pool(workers) as pool:
        results = pool.starmap(yl.run_sleeve, jobs)
    for name, out, events, secs in results:
        out.to_csv(f"{RESULT_DIR}/sleeve_{name}.csv")
        pd.Series(pd.DatetimeIndex(events), name="t").to_csv(f"{RESULT_DIR}/events_{name}.csv", index=False)
        nav = out["nav"]
        print(f"{name}: {nav.index[0].date()} .. {nav.index[-1].date()}, total {nav.iloc[-1] / nav.iloc[0] - 1:+.2%} "
              f"in WETH, {len(events)} re-centres, {secs:.0f} s", flush=True)


def load(name: str) -> tuple[pd.Series, pd.DatetimeIndex]:
    out = pd.read_csv(f"{RESULT_DIR}/sleeve_{name}.csv", index_col=0, parse_dates=True)
    events = pd.read_csv(f"{RESULT_DIR}/events_{name}.csv", parse_dates=["t"])["t"]
    return out["nav"], pd.DatetimeIndex(events)


def years_of(lo: str, hi: str) -> list[tuple[str, str]]:
    return [(f"{y}-01-01", min(f"{y + 1}-01-01", hi)) for y in range(int(lo[:4]), int(hi[:4]) + (hi[5:] != "01-01"))]


def combine():
    prices, _, _ = load_prices()
    hours = prices.index
    eth, btc = prices["eth"], prices["btc"]
    w = sr.gate(prices)
    park, ev_park = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
    cash = yl.index_on(park["nav"], hours, yl.FULL[0])
    rows = []
    for key, (_, _, _, lo, hi) in POOLS.items():
        for width in WIDTHS:
            lp, ev_lp = load(f"{key}_w{round(width * 100)}")
            lp_v = eth * yl.index_on(lp, hours, lo)
            books = {
                "B": (w, pd.DataFrame({"eth": eth, "btc": btc, "cash": cash}), {"eth": 10, "btc": 10},
                      {"cash": "lp"}, {"cash": ev_park}),
                "L": (pd.DataFrame({"lp": w["eth"] + w["btc"]}), pd.DataFrame({"lp": lp_v, "cash": cash}),
                      {"lp": 11}, {"lp": "lp", "cash": "lp"}, {"lp": ev_lp, "cash": ev_park}),
            }
            for capital in (None, 100_000, 1_000_000):
                scale = 0 if capital is None else 100_000 / capital
                for name, (weights, values, cost, gas_on, lp_events) in books.items():
                    gas = {s: mainnet_gas(eth, scale) for s in gas_on} if scale else None
                    nav, trades, paid = simulate(weights, values, start=lo, cost_bps=cost, cash_cost_bps=0.5, gas=gas,
                                                 lp=lp_events)
                    nav = nav[nav.index < hi]
                    st = sr.stats(nav, lo, hi)
                    row = {"pool": key, "width": width, "capital": capital or 0, "book": name, "total": st["total"],
                           "maxDD": st["maxDD"], "trades": trades, "swap $": round(paid["swap"]),
                           "gas $": round(paid["gas"])}
                    row.update({y0[:4]: sr.stats(nav, y0, y1)["total"] for y0, y1 in years_of(lo, hi)})
                    rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/combine.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    for (key, width, capital), part in t.groupby(["pool", "width", "capital"], sort=False):
        b, l = part.set_index("book").loc["B"], part.set_index("book").loc["L"]
        lo, hi = POOLS[key][3], POOLS[key][4]
        yrs = [y0[:4] for y0, _ in years_of(lo, hi)]
        diff = {y: l[y] - b[y] for y in yrs}
        need = math.ceil(2 * len(yrs) / 3)
        ok = l["total"] - b["total"] > 0 and sum(v > 0 for v in diff.values()) >= need
        judged = width == JUDGED_WIDTH and capital == 100_000
        print(f"{key} +/-{width:.0%} {'no gas' if not capital else f'${capital:,}'}: L - B total "
              f"{l['total'] - b['total']:+.4f}, by year " + " ".join(f"{y} {v:+.3f}" for y, v in diff.items())
              + f", maxDD L {l['maxDD']:+.3f} B {b['maxDD']:+.3f}"
              + (f" -> {'PASS' if ok else 'fail'} (needs {need}/{len(yrs)} years > 0)" if judged else " (listed)"))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--sleeves", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if a.sleeves:
        run_sleeves(a.workers)
    if a.combine:
        combine()


if __name__ == "__main__":
    main()
