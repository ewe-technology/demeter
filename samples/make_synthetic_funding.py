"""
Funding of a synthetic <ALT>/ETH perp for EXP-021: short ALTUSDT + long ETHUSDT of equal USD notional.
The short receives ALT funding and the long pays ETH funding, so the rate the short side of ALT/ETH receives per 8h
settlement is rate(ALT) − rate(ETH). Settlements present in both files only.

usage: python make_synthetic_funding.py LINK   -> binance_funding_LINKETH_synth.csv
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def load(sym: str) -> pd.Series:
    f = pd.read_csv(os.path.join(HERE, f"binance_funding_{sym}USDT.csv"), parse_dates=["timestamp"])
    return f.set_index("timestamp")["rate"]


if __name__ == "__main__":
    alt = sys.argv[1]
    a, e = load(alt), load("ETH")
    s = (a - e).dropna().rename("rate").to_frame()
    s["mark_price"] = ""
    out = os.path.join(HERE, f"binance_funding_{alt}ETH_synth.csv")
    s.to_csv(out)
    print(f"{out}: {len(s)} settlements {s.index[0]}..{s.index[-1]}, annualised {s['rate'].mean() * 3 * 365:.1%}")
