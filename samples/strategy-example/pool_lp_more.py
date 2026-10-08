"""
H20 - H22 of reports/single_pool_loop.md (registered 2026-10-08, after H16, before H17 - H19 ran). Costs and
mechanics as pool_lp_batch.py.

H20  g_down in three time slices. Slice k takes the price before UTC 00, 08 or 16 h as the daily close, runs the
     BTC EMA100 on those closes and switches at that hour (pool_lp_batch.gate(hour=)). Each slice is its own $100k
     run of g_down and g_spot100 on 0x99ac over the 16 windows; the book is the mean of the three (each normalised
     to 1). The 00 h slice is H4b's g_down and H13's g_spot100, read from their files.
       Verdict: (g_down_3 - g_spot100_3) meets H2's 1-3.
       Listed: per window, max - min of (g_down - g_spot100) over the three slices; and the same at a third of the
       capital ($33,333 a slice) with 3 gwei in every year (set h20_33k, its own process since gas is global).
H21  g_down on the BTC/ETH ratio in 0.3%: 0xCBCd (WBTC/WETH 0.3%, mainnet), 4585's ratio gate as H5, 40 WETH,
     12-month windows from 2022-01 .. 2023-10 (8, the last ends 2024-09-30; data ends 2024-10-01). g_down and
     g_spot100; H5's 4585 numbers over the same 8 windows are listed beside them.
       Verdict: (g_down - g_spot100) meets H2's 1-3 (>= 6 of 8 windows > 0).
H22  ETH ladder in 0.3%, listed only: 0xc473 (WETH/USDC 0.3%, Arbitrum, data 2023-06-11 .. 2024-08-05), the ETH gate
     of H18-A (88e6 EMA100), $100k, Arbitrum gas. 6-month windows from 2023-07, 2023-10, 2024-01. e_down and
     e_spot100, with the same two on c696 (WETH/USDC 0.05%, Arbitrum) over the same windows.

Data: sync 0xCBCd... and 0xc473... from S3 into ../real-data first.

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_more.py --test                  # one short run per new pool and slice
  PYTHONPATH=../.. python pool_lp_more.py --set h20 --workers 3   # also h20_33k, h21, h22
  PYTHONPATH=../.. python pool_lp_more.py --report
"""
import argparse
import multiprocessing
import os
from datetime import date

import pandas as pd

import pool_lp_batch as batch
from pool_lp_batch import Pool
from pool_lp_windows import GatedPool
from tri_btc_eth_gate import usdc, wbtc, weth

batch.POOLS["cbcd"] = Pool("0xCBCdF9626bC03E24f779434178A73a0B4bad62eD", "ethereum", wbtc, weth, weth, 0.3, 60,
                           date(2021, 5, 5))
batch.POOLS["c473"] = Pool("0xc473e2aEE3441BF9240Be85eb122aBB059A3B57c", "arbitrum", weth, usdc, usdc, 0.3, 60,
                           date(2023, 6, 11))
batch.GATE_SOURCE.update({"cbcd": "4585", "c473": "88e6"})
HOURS = (0, 8, 16)
SLICE_33K = 100_000 / 3
LADDER = dict(off="range", off_width=0.40, off_up=0.01)
g = dict(gated=True, on="spot")
H21_STARTS = [date(y, m, 1) for y in (2022, 2023) for m in (1, 4, 7, 10)]
H22_WINDOWS = [(date(2023, 7, 1), date(2023, 12, 31)), (date(2023, 10, 1), date(2024, 3, 31)),
               (date(2024, 1, 1), date(2024, 6, 30))]


class HourGated(GatedPool):
    """GatedPool that reads the gate and switches at cfg.gate_hour instead of 00:00."""

    def on_bar(self, snapshot):
        t = snapshot.timestamp
        price = self.markets[batch.KEY].market_status.data.price
        if self.state is None or (t.hour == self.cfg.gate_hour and t.minute == 0):
            on = bool(self.gate.asof(pd.Timestamp(t)))
            if on != self.state:
                self.go(on, price, t)
        elif t.minute == 0 and self.mode == "range" and not (self.bounds[0] <= price <= self.bounds[1]):
            self.remove()
            self.place(price, 0.0, "recentre", t)
        if t.minute == 0:
            self.log_weight(t, price)


batch.GatedPool = HourGated  # pool_lp_batch.run builds the gated strategy from this name; the workers fork after


def slice_cfgs(hour: int, initial: float | None = None, tag: str = "") -> list:
    return [batch.cfg("99ac", f"g_down{tag}_h{hour:02d}", initial=initial, gate_hour=hour, **LADDER, **g),
            batch.cfg("99ac", f"g_spot100{tag}_h{hour:02d}", initial=initial, gate_hour=hour, **g)]


def eth_gated(pool_key: str) -> list:
    return [batch.cfg(pool_key, "e_down", gate_src="88e6", **LADDER, **g),
            batch.cfg(pool_key, "e_spot100", gate_src="88e6", **g)]


SETS = {
    "h20": slice_cfgs(8) + slice_cfgs(16),
    "h20_33k": [c for h in HOURS for c in slice_cfgs(h, SLICE_33K, "_33k")],
    "h21": [batch.cfg("cbcd", "g_down", **LADDER, **g), batch.cfg("cbcd", "g_spot100", **g)],
    "h22": eth_gated("c473") + eth_gated("c696"),
}


