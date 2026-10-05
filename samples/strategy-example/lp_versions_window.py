"""
The old LP version (ETH/USDC + WBTC/WETH, tri_btc_eth_gate.py) over the window of yield_layer's D version,
2024-01-01 ~ 2025-11-09, so the two can be compared on the same days (reports/spot_yield_and_basket.md section 9).
Net of the estimated mainnet gas of tri_btc_eth_gate, $100k start.

Run from samples/strategy-example:
  PYTHONPATH=../.. python lp_versions_window.py
"""
import multiprocessing
from datetime import date, datetime

import pandas as pd

import tri_btc_eth_gate as t

LO, HI = "2024-01-01", "2025-11-10"
DATA_END = date(2025, 11, 30)  # the USDC/USDT parking pool ends here on the backtest host
CONFIGS = [
    t.Config("fixed 50/50", "btc"),
    t.Config("fixed 50/50 + park", "btc", park=True),
    t.Config("follow", "btc", tilt="follow"),
    t.Config("follow + park + band 1%", "btc", tilt="follow", park=True, band=0.01),
]


def stats(nav: pd.Series) -> dict:
    return {"total": nav.iloc[-1] / nav.iloc[0] - 1, "maxDD": (nav / nav.cummax() - 1).min()}


if __name__ == "__main__":
    data, prices, eth_close, ratio_close = t.load_all(t.DATA_START, DATA_END, "1h")
    signal = t.build_signal(eth_close, ratio_close)
    sliced = {k: v.loc[LO:] for k, v in data.items()}
    args = [(c, sliced, prices.loc[LO:], signal, datetime(2024, 1, 1)) for c in CONFIGS]
    with multiprocessing.Pool(t.WORKERS) as pool:
        results = pool.starmap(t.run_one, args)
    rows = []
    for name, nav, rebuilds, swap_fee, gas, _ in results:
        rows.append({"run": name, **stats(nav[nav.index < HI]), "rebuilds": rebuilds, "swap $": round(swap_fee),
                     "gas $": round(gas)})
    p = prices.loc[LO:]
    p = p[p.index < HI]
    e, b = p[t.weth.name], p[t.wbtc.name]
    rows.append({"run": "hold 50/50", **stats(0.5 * e / e.iloc[0] + 0.5 * b / b.iloc[0])})
    table = pd.DataFrame(rows).set_index("run")
    for c in ("total", "maxDD"):
        table[c] = table[c].map(lambda v: f"{v:+.1%}")
    print(table.to_string())
