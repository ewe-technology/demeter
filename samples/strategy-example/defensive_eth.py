"""
H45 of reports/plan_2026-10-14_out_of_sample.md (registered in 72f83dd, an after-the-fact idea, before this code ran):
version C + full g_down, with the ETH half's target share at half the BTC gate (three slices) and half F'.

  C          ETH half: wstETH while the gate is on, parked while off; BTC half: WBTC / parked (H34's C)
  C+g        BTC half: H34's full g_down (the nav files of half_vs_c.py's "full" runs); ETH half as C (listed)
  C+g+def    BTC half as C+g; ETH half: 0.5 x the gate's slice mean + 0.5 x F' spot's ETH share, where F' spot's
             share is H40's fp_spot continuous book (UTC 00, Binance F') right after each of its trades, held until
             the next trade (no drift)

Everything else is candidate_vs_c.py: $100k, two halves from 2022-01-01 with no rebalancing between them, C's
costs and parking, wstETH, hourly bars, cut at 2026-08-31 (the last day of the Binance file).
Verdict (fixed in the plan, H34's rule): (C+g+def - C) total > 0, > 0 in at least 4 of the 5 calendar years 2022 ..
2026 (to 8/31), and C+g+def's max drawdown (hourly) no more than 2 pt worse than C's.

Run from samples/strategy-example on the host that has the H37 / H40 results:
  PYTHONPATH=../.. python defensive_eth.py --test    # C and C+g cut at 2026-08-31 against nav_h37.csv
  PYTHONPATH=../.. python defensive_eth.py
"""
import argparse
import os
from datetime import date

import pandas as pd

import candidate_vs_c as cvc
import cost_matrix as cm
import yield_layer as yl
from spot_btc_eth_gate import load_prices

RESULT_DIR = "result/defensive-eth"
LO, HI = "2022-01-01", "2026-09-01"  # HI is exclusive: through 2026-08-31 23:00
BOOK, N = 100_000, 3
FP_DIR = "result/fprime-spot"


def fp_share(index: pd.DatetimeIndex) -> pd.Series:
    """fp_spot's ETH share right after each trade, held until the next one; 0 before its first trade."""
    nav = pd.read_csv(f"{FP_DIR}/nav_fp_spot_cont.csv", index_col=0, parse_dates=True)
    trades = pd.read_csv(f"{FP_DIR}/trades_fp_spot_cont.csv", parse_dates=["t"])
    at = pd.DatetimeIndex(trades["t"].drop_duplicates())
    share = (nav["eth"] * nav["price"] / nav["net_pre"]).loc[at]
    return share.reindex(index.union(at)).ffill().reindex(index).fillna(0.0).clip(0.0, 1.0)


def books():
    prices, _, _ = load_prices()
    park, park_events = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
    cash = yl.index_on(park["nav"], prices.index, yl.FULL[0])
    ratio = yl.wsteth_ratio(prices.index, "causal").bfill()
    cm.G.update(eth=prices["eth"], gwei=None)  # read by cost_matrix.gas_fn
    eth_values = pd.DataFrame({"eth": prices["eth"] * ratio, "cash": cash})
    btc_values = pd.DataFrame({"btc": prices["btc"], "cash": cash})
    gate = cvc.gate_share(prices.index, N)
    fp = fp_share(prices.index)
    w_def = 0.5 * gate + 0.5 * fp
    eth_c, eth_c_tr, eth_c_paid = cvc.half_sim("eth", gate, eth_values, LO, HI, BOOK, park_events)
    eth_d, eth_d_tr, eth_d_paid = cvc.half_sim("eth", w_def, eth_values, LO, HI, BOOK, park_events)
    btc_c, btc_tr, btc_paid = cvc.half_sim("btc", gate, btc_values, LO, HI, BOOK, park_events)
    btc_g = cvc.btc_half_g(BOOK, N, eth_c.index, date(2022, 1, 1))
    out = {"C": 0.5 * eth_c + 0.5 * btc_c, "C+g": 0.5 * eth_c + 0.5 * btc_g, "C+g+def": 0.5 * eth_d + 0.5 * btc_g,
           "ETH half C": eth_c, "ETH half def": eth_d, "BTC half C": btc_c, "BTC half g": btc_g}
    counts = {"ETH half C trades": eth_c_tr, "ETH half def trades": eth_d_tr, "BTC half C trades": btc_tr,
              "ETH half def gas_usd": eth_d_paid["gas"] * (BOOK / 2) / 100_000,
              "ETH half C gas_usd": eth_c_paid["gas"] * (BOOK / 2) / 100_000,
              "mean ETH target C": float(gate.loc[LO:].mean()), "mean ETH target def": float(w_def.loc[LO:].mean())}
    return out, counts


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    out, counts = books()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    if a.test:
        ref = pd.read_csv(f"{cvc.RESULT_DIR}/nav_h37.csv", index_col=0, parse_dates=True)
        for k in ("C", "C+g"):
            r = ref["C+g-full" if k == "C+g" else k]
            r = r[r.index < HI]
            print(f"{k}: here {out[k].iloc[-1]:.6f}, nav_h37 at the same hour {r.iloc[-1]:.6f}, "
                  f"max abs diff {float((out[k] - r.reindex(out[k].index)).abs().max()):.2e}")
        return
    rows = [{"version": k, **cvc.row(v, LO, HI)} for k, v in out.items()]
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/combine_h45.csv", index=False)
    pd.DataFrame(out).to_csv(f"{RESULT_DIR}/nav_h45.csv")
    pd.Series(counts).to_csv(f"{RESULT_DIR}/counts_h45.csv")
    print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    print(pd.Series(counts).to_string())
    yrs = [y0[:4] for y0, _ in cvc.years(LO, HI)]
    p = t.set_index("version")
    for cand, judged in (("C+g+def", True), ("C+g", False)):
        x, b = p.loc[cand], p.loc["C"]
        diff = {y: x[y] - b[y] for y in yrs}
        ok = x["total"] - b["total"] > 0 and sum(v > 0 for v in diff.values()) >= min(4, len(yrs)) \
            and x["maxDD"] >= b["maxDD"] - 0.02
        print(f"H45 {cand} - C: total {x['total'] - b['total']:+.4f}, by year "
              + " ".join(f"{y} {v:+.3f}" for y, v in diff.items())
              + f", maxDD {cand} {x['maxDD']:+.3f} C {b['maxDD']:+.3f} (gap {x['maxDD'] - b['maxDD']:+.3f})"
              + (f" -> {'PASS' if ok else 'fail'}" if judged else " (listed)"))


if __name__ == "__main__":
    main()
