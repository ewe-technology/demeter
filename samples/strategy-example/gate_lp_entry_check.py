"""H48 cells with the entry included: every window's return from its $100k instead of from its first bar."""
import glob, json, math
import pandas as pd
import gate_lp_options as g
R = g.RESULT_DIR
rows = []
for f in glob.glob(f"{R}/rows/*_window_*.json"):
    r = json.load(open(f))
    if r["option"] not in ("A1", "A2", "B1", "C1", "C2", "C3", "C4"):
        continue
    p = f"{R}/nav/{r['option']}_{r['pool']}_{r['version']}_window_{r['start']}.parquet"
    try:
        u = pd.read_parquet(p, columns=["usd"])["usd"]
    except FileNotFoundError:
        continue
    rows.append({**{k: r[k] for k in ("option", "pool", "version", "start")}, "net_first": r["net"],
                 "net_cash": float(u.iloc[-1] / g.USD - 1), "entry": float(u.iloc[0] / g.USD - 1)})
t = pd.DataFrame(rows)
t.to_csv(f"{R}/h48_entry_check.csv", index=False)
out = []
for (opt, pk), gp in t.groupby(["option", "pool"]):
    for col in ("net_first", "net_cash"):
        nets = gp.pivot(index="start", columns="version", values=col).sort_index()
        for v in nets.columns:
            if v.startswith("ctl") or v == "hold_wsteth":
                continue
            ctl = g.control_of(opt, v)
            if ctl not in nets:
                continue
            x = (nets[v] - nets[ctl]).dropna()
            h = math.ceil(len(x) / 2)
            out.append({"option": opt, "pool": pk, "version": v, "basis": col, "n": len(x), "median": x.median(),
                        "positive": int((x > 0).sum()), "first_half": x.iloc[:h].median(),
                        "second_half": x.iloc[h:].median(),
                        "first3": bool(x.median() > 0 and (x > 0).sum() >= math.ceil(0.75 * len(x))
                                       and x.iloc[:h].median() > 0 and x.iloc[h:].median() > 0),
                        "entry_lp_median": gp[gp.version == v]["entry"].median(),
                        "entry_ctl_median": gp[gp.version == ctl]["entry"].median()})
s = pd.DataFrame(out).sort_values(["option", "pool", "version", "basis"])
s.to_csv(f"{R}/h48_entry_summary.csv", index=False)
pd.set_option("display.width", 250)
print(s.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print(t[t.option.isin(["A1", "A2"])].pivot_table(index="start", columns="version", values="entry").round(4).to_string())
