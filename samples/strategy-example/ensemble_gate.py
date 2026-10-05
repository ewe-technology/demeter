"""
Does splitting the BTC gate across close hours and EMA spans take the luck out of the timing? Report section 12.1
found the same rule worth +165% to +310% over 2022-2025 depending only on the hour the daily close is taken.

Each tranche runs the base rule (BTC above its EMA -> 50% ETH + 50% BTC, otherwise USDC) with its own close hour
and span; the portfolio holds the average of the tranches, so it steps in and out in 1/n slices. Designs, fixed
before the run, all reported:

  base    one tranche: 00h, EMA100 (spot_robustness)
  hours   00 / 06 / 12 / 18h x EMA100
  spans   00h x EMA 90 / 110 / 130 / 150
  both    the 4 x 4 grid

Stability: every hour set is shifted together by an offset (base and spans 0-23 h, hours and both 0-5 h, after which
they repeat), and the spread of results across offsets is the measure of timing luck.

Run from samples/strategy-example after spot_btc_eth_gate.py has built the price cache:
  PYTHONPATH=../.. python ensemble_gate.py
"""
import os

import pandas as pd

import spot_robustness as sr
from spot_btc_eth_gate import load_prices

RESULT_DIR = "result/ensemble"
DESIGNS = {
    "base": ((0,), (100,), 24),
    "hours": ((0, 6, 12, 18), (100,), 6),
    "spans": ((0,), (90, 110, 130, 150), 24),
    "both": ((0, 6, 12, 18), (90, 110, 130, 150), 6),
}
COLS = ["2022", "2023", "2024", "2025", "total", "maxDD", "calmar", "drop window", "2026", "2026 maxDD", "trades"]


def ensemble_weights(prices: pd.DataFrame, hours, spans) -> pd.DataFrame:
    """Average of the tranches' (eth, btc) shares, carried forward to every hour."""
    parts = [sr.gate(prices, hour=h, span=s).reindex(prices.index).ffill().fillna(0.0) for h in hours for s in spans]
    return sum(parts) / len(parts)


if __name__ == "__main__":
    os.makedirs(RESULT_DIR, exist_ok=True)
    prices, _, _ = load_prices()
    rows = []
    for design, (hours, spans, offsets) in DESIGNS.items():
        for k in range(offsets):
            shifted = tuple((h + k) % 24 for h in hours)
            nav, trades = sr.simulate(ensemble_weights(prices, shifted, spans), prices)
            s = sr.summary(design, nav, trades)
            rows.append({"design": design, "offset": k, "tranches": len(hours) * len(spans), **{c: s[c] for c in COLS}})
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/ensemble.csv", index=False)

    pd.set_option("display.width", 250)
    at_zero = table[table["offset"] == 0].set_index("design")
    print("\n== offset 0 (the hour sets as written) ==")
    print(sr.show(at_zero, COLS))
    print("\n== spread across offsets: min / median / max ==")
    spread = []
    for design, g in table.groupby("design", sort=False):
        row = {"design": design, "offsets": len(g), "tranches": int(g["tranches"].iloc[0])}
        for c in ("total", "maxDD", "calmar", "2026", "trades"):
            q = g[c].quantile([0, 0.5, 1]).to_numpy()
            if c in ("total", "maxDD", "2026"):
                row[c] = " / ".join(f"{v:+.0%}" for v in q)
            elif c == "calmar":
                row[c] = " / ".join(f"{v:.2f}" for v in q)
            else:
                row[c] = " / ".join(f"{v:.0f}" for v in q)
        row["total range pt"] = f"{100 * (g['total'].max() - g['total'].min()):.0f}"
        spread.append(row)
    print(pd.DataFrame(spread).to_string(index=False))
    print("ENSEMBLE_DONE")
