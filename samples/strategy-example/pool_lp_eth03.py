"""
H31 and H22R of reports/plan_2026-10-12_single_coin.md (registered 2026-10-12, before H17 - H28 ran): the ETH buy
ladder in 0.3% pools, once the colleague filled the data. Costs and mechanics as pool_lp_batch.py; the ladder is H4b's
g_down untouched ([p/1.40, p 1.01], re-centred hourly when out).

H31   0x8ad5 (USDC/WETH 0.3%, mainnet), $100k, the 16 windows of pool_lp_batch.py:
        e_down, e_spot100  ETH gate (88e6 EMA100, as H18-A)
        g_down, g_spot100  BTC gate (99ac EMA100, as H7), listed
      Verdict: (e_down - e_spot100) meets H2's 1-3. Listed: (g_down - g_spot100), and H18-A / H7 on 88e6 beside it.
H22R  0xc473 (WETH/USDC 0.3%, Arbitrum), ETH gate, $100k, Arbitrum gas, 12-month windows from 2023-07 .. 2025-10
      (10, the last ends 2026-09-30); e_down and e_spot100, and the same two on c696 (0.05%, Arbitrum), listed.
      Verdict: c473's (e_down - e_spot100) meets H2's 1-3 (>= 8 of 10 windows > 0).

Run from samples/strategy-example (sync 0x8ad5... and 0xc473... from S3 into ../real-data first):
  PYTHONPATH=../.. python pool_lp_eth03.py --test                  # short runs, one across c473's empty 2023-09-09
  PYTHONPATH=../.. python pool_lp_eth03.py --set h31 --workers 3   # also h22r
  PYTHONPATH=../.. python pool_lp_eth03.py --report
"""
import argparse
import multiprocessing
import os
from datetime import date

import pandas as pd

import pool_lp_batch as batch
import pool_lp_more  # noqa: F401  registers c473 on pool_lp_batch
from pool_lp_batch import Pool
from tri_btc_eth_gate import usdc, weth

batch.POOLS["8ad5"] = Pool("0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8", "ethereum", usdc, weth, usdc, 0.3, 60,
                           date(2021, 5, 5))
batch.GATE_SOURCE["8ad5"] = "99ac"
LADDER = dict(off="range", off_width=0.40, off_up=0.01)
g = dict(gated=True, on="spot")


def eth_gated(pool_key: str) -> list:
    return [batch.cfg(pool_key, "e_down", gate_src="88e6", **LADDER, **g),
            batch.cfg(pool_key, "e_spot100", gate_src="88e6", **g)]


SETS = {
    "h31": eth_gated("8ad5") + [batch.cfg("8ad5", "g_down", **LADDER, **g), batch.cfg("8ad5", "g_spot100", **g)],
    "h22r": eth_gated("c473") + eth_gated("c696"),
}


def tasks(name: str) -> list[tuple]:
    out = []
    for c in SETS[name]:
        starts = batch.window_starts(c.pool_key) if name == "h31" else batch.window_starts("c473")
        out += [(c, s, batch.window_end(s)) for s in starts]
    return out


def net(path: str) -> float:
    n = pd.read_csv(path, index_col=0, parse_dates=True)["net"]
    return n.iloc[-1] / n.iloc[0] - 1


def diff(pool_key: str, a: str, b: str, starts: list[date]) -> pd.Series:
    """(a - b) per window from the NAV files; NaN where a file is missing."""
    def one(v, s):
        p = f"{batch.RESULT_DIR}/nav_{pool_key}_{v}_ema100_{s}.csv"
        return net(p) if os.path.exists(p) else float("nan")
    return pd.Series([one(a, s) - one(b, s) for s in starts], index=starts)


def line(label: str, x: pd.Series, judged: bool) -> str:
    x = x.dropna()
    h = len(x) // 2
    c = batch.checks(x)
    v = ("PASS" if all(c.values()) else "fail: " + "; ".join(k for k, ok in c.items() if not ok)) if judged else "listed"
    return (f"{label}: median {x.median():+.4f}, positive {(x > 0).sum()}/{len(x)}, "
            f"halves {x.iloc[:h].median():+.4f} / {x.iloc[h:].median():+.4f} -> {v}\n"
            f"  by window: " + " ".join(f"{u * 100:+.1f}" for u in x))


def report():
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h31.csv"):
        s = batch.window_starts("8ad5")
        print(line("H31 8ad5 e_down - e_spot100", diff("8ad5", "e_down", "e_spot100", s), True))
        print(line("H31 8ad5 g_down - g_spot100 (BTC gate)", diff("8ad5", "g_down", "g_spot100", s), False))
        print(line("  88e6 e_down - e_spot100 (H18-A)", diff("88e6", "e_down", "e_spot100", s), False))
        print(line("  88e6 g_down - g_spot100 (H7)", diff("88e6", "g_down", "g_spot100", s), False))
    if os.path.exists(f"{batch.RESULT_DIR}/windows_h22r.csv"):
        s = batch.window_starts("c473")
        print(line("H22R c473 e_down - e_spot100", diff("c473", "e_down", "e_spot100", s), True))
        print(line("  c696 e_down - e_spot100", diff("c696", "e_down", "e_spot100", s), False))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--set", choices=list(SETS))
    a.add_argument("--test", action="store_true")
    a.add_argument("--report", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.eth_daily()  # fill the caches before the workers read them
    for src in ("99ac", "88e6"):
        batch.gate(src, 100)
    if a.test:
        for c, s, e in ((SETS["h31"][0], date(2022, 5, 3), date(2022, 5, 20)),
                        (SETS["h22r"][0], date(2023, 9, 3), date(2023, 9, 15))):
            print(pd.Series(batch.run(c, s, e)).to_string(), flush=True)
        return
    if a.set:
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            rows = pool.starmap(batch.run, tasks(a.set), chunksize=1)
        pd.DataFrame(rows).to_csv(f"{batch.RESULT_DIR}/windows_{a.set}.csv", index=False)
    if a.report or a.set:
        report()


if __name__ == "__main__":
    main()
