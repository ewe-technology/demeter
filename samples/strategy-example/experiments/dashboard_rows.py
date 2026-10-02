"""
Build the dashboard documents for one experiment, as JSON files for the ArtifactData tool.

- experiments/<EXP-id>: from a registry.csv row plus the EXP file's hypothesis / verdict (passed in).
- curves/<asset> merge: the variant's weekly net value, aligned to the dashboard's weekly grid.

usage (from samples/strategy-example):
    python experiments/dashboard_rows.py row   <EXP-id> <version> <order> "<hypothesis>" "<verdict>" <out.json>
    python experiments/dashboard_rows.py curve <equity_csv> <series key> "<label>" <slot 2|5|6|7|8> <out.json>

Then: ArtifactData set experiments/<EXP-id> file_path=<out.json>, and ArtifactData update curves/eth (or btc)
file_path=<out.json> with if_version from a get. `update` merges nested objects, so the new series key is added
next to the existing ones. The equity CSV must come from the same continuous window as the curve document
(ETH 2022-01-01..2026-09-17, WBTC 2022-11-01..2026-09-17), or the weekly points will not line up.
"""
import csv
import json
import sys

import pandas as pd

REGISTRY = "experiments/registry.csv"
NUMERIC = {"dev_median_gain_pts", "holdout_median_gain_pts", "eth_cont_total", "eth_cont_cagr", "eth_cont_maxdd"}


def row(exp_id: str, version: str, order: str, hypothesis: str, verdict: str, out: str) -> None:
    with open(REGISTRY) as f:
        r = next(x for x in csv.DictReader(f) if x["id"] == exp_id)
    num = lambda k: float(r[k]) if r[k] not in ("", None) else None
    stage = lambda wins, median: {"wins": r[wins], "median": num(median)} if r[wins] else None
    doc = {"id": exp_id, "version": version, "order": int(order), "name": r["name"], "status": r["status"],
           "date": r["date"], "hypothesis": hypothesis, "verdict": verdict,
           "dev": stage("dev_wins", "dev_median_gain_pts"), "holdout": stage("holdout_wins", "holdout_median_gain_pts"),
           "eth_total": num("eth_cont_total"), "eth_cagr": num("eth_cont_cagr"), "eth_maxdd": num("eth_cont_maxdd"),
           "commit": r["result_commit"] or r["prereg_commit"], "doc": f"experiments/{r['doc']}" if r["doc"] else "",
           "level": r.get("level") or None}   # improvement / standalone / validation / both (both levels failed at dev)
    json.dump(doc, open(out, "w"))
    print(json.dumps(doc, ensure_ascii=False)[:300])


def curve(equity_csv: str, key: str, label: str, slot: str, out: str) -> None:
    if int(slot) not in (2, 5, 6, 7, 8):
        raise SystemExit("slot must be one of 2, 5, 6, 7, 8 (1, 3, 4 are v6, plain LP, hold)")
    eq = pd.read_csv(equity_csv, index_col=0, parse_dates=True)["net_value"]
    w = eq.resample("W-SUN").last().dropna()
    w.iloc[0] = eq.iloc[0]   # same first point as the existing series: the start value
    doc = {"series": {key: [round(float(v)) for v in w]}, "labels": {key: label}, "slots": {key: int(slot)}}
    json.dump(doc, open(out, "w"))
    print(f"{key}: {len(w)} weekly points, {w.index[0].date()}..{w.index[-1].date()}, last {round(float(w.iloc[-1]))}")


if __name__ == "__main__":
    {"row": row, "curve": curve}[sys.argv[1]](*sys.argv[2:])
