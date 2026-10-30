"""
QUAN-1216 L6 robustness runs (experiments/VALIDATION-2026-10-29-v3_2-v2_2.md, L6): one L0 window per call, with the L0
switches on (flat 0.1% swap, fee in-range liquidity, v3.2 gas cap) and the variant from L6_EMA_SHIFT / L6_WIDTH in the
environment. ../real-data must hold the pool's minute files as for L0 (0x4585 from holdout-data; 0x7aea from base-data,
files renamed base-0x7aea...). Results go to result/<run folder> (tagged -l6ema+10 / -l6w1.1).

Usage, from samples/strategy-example:
    L6_WIDTH=1.1 python l6_runs.py v32|v22mainnet|v22base
"""
import os
import sys
from datetime import date, datetime

os.environ.setdefault("FLAT_SWAP_COST", "1")
os.environ.setdefault("FEE_IN_RANGE_LIQUIDITY", "1")
os.environ.setdefault("CLAIM_GAS_CAP", "1")

if __name__ == "__main__":   # the scripts start worker processes (spawn re-imports this file)
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "v32":
        import gamma_maker_defense_ethusdc_v3_2 as m
        m.process_for_date(datetime(2021, 5, 6), date(2021, 5, 6), date(2026, 8, 31), "", [])
    elif which == "v22mainnet":
        import gamma_ig_gap_bands_defense_btceth_v2_2 as m
        m.process_for_date(datetime(2021, 11, 2), date(2021, 11, 2), date(2026, 8, 31), "mainnet")
    elif which == "v22base":
        import gamma_ig_gap_bands_defense_btceth_v2_2 as m
        m.process_for_date(datetime(2024, 9, 14), date(2024, 9, 14), date(2026, 8, 31), "base")
    else:
        sys.exit(__doc__)
