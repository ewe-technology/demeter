"""
H32 of reports/plan_2026-10-12_two_coin.md (registered 2026-10-12, after the week's queue started, before any of
H17 - H31 had results): while the BTC gate is off, both coins buy back below in their own stablecoin pool instead of
sitting in USDC. H19's frame (pool_lp_combo.book): the 16 windows of H4b, half the capital in a BTC sleeve and half
in an ETH sleeve, each from cash, no rebalancing inside the window, each sleeve's net value from its own $100k run
normalised to 1. Both sleeves on the BTC gate (99ac EMA100):

  D0       BTC g_spot100 (99ac, H13)   ETH g_spot100 (8ad5, H31)     the control
  D1       BTC g_down    (99ac, H4b)   ETH g_down    (8ad5, H31)
  D0_88e6  BTC g_spot100               ETH g_spot100 (88e6, H7)      listed, with D1_88e6
  D1_88e6  BTC g_down                  ETH g_down    (88e6, H7)
  D1_btc   BTC g_down                  ETH g_spot100 (8ad5)          listed

Verdict: (D1 - D0) meets H2's 1-3 and D1's median max drawdown (hourly) is no more than 2 pt worse than D0's.
Listed: D1_88e6 - D0_88e6, D1_btc - D0, D1 - D1_btc, and every book rebalanced to 50/50 at each quarter start.

Inputs on the backtest host: H4b's result/pool-lp-windows/nav_g_down_<start>.csv and result/pool-lp-batch/
nav_{99ac,88e6,8ad5}_{g_down,g_spot100}_ema100_<start>.csv (8ad5 from pool_lp_eth03.py --set h31). No Demeter runs.

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_ladder_book.py          # every book whose inputs exist
"""
import os

import pandas as pd

import pool_lp_batch as batch
import pool_lp_combo as combo
import pool_lp_eth03  # noqa: F401  registers 8ad5 on pool_lp_batch

g = dict(gated=True, on="spot")
combo.SLEEVE_CFG.update({
    "eth_down_8ad5": batch.cfg("8ad5", "g_down", **combo.LADDER, **g),
    "eth_spot_8ad5": batch.cfg("8ad5", "g_spot100", **g),
    "eth_down_88e6": batch.cfg("88e6", "g_down", **combo.LADDER, **g),
})
BOOKS = {"D0": ("btc_spot", "eth_spot_8ad5"), "D1": ("btc_down", "eth_down_8ad5"),
         "D0_88e6": ("btc_spot", "eth_spot_btcgate"), "D1_88e6": ("btc_down", "eth_down_88e6"),
         "D1_btc": ("btc_down", "eth_spot_8ad5")}
DIFFS = (("D1 - D0", "D1", "D0", True), ("D1_88e6 - D0_88e6", "D1_88e6", "D0_88e6", False),
         ("D1_btc - D0", "D1_btc", "D0", False), ("D1 - D1_btc", "D1", "D1_btc", False),
         ("D1_q - D0_q", "D1_q", "D0_q", False))


def available(name: str) -> bool:
    return all(any(os.path.exists(p) for p in combo.sleeve_paths(name, s)) for s in batch.window_starts("99ac"))


def main():
    pd.set_option("display.width", 250)
    books = {b: pair for b, pair in BOOKS.items() if all(available(n) for n in pair)}
    missing = sorted(set(BOOKS) - set(books))
    if missing:
        print("inputs missing for", missing)
    rows = []
    for s in batch.window_starts("99ac"):
        navs = {n: combo.load_nav(n, s) for n in {x for pair in books.values() for x in pair}}
        for b, (bn, en) in books.items():
            for reb in (False, True):
                nav = combo.book(navs[bn], navs[en], reb)
                rows.append({"book": b + ("_q" if reb else ""), "start": s, "net": nav.iloc[-1] - 1,
                             "maxDD": combo.max_dd(nav)})
    t = pd.DataFrame(rows)
    t.to_csv(f"{batch.RESULT_DIR}/windows_h32.csv", index=False)
    nets = t.pivot(index="start", columns="book", values="net").sort_index()
    dds = t.pivot(index="start", columns="book", values="maxDD").sort_index()
    print((nets * 100).round(1).to_string())
    for name, a, b, judged in DIFFS:
        if a not in nets or b not in nets:
            continue
        x = nets[a] - nets[b]
        c = batch.checks(x)
        half = len(x) // 2
        dd_ok = dds[a].median() >= dds[b].median() - combo.MAX_DD_SLACK
        verdict = ("PASS" if all(c.values()) and dd_ok else "fail: " + "; ".join(
            [k for k, ok in c.items() if not ok] + ([] if dd_ok else ["maxDD more than 2 pt worse"]))) if judged else "listed"
        print(f"H32 {name}: median {x.median():+.4f}, positive {(x > 0).sum()}/{len(x)}, halves "
              f"{x.iloc[:half].median():+.4f} / {x.iloc[half:].median():+.4f}, median maxDD {dds[a].median():+.4f} vs "
              f"{dds[b].median():+.4f} -> {verdict}")
        print("  by window:", " ".join(f"{v * 100:+.1f}" for v in x))


if __name__ == "__main__":
    main()
