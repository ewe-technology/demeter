"""
H33 of reports/plan_2026-10-12_two_coin.md (registered 2026-10-13, after the results of H17 - H32): the candidate to
run live. Not new evidence: its parts were seen in H26 (the daily-checked ladder) and H19 (P1). H19's frame
(pool_lp_combo.book): the 16 windows of H4b, half the capital in a BTC sleeve and half in an ETH sleeve, each from
cash, no rebalancing inside the window, both on the BTC gate (99ac EMA100, 00 UTC):

  C0         BTC g_spot100 (99ac)                          ETH g_spot100 (88e6)    the live gate, spot
  C1         BTC g_down_d1x (H26: re-centred at 00 only)   ETH g_spot100 (88e6)    the candidate
  C1_hourly  BTC g_down (H4b, hourly re-centre) = H19's P1  ETH g_spot100 (88e6)   listed, $100k only

Each capital runs both sleeves at that capital and takes half of each. $100k reads existing NAVs; $10k and $1M run
what is missing (88e6 g_spot100 at both, 99ac g_down_d1x at $1M: 48 runs).
Verdict ($100k, each year's gas): (C1 - C0) meets H2's 1-3 and C1's median max drawdown (hourly) is no more than
2 pt worse than C0's. Listed: $10k and $1M, C1 - C1_hourly, the books rebalanced to 50/50 at every quarter start,
and the median gas and price impact of each sleeve.

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_candidate.py --runs --workers 3   # the missing runs
  PYTHONPATH=../.. python pool_lp_candidate.py --report
"""
import argparse
import glob
import multiprocessing
import os

import pandas as pd

import pool_lp_batch as batch
import pool_lp_combo as combo
import pool_lp_robust as robust  # noqa: F401  sets pool_lp_batch.GatedPool to RobustGated (daily_check)

g = dict(gated=True, on="spot")
CAPITALS = {100_000: "", 10_000: "_10k", 1_000_000: "_1m"}
JUDGED = 100_000
for cap, tag in CAPITALS.items():
    combo.SLEEVE_CFG[f"btc_spot{tag}"] = batch.cfg("99ac", f"g_spot100{tag}", initial=cap, **g)
    combo.SLEEVE_CFG[f"btc_d1x{tag}"] = robust.rcfg(f"g_down_d1x{tag}", initial=cap, daily_check=True,
                                                     **combo.LADDER)
    combo.SLEEVE_CFG[f"eth_spot{tag}"] = batch.cfg("88e6", f"g_spot100{tag}", initial=cap, **g)


def books(tag: str) -> dict:
    out = {"C0": (f"btc_spot{tag}", f"eth_spot{tag}"), "C1": (f"btc_d1x{tag}", f"eth_spot{tag}")}
    if tag == "":
        out["C1_hourly"] = ("btc_down", "eth_spot")
    return out


def missing() -> list[tuple]:
    names = {n for tag in CAPITALS.values() for pair in books(tag).values() for n in pair}
    return [(combo.SLEEVE_CFG[n], s, batch.window_end(s)) for n in sorted(names) for s in batch.window_starts("99ac")
            if not any(os.path.exists(p) for p in combo.sleeve_paths(n, s))]


def costs() -> pd.DataFrame:
    """Median gas and price impact per sleeve, from every windows_*.csv that holds it."""
    rows = []
    for f in glob.glob(f"{batch.RESULT_DIR}/windows_*.csv") + glob.glob("result/pool-lp-windows/windows_*.csv"):
        t = pd.read_csv(f, dtype={"pool": str})  # "88e6" would otherwise read as a float
        if {"version", "start", "gas", "impact"} <= set(t.columns):
            t = t.assign(pool=t["pool"] if "pool" in t else "99ac", ema=t["ema"] if "ema" in t else 100)
            rows.append(t[["pool", "version", "ema", "start", "gas", "impact"]])
    t = pd.concat(rows).drop_duplicates(["pool", "version", "ema", "start"], keep="last")
    starts = {str(s) for s in batch.window_starts("99ac")}
    out = []
    for name, c in combo.SLEEVE_CFG.items():
        if not name.startswith(("btc_spot", "btc_d1x", "eth_spot")) and name != "btc_down":
            continue
        m = t[(t["pool"] == c.pool_key) & (t["version"] == c.name) & (t["ema"] == c.ema)
              & t["start"].astype(str).isin(starts)]
        if len(m):
            out.append({"sleeve": name, "windows": len(m), "gas": m["gas"].median(), "impact": m["impact"].median()})
    return pd.DataFrame(out)


def report():
    pd.set_option("display.width", 250)
    rows = []
    for cap, tag in CAPITALS.items():
        bk = books(tag)
        for s in batch.window_starts("99ac"):
            navs = {n: combo.load_nav(n, s) for n in {x for pair in bk.values() for x in pair}}
            for b, (bn, en) in bk.items():
                for reb in (False, True):
                    nav = combo.book(navs[bn], navs[en], reb)
                    rows.append({"capital": cap, "book": b + ("_q" if reb else ""), "start": s,
                                 "net": nav.iloc[-1] - 1, "maxDD": combo.max_dd(nav)})
    t = pd.DataFrame(rows)
    t.to_csv(f"{batch.RESULT_DIR}/windows_h33_books.csv", index=False)
    for cap in CAPITALS:
        p = t[t["capital"] == cap]
        nets = p.pivot(index="start", columns="book", values="net").sort_index()
        dds = p.pivot(index="start", columns="book", values="maxDD").sort_index()
        print(f"--- ${cap:,}: net by window, %")
        print((nets * 100).round(1).to_string())
        for name, a, b in (("C1 - C0", "C1", "C0"), ("C1_q - C0_q", "C1_q", "C0_q"),
                           ("C1 - C1_hourly", "C1", "C1_hourly")):
            if a not in nets or b not in nets:
                continue
            x = nets[a] - nets[b]
            c = batch.checks(x)
            half = len(x) // 2
            dd_ok = dds[a].median() >= dds[b].median() - combo.MAX_DD_SLACK
            judged = cap == JUDGED and name == "C1 - C0"
            verdict = ("PASS" if all(c.values()) and dd_ok else "fail: " + "; ".join(
                [k for k, ok in c.items() if not ok] + ([] if dd_ok else ["maxDD more than 2 pt worse"]))) \
                if judged else "listed"
            print(f"H33 ${cap:,} {name}: median {x.median():+.4f}, positive {(x > 0).sum()}/{len(x)}, halves "
                  f"{x.iloc[:half].median():+.4f} / {x.iloc[half:].median():+.4f}, median maxDD "
                  f"{dds[a].median():+.4f} vs {dds[b].median():+.4f} -> {verdict}")
            print("  by window:", " ".join(f"{v * 100:+.1f}" for v in x))
    print("--- median cost per sleeve over its windows (share of the sleeve's capital, listed)")
    print(costs().to_string(index=False, float_format=lambda v: f"{v:.4f}"))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--runs", action="store_true")
    a.add_argument("--report", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.eth_daily()  # fill the caches before the workers read them
    batch.gate("99ac", 100)
    if a.runs:
        tasks = missing()
        print(f"{len(tasks)} runs", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            rows = pool.starmap(batch.run, tasks, chunksize=1)
        pd.DataFrame(rows).to_csv(f"{batch.RESULT_DIR}/windows_h33.csv", index=False)
    if a.report or a.runs:
        report()


if __name__ == "__main__":
    main()
