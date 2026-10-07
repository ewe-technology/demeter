"""
Full-history judge on the spec v1 baseline (EXP-156 part 2 / EXP-157 on): per pool a variant wins when its CAGR is above
`A`'s, its Calmar is at least `A`'s and its max DD is no more than 3 pts deeper. Pass: wins on >= 4 of the 7 pools with at
least one ETH and one BTC pool among them; a pool without a result counts as a loss.
usage (from samples/strategy-example): python experiments/judge_full.py <grid tag, e.g. opt-AGAGB> [result dir]
"""
import glob
import os
import sys
from datetime import date

import pandas as pd

POOLS = [("0x88e6", "ETH mainnet 0.05%"), ("0x8ad5", "ETH mainnet 0.3%"), ("0xd0b5", "ETH Base 0.05%"),
         ("0xc696", "ETH Arbitrum 0.05%"), ("0x6c56", "ETH Base 0.3%"), ("0x99ac", "BTC mainnet WBTC 0.3%"),
         ("0xfbb6", "BTC Base cbBTC 0.05%")]
START = {"0x88e6": "2021-05-06", "0x8ad5": "2021-05-06", "0xd0b5": "2023-12-01", "0xc696": "2023-06-09",
         "0x6c56": "2025-01-01", "0x99ac": "2021-11-02", "0xfbb6": "2024-10-01"}   # full-history windows (EXP-154 / 156)
NEED, DD_SLACK = 4, 0.03


def metrics(r) -> dict:
    years = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days / 365.25
    cagr = (1 + r["net_return"]) ** (1 / years) - 1 if r["net_return"] > -1 else float("nan")
    dd = float(r["max_draw_down"])
    return {"total": r["net_return"], "cagr": cagr, "dd": dd, "calmar": cagr / dd if dd > 0 else float("nan"),
            "rebuilds": r.get("rebuilds"), "gas": r.get("gas_if_mainnet")}


def load(tag: str, folder: str) -> dict:
    out = {}
    for pool, _ in POOLS:
        files = glob.glob(os.path.join(folder, f"{pool}-{tag}-specv1-{START[pool]}-*.csv"))
        if not files:
            continue
        df = pd.concat(pd.read_csv(f) for f in files)
        if "error" in df:
            df = df[df["error"].isna()]
        out[pool] = {row["variant"]: metrics(row) for _, row in df.drop_duplicates("variant", keep="last").iterrows()}
    return out


def judge(tag: str, folder: str = "result/v6_validate") -> dict:
    res = load(tag, folder)
    variants = sorted({v for p in res.values() for v in p if v != "A_v6"})
    verdicts = {}
    for v in variants:
        wins, lines = [], []
        for pool, label in POOLS:
            a, x = res.get(pool, {}).get("A_v6"), res.get(pool, {}).get(v)
            if a is None or x is None:
                lines.append(f"  {label:22s} missing -> loss")
                continue
            win = x["cagr"] > a["cagr"] and x["calmar"] >= a["calmar"] and x["dd"] <= a["dd"] + DD_SLACK
            if win:
                wins.append(label)
            lines.append(f"  {label:22s} A {a['cagr']:6.2%} / {-a['dd']:6.1%} / {a['calmar']:.3f}   "
                         f"{v[:2]} {x['cagr']:6.2%} / {-x['dd']:6.1%} / {x['calmar']:.3f}   {'WIN' if win else 'lose'}")
        eth = any(w.startswith("ETH") for w in wins)
        btc = any(w.startswith("BTC") for w in wins)
        ok = len(wins) >= NEED and eth and btc
        verdicts[v] = {"wins": len(wins), "eth": eth, "btc": btc, "pass": ok}
        print(f"{v}: {len(wins)}/7 wins (ETH {'y' if eth else 'n'}, BTC {'y' if btc else 'n'}) -> {'PASS' if ok else 'fail'}")
        print("\n".join(lines))
    return verdicts


if __name__ == "__main__":
    judge(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "result/v6_validate")
