"""Chart data for the 2026-10-07 weekly deck and video (EXP-052..164).

Writes curve_eth_mainnet.json: weekly net value ($k on $100k) of spec v1 (A) and v6.75 (GA, EXP-157)
on mainnet USDC/ETH 0.05% (0x88e6), full history, plus buy-and-hold ETH from Binance daily closes.
"""
import json
from pathlib import Path

import pandas as pd

MAIN = Path("/Users/dinohuang/Desktop/demeter-momentum/samples")
RUN = MAIN / "strategy-example/result/v6_validate/0x88e6-opt-AGAGBGCGDGEGFGGGH-specv1-2021-05-06-2026-09-17"
OUT = Path(__file__).with_name("curve_eth_mainnet.json")


def weekly(path):
    s = pd.read_csv(path, index_col=0, parse_dates=True)["net_value"]
    return s.resample("W-SUN").last()


spec = weekly(RUN / "equity_A_v6.csv")
nolow = weekly(RUN / "equity_GA_nolow.csv")
eth = pd.read_csv(MAIN / "binance_daily_closes.csv", index_col=0, parse_dates=True)["ETHUSDT"]
eth = eth[eth.index >= "2021-05-06"]
hold = (100_000 * eth / eth.iloc[0]).resample("W-SUN").last().reindex(spec.index).ffill()

OUT.write_text(json.dumps({
    "dates": [d.strftime("%Y-%m-%d") for d in spec.index],
    "spec_v1": [round(v / 1000, 2) for v in spec],
    "v6_75": [round(v / 1000, 2) for v in nolow],
    "hold_eth": [round(v / 1000, 2) for v in hold],
}))
