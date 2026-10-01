"""
Apply the pre-registered success rules (README *Success levels*) to v6_validate.py runs.

usage (from samples/strategy-example):
    python experiments/judge.py dev  <tag> <prefix> [<prefix> ...]    # tag = opt list without commas, e.g. AABADAEAF
    python experiments/judge.py hold <tag> <prefix> [<prefix> ...]

dev  reads result/v6_validate/0x88e6-opt-<tag>-<segment> (ETH yearly + continuous) and 0x99ac-opt-<tag>-2022-11-01-2026-09-17.
hold reads the three holdout folders (Arbitrum WETH 2024-01-01..2025-07-23, Base WETH 2024-01-01..2026-09-17,
      Base cbBTC 2025-01-01..2026-09-17).
<prefix> is the variant name prefix, e.g. AB_ ; the baseline is A_ in the same folder.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import exp_metrics as e  # noqa: E402

R = "result/v6_validate"
SEGS = ["2022-01-01-2022-12-31", "2023-01-01-2023-12-31", "2024-01-01-2024-12-31", "2025-01-01-2025-12-31", "2026-01-01-2026-09-17"]
HOLD = [("Arbitrum WETH", "0xc696", "2024-01-01-2025-07-23"), ("Base WETH", "0xd0b5", "2024-01-01-2026-09-17"),
        ("Base cbBTC", "0xfbb6", "2025-01-01-2026-09-17")]


def cont(folder: str, pre: str) -> dict:
    eqs = e.load(folder)
    return e.metrics(eqs[next(k for k in eqs if k.startswith(pre))])


def improves(a: dict, v: dict) -> bool:
    """CAGR above v6's, Calmar >= v6's (if v6's CAGR is negative: only CAGR above), max DD no more than 3 pts deeper."""
    dd_ok = v["maxdd"] >= a["maxdd"] - 0.03
    if a["cagr"] < 0:
        return v["cagr"] > a["cagr"] and dd_ok
    return v["cagr"] > a["cagr"] and v["calmar"] >= a["calmar"] and dd_ok


def dev(tag: str, prefixes: list) -> dict:
    out = {}
    eth, btc = f"{R}/0x88e6-opt-{tag}-2022-01-01-2026-09-17", f"{R}/0x99ac-opt-{tag}-2022-11-01-2026-09-17"
    a_e, a_b = cont(eth, "A_"), cont(btc, "A_")
    yearly = [pd.read_csv(f"{R}/0x88e6-opt-{tag}-{s}.csv").set_index("variant")["net_return"] for s in SEGS]
    for pre in prefixes:
        v_e, v_b = cont(eth, pre), cont(btc, pre)
        name = lambda y: y[next(k for k in y.index if k.startswith(pre))]
        base = lambda y: y[next(k for k in y.index if k.startswith("A_"))]
        wins = sum(float(name(y)) > float(base(y)) for y in yearly)
        pos = sum(float(name(y)) > 0 for y in yearly)
        imp = improves(a_e, v_e) and improves(a_b, v_b) and wins >= 3
        std = all(m["calmar"] >= 0.6 and m["maxdd"] >= -0.30 for m in (v_e, v_b)) and pos >= 4
        out[pre] = {"improvement": imp, "standalone": std, "wins": wins, "pos": pos, "eth": v_e, "wbtc": v_b, "a_eth": a_e, "a_wbtc": a_b}
        print(f"{pre:6s} improvement={'PASS' if imp else 'fail'} standalone={'PASS' if std else 'fail'} | ETH cagr {v_e['cagr']*100:.1f} vs {a_e['cagr']*100:.1f}, "
              f"calmar {v_e['calmar']:.2f} vs {a_e['calmar']:.2f}, dd {v_e['maxdd']*100:.1f} vs {a_e['maxdd']*100:.1f} | WBTC cagr {v_b['cagr']*100:.1f} vs {a_b['cagr']*100:.1f}, "
              f"calmar {v_b['calmar']:.2f} vs {a_b['calmar']:.2f}, dd {v_b['maxdd']*100:.1f} vs {a_b['maxdd']*100:.1f} | wins {wins}/5, positive years {pos}/5")
    return out


def hold(tag: str, prefixes: list) -> dict:
    out = {}
    for pre in prefixes:
        per = []
        for label, pool, seg in HOLD:
            f = f"{R}/{pool}-opt-{tag}-{seg}"
            per.append((label, cont(f, "A_"), cont(f, pre)))
        imp_pools = [l for l, a, v in per if improves(a, v)]
        rest = [(l, a, v) for l, a, v in per if l not in imp_pools]
        imp = len(imp_pools) >= 2 and all(v["calmar"] >= a["calmar"] - 0.2 for l, a, v in rest)
        std_pools = [l for l, a, v in per if v["calmar"] >= 0.5]
        std = all(v["total"] > 0 for _, a, v in per) and len(std_pools) >= 2 and all(v["maxdd"] >= -0.35 for _, a, v in per)
        out[pre] = {"improvement": imp, "standalone": std, "per": per}
        print(f"{pre:6s} improvement={'PASS' if imp else 'fail'} ({len(imp_pools)}/3 pools) standalone={'PASS' if std else 'fail'} ({len(std_pools)}/3 pools Calmar>=0.5) | "
              + "; ".join(f"{l}: calmar {v['calmar']:.3f} (v6 {a['calmar']:.3f}) dd {v['maxdd']*100:.1f}" for l, a, v in per))
    return out


if __name__ == "__main__":
    {"dev": dev, "hold": hold}[sys.argv[1]](sys.argv[2], sys.argv[3:])
