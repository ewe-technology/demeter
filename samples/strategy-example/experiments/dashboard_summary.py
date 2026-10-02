"""
Build the dashboard documents `summary/standalone` (strategy comparison table + per-window detail) and `summary/findings`
from the EXP files' Result tables (run from samples/strategy-example/experiments; usage: python dashboard_summary.py <out dir>).
Then: ArtifactData set summary/standalone and summary/findings with file_path. The FILES dict lists the strategies; edit it
when a new standalone strategy is added. v6 numbers are taken from EXP-048's table; two supplementary 2022 values are hard-coded.
"""
import json, os, re, sys
D = sys.argv[1] if len(sys.argv) > 1 else "."   # output dir for s_standalone.json / s_findings.json
FILES = {  # exp -> (file, version, name, reading)
 "EXP-048": ("EXP-048-share50-exit-confirm.md", "v6.35", "ETH share 50% + exit confirmation", "credible"),
 "EXP-046": ("EXP-046-share-50.md", "v6.33", "ETH share fixed at 50%", "credible"),
 "EXP-044": ("EXP-044-exit-confirm.md", "v6.31", "Range exit needs 2 daily checks", "credible"),
 "EXP-051": ("EXP-051-share50-confirm-vol-width.md", "v6.38", "Share 50% + confirm + vol width", "weak"),
 "EXP-049": ("EXP-049-share50-vol-width.md", "v6.36", "Share 50% + vol-scaled width", "weak"),
 "EXP-034": ("EXP-034-vol-width-standalone.md", "v6.25r", "Vol-scaled ladder width", "weak"),
 "EXP-032": ("EXP-032-donchian-regime-standalone.md", "v6.19r", "Donchian-midpoint regime", "fragile"),
}
num = lambda s: float(s.replace("%", "").replace("$", "").replace("k", "").replace("+", "").replace("−", "-"))
def row(cells):  # | label | total | cagr | dd | sharpe | calmar | fees | impact | rebuilds |
    return {"total": num(cells[1]) / 100, "cagr": num(cells[2]) / 100, "dd": num(cells[3]) / 100, "sharpe": num(cells[4]), "calmar": num(cells[5]),
            "fees": num(cells[6]) * 1000, "rebuilds": int(cells[8])}
def parse(path):
    s = open(path).read(); out = {}
    for line in s.splitlines():
        if not line.startswith("| ") or line.count("|") < 10: continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        m = re.match(r"(.+) (v6|this)$", c[0])
        if not m or not c[1].startswith(("+", "-", "−")): continue
        out.setdefault(m.group(1).strip(), {})[m.group(2)] = row(c)
    return s, out
rows, base = [], None
for exp, (fn, ver, name, reading) in FILES.items():
    s, t = parse(fn)
    def dev(key):  # from the dev table (ETH/WBTC) or from the verdict text
        if key in t: return {"calmar": t[key]["this"]["calmar"], "dd": t[key]["this"]["dd"]}
        m = re.search(key + r" Calmar ([\d.-]+), max DD ([\d.-]+)%", s)
        return {"calmar": float(m.group(1)), "dd": float(m.group(2)) / 100}
    wins = []
    for label in ("Arbitrum WETH", "Base WETH", "Base cbBTC"):
        wins.append({"label": label, **t[label]})
    h4 = next((k for k in t if "H4" in k), None); h5 = next((k for k in t if "H5" in k), None)
    if h4: wins.append({"label": "WBTC 2022 out-of-time (H4)", **t[h4]})
    elif exp == "EXP-032":
        wins.append({"label": "WBTC 2022 out-of-time (H4, supplementary)", "v6": {"total": 0.024, "cagr": 0.029, "dd": -0.125, "sharpe": 0.24, "calmar": 0.23, "fees": 14300, "rebuilds": 17}, "this": {"total": -0.033, "cagr": None, "dd": -0.126, "sharpe": None, "calmar": -0.32, "fees": None, "rebuilds": None}})
    elif exp == "EXP-034":
        wins.append({"label": "WBTC 2022 out-of-time (H4, supplementary)", "v6": {"total": 0.024, "cagr": 0.029, "dd": -0.125, "sharpe": 0.24, "calmar": 0.23, "fees": 14300, "rebuilds": 17}, "this": {"total": 0.016, "cagr": None, "dd": -0.132, "sharpe": None, "calmar": 0.14, "fees": None, "rebuilds": None}})
    if h5: wins.append({"label": "ETH 2021 bull (H5, reported)", **t[h5]})
    rows.append({"exp": exp, "version": ver, "name": name, "reading": reading, "level": "standalone", "devEth": dev("ETH"), "devBtc": dev("WBTC"), "windows": wins})
    if exp == "EXP-048":
        base = {"exp": "EXP-000", "version": "v6", "name": "Baseline (EMA 90-120 engine, ETH share 70/50)", "reading": "baseline", "level": "baseline",
                "devEth": {"calmar": t["ETH"]["v6"]["calmar"], "dd": t["ETH"]["v6"]["dd"]}, "devBtc": {"calmar": t["WBTC"]["v6"]["calmar"], "dd": t["WBTC"]["v6"]["dd"]},
                "windows": [{"label": w["label"], "v6": w["v6"], "this": w["v6"]} for w in wins]}
rows.insert(0, base)
order = ["baseline", "credible", "weak", "fragile"]
rows.sort(key=lambda r: order.index(r["reading"]))
notes = {"credible": "Holdout Calmar within about 0.05 of v6, max DD shallower, positive out-of-time; return below v6.",
         "weak": "Clears the absolute bar; Calmar below v6 on most pools, Base WETH 0.33-0.42.",
         "fragile": "Passed its pre-registered holdout; loses on the 2022 out-of-time window (-3.3%)."}
for r in rows: r["note"] = notes.get(r["reading"], "Reference.")
json.dump({"title": "Standalone strategies", "updated": "2026-10-02", "rows": rows}, open(os.path.join(D, "s_standalone.json"), "w"))
findings = [
 "No variant beats v6's return out-of-time. 0 of 28 experiments (EXP-024..051) passed the improvement level; 7 passed the standalone level.",
 "Standalone = absolute bar (dev Calmar >= 0.60, max DD > -30%; holdout Calmar >= 0.50 on 2 of 3 pools, return > 0, max DD > -35%, plus a positive 2022 bear-market out-of-time window). It says a strategy is good alone, not better than v6.",
 "Strongest: v6.35 (ETH share 50% + 2-day exit confirmation) and v6.33 (share 50%): v6-level holdout Calmar with 3-8 pts shallower max DD, lower return. v6.31 is neutral. v6.36, v6.38, v6.25r pass weakly. v6.19r (Donchian) is fragile.",
 "Faster regime lines (Hull, ROC, Supertrend) lose. Slow lines (SMA 200, Ichimoku, Aroon, ROC) beat v6 on WBTC at dev but lose the 2022 BTC bear window (-5.8% to -14.3% vs v6 +2.4%): a bull-market fit.",
 "The seven are one family (same EMA signal, same pools), not independent evidence. Thresholds were set after seeing dev results. The clean test is the forward window 2026-09-18..12-31 (not yet available).",
]
json.dump({"title": "What the series found", "updated": "2026-10-02", "items": findings, "doc": "samples/strategy-example/experiments/FINDINGS-2026-10-02.md"}, open(os.path.join(D, "s_findings.json"), "w"))
print(len(rows), [ (r["exp"], len(r["windows"])) for r in rows])