def tasks(name: str) -> list[tuple]:
    if name in ("h20", "h20_33k"):
        return [(c, s, batch.window_end(s)) for c in SETS[name] for s in batch.window_starts("99ac")]
    if name == "h21":
        return [(c, s, batch.window_end(s)) for c in SETS[name] for s in H21_STARTS]
    return [(c, s, e) for c in SETS[name] for s, e in H22_WINDOWS]


def net(path: str) -> float:
    n = pd.read_csv(path, index_col=0, parse_dates=True)["net"]
    return n.iloc[-1] / n.iloc[0] - 1


def slice_net(version: str, hour: int, start: date) -> float:
    """The net of one slice's window; the 00 h slice at $100k comes from H4b (g_down) and H13 (g_spot100)."""
    name = f"{version}_h{hour:02d}"
    paths = [f"{batch.RESULT_DIR}/nav_99ac_{name}_ema100_{start}.csv"]
    if hour == 0 and version == "g_down":
        paths = [f"result/pool-lp-windows/nav_g_down_{start}.csv",
                 f"{batch.RESULT_DIR}/nav_99ac_g_down_ema100_{start}.csv"] + paths
    elif hour == 0 and version == "g_spot100":
        paths = [f"{batch.RESULT_DIR}/nav_99ac_g_spot100_ema100_{start}.csv"] + paths
    return net(next(p for p in paths if os.path.exists(p)))


def verdict(x: pd.Series) -> str:
    c = batch.checks(x)
    return "PASS" if all(c.values()) else "fail: " + "; ".join(k for k, ok in c.items() if not ok)


def report_h20(tag: str = ""):
    starts = batch.window_starts("99ac")
    d = pd.DataFrame({h: [slice_net(f"g_down{tag}", h, s) - slice_net(f"g_spot100{tag}", h, s) for s in starts]
                      for h in HOURS}, index=starts)
    x = d.mean(axis=1)  # each slice starts at 1, so the mean of the nets is the book's net
    print(f"H20{tag} g_down_3 - g_spot100_3: median {x.median():.4f}, positive {(x > 0).sum()}/{len(x)}, "
          f"halves {x.iloc[:8].median():.4f} / {x.iloc[8:].median():.4f} -> {verdict(x)}")
    d["book"], d["spread"] = x, d[list(HOURS)].max(axis=1) - d[list(HOURS)].min(axis=1)
    print((d * 100).round(1).to_string())
    print(f"  median spread across slices {d['spread'].median():.4f}")


def report():
    pd.set_option("display.width", 250)
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h20.csv"):
        report_h20()
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h20_33k.csv"):
        report_h20("_33k")
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h21.csv"):
        t = pd.read_csv(f"{batch.RESULT_DIR}/windows_h21.csv")
        n = t.pivot(index="start", columns="version", values="net").sort_index()
        x = n["g_down"] - n["g_spot100"]
        print(f"H21 cbcd g_down - g_spot100: median {x.median():.4f}, positive {(x > 0).sum()}/{len(x)}, "
              f"halves {x.iloc[:4].median():.4f} / {x.iloc[4:].median():.4f} -> {verdict(x)}")
        print("  by window:", " ".join(f"{v * 100:+.1f}" for v in x))
        h5 = f"{batch.RESULT_DIR}/windows_h5_4585.csv"
        if os.path.exists(h5):
            m = pd.read_csv(h5).pivot(index="start", columns="version", values="net")
            y = (m["g_down"] - m["g_spot100"]).reindex(x.index)
            print("  4585 (H5), same windows:", " ".join(f"{v * 100:+.1f}" for v in y), f"median {y.median():.4f}")
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h22.csv"):
        t = pd.read_csv(f"{batch.RESULT_DIR}/windows_h22.csv")
        n = t.pivot_table(index="start", columns=["pool", "version"], values="net")
        for pool in ("c473", "c696"):
            x = n[(pool, "e_down")] - n[(pool, "e_spot100")]
            print(f"H22 {pool} e_down - e_spot100 (listed):", " ".join(f"{v * 100:+.1f}" for v in x))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--set", choices=list(SETS))
    a.add_argument("--test", action="store_true")
    a.add_argument("--report", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.eth_daily()  # fill the caches before the workers read them
    for src, hour in (("99ac", 0), ("99ac", 8), ("99ac", 16), ("4585", 0), ("88e6", 0)):
        batch.gate(src, 100, hour)
    if a.test:
        for c, s, e in ((SETS["h20"][0], date(2023, 1, 1), date(2023, 1, 31)),
                        (SETS["h21"][0], date(2022, 5, 1), date(2022, 5, 15)),
                        (SETS["h22"][0], date(2023, 8, 1), date(2023, 8, 15))):
            print(pd.Series(batch.run(c, s, e)).to_string(), flush=True)
        return
    if a.set:
        if a.set == "h20_33k":
            batch.GAS_GWEI = {y: 3 for y in range(2021, 2027)}  # read by pool_lp_batch.run; the workers fork after
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            rows = pool.starmap(batch.run, tasks(a.set), chunksize=1)
        pd.DataFrame(rows).to_csv(f"{batch.RESULT_DIR}/windows_{a.set}.csv", index=False)
    if a.report or a.set:
        report()


if __name__ == "__main__":
    main()
