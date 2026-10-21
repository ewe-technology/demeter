"""
The standard metric set (gate_lp_metrics) for the C1 drawdown report (reports/c1_drawdown_2026-10-21_report.md):
the live gate, C1's ladder and the H59 / H62 / H63 / H66 versions on 99ac, 2022-01-01 .. 2026-09-30, descriptive
only. LP metrics only for books whose ladder is the whole book while off (the attribution rebuild sizes the ladder
to the NAV, so a sized ladder with stablecoin beside it would be overstated). Benchmarks are metrics.json's C1 set
(same pool, same period).

Run from samples/strategy-example on the strategy host, with lp_attribution.py next to it:
  PYTHONPATH=../.. python c1_report_metrics.py      # writes result/gate-lp-options/c1_report_metrics.json
"""
import json

import gate_lp_metrics as m

LADDER = m.on_off(["spot", 1.0], ["range", 1.40, 1.01])
# key: (label, option, names, LP modes or None, control key)
SERIES = {
    "ctl": ("現行（EMA100 濾網現貨）", "H51C1", ["ctl_n1_h00_100k"], None, None),
    "ladder": ("C1 原版", "H51C1", ["ladder_n1_h00_100k"], LADDER, "ctl"),
    "dd20": ("H59 dd20", "H59", ["dd20"], None, "ctl"),
    "dd30": ("H59 dd30", "H59", ["dd30"], None, "ctl"),
    "hdown": ("H62 下緣每小時檢查", "H62", ["hdown"], LADDER, "ctl"),
    "ctl_rt": ("現行 + 換幣路徑（H63）", "H63", ["ctl_rt"], None, None),
    "ladder_rt": ("C1 原版 + 換幣路徑（H63）", "H63", ["ladder_rt"], LADDER, "ctl_rt"),
    "lp5": ("H66 lp5", "H66", ["lp5"], None, "ctl"),
}


def main():
    px = m.usd_prices()
    out = {"series": {}, "bench": {}, "notes": __doc__}
    navs = {}
    for key, (label, opt, names, modes, ctl) in SERIES.items():
        usd, parts = m.read_book(opt, "99ac", names, m.D22, m.END)
        navs[key] = m.nav0(usd)
        evs = [m.events(opt, "99ac", v, m.D22, m.END) for v in names]
        extra = {"control": ctl, **m.counts(evs), **m.row_costs(opt, "99ac", names, m.D22)}
        extra["moves"] += sum(int((e["kind"] == "recentre_h").sum()) for e in evs)  # H62's hourly ones (counts() skips them)
        if modes:
            extra.update(m.lp_metrics([m.lp_parts(p, e, modes, "99ac") for p, e in zip(parts, evs)]))
        out["series"][key] = m.full(label, navs[key], navs.get(ctl), px, "btc", extra)
        print(key, {k: round(v, 4) for k, v in out["series"][key].items() if isinstance(v, float)}, flush=True)
    with open(f"{m.R}/metrics.json", encoding="utf-8") as f:
        out["bench"] = json.load(f)["bench"]["C1"]
    with open(f"{m.R}/c1_report_metrics.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
