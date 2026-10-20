"""C1 head to head on one basis: in sample 2022-2025 and 2026 from cash, the H56 pick, H48's ladder and the live
EMA100 spot control; plus the in-sample yearly returns of the pick and the live control."""
import json
import pandas as pd
import gate_lp_options as g
import gate_lp_pnl as p
R = g.RESULT_DIR
def row(name, kind, start, pool="99ac", opt="H56C1"):
    return json.load(open(f"{R}/rows/{opt}_{pool}_{name}_{kind}_{start}.json"))
for pool in ("99ac", "9db9"):
    print(pool)
    for v in ("ema50_l120", "ema50_ctl", "ema100_l140", "ema100_ctl", "ema200_l140", "ema200_ctl"):
        r = row(v, "continuous", "2022-01-01", pool)
        print(f"  IS {v}: net {r['net']:+.4f} dd {r['maxDD']:+.4f} moves {r['recentres']} switches {r['switches']} gas {r['gas']:.4f}")
    for v in ("ema50_l120", "ema50_ctl"):
        r = row(v, "oos", "2026-01-01", pool)
        print(f"  2026 {v}: net {r['net']:+.4f} dd {r['maxDD']:+.4f}")
    for v in ("ladder", "ctl"):
        r = row(v, "oos", "2026-01-01", pool, "C1")
        print(f"  2026 H48 C1 {v} (EMA100): net {r['net']:+.4f} dd {r['maxDD']:+.4f}")
for v in ("ema50_l120", "ema100_ctl", "ema100_l140", "ema50_ctl"):
    n = pd.read_parquet(f"{R}/nav/H56C1_99ac_{v}_continuous_2022-01-01.parquet")["usd"]
    print(v, {y: (round(a["ret"], 4), round(a["mdd"], 4)) for y, a in p.yearly(n, g.USD).items()})
