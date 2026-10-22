"""
Yearly ledger of the C1 drawdown round (H58 - H68, reports/c1_drawdown_2026-10-21_report.md) for the PnL page: each
continuous book on 99ac (and the main ones on 9db9) cut into calendar years (a year's return is its last NAV over the
NAV just before it), the year's max drawdown, 移倉 (re-centres, the hourly ones included) and 換邊 (gate switches: the
same gate for every version, so the live gate's own count), and for books whose gate-off ladder is a fixed share of
the book the attribution of lp_attribution.decompose (gate-on price, gate-off price, fees, costs). A fixed share s
scales the rebuilt ladder to s x NAV (the rest is stablecoin, no price effect); the gate-on spot weight is the spot
mode's own weight. Books sized by drawdown, inventory or a stop (dd20, dd30, inv*, lp5) get returns only.

Run from samples/strategy-example on the strategy host, with lp_attribution.py next to it:
  PYTHONPATH=../.. python c1_drawdown_pnl.py        # writes result/gate-lp-options/c1_drawdown_ledger.json
"""
import json

import numpy as np
import pandas as pd

import gate_lp_options as g
from gate_lp_pnl import YEARS, yearly
from lp_attribution import decompose, vnorm

R = g.RESULT_DIR
START = "2022-01-01"
LADDER = (1.40, 1.01)

# key: (option, pool, version, modes or None); modes {"on": spot weight, "off": ladder share or None (cash)}
SERIES = {
    "ctl": ("H51C1", "99ac", "ctl_n1_h00_100k", {"on": 1.0, "off": None}),
    "ladder": ("H51C1", "99ac", "ladder_n1_h00_100k", {"on": 1.0, "off": 1.0}),
    "dd20": ("H59", "99ac", "dd20", None),
    "dd30": ("H59", "99ac", "dd30", None),
    "hdown": ("H62", "99ac", "hdown", {"on": 1.0, "off": 1.0}),
    "lp5": ("H66", "99ac", "lp5", None),
    "inv30": ("H67", "99ac", "inv30", None),
    "inv50": ("H67", "99ac", "inv50", None),
    "fix65": ("H67F", "99ac", "fix65", {"on": 1.0, "off": 0.65}),
    "w80_s60": ("H68", "99ac", "w80_s60", {"on": 0.8, "off": 0.6}),
    "w90_s40": ("H68", "99ac", "w90_s40", {"on": 0.9, "off": 0.4}),
    "ctl_rt": ("H63", "99ac", "ctl_rt", {"on": 1.0, "off": None}),
    "ladder_rt": ("H63", "99ac", "ladder_rt", {"on": 1.0, "off": 1.0}),
    "ctl_9db9": ("H51C1", "9db9", "ctl_n1_h00_100k", None),
    "ladder_9db9": ("H51C1", "9db9", "ladder_n1_h00_100k", None),
    "dd30_9db9": ("H59", "9db9", "dd30", None),
    "w80_s60_9db9": ("H68", "9db9", "w80_s60", None),
    "w90_s40_9db9": ("H68", "9db9", "w90_s40", None),
}


def tag(opt, pk, v):
    return f"{opt}_{pk}_{v}_continuous_{START}"


def segments_share(index, nav, price, events, modes):
    """lp_attribution.segments with shares: a range placed at an event holds share x NAV, a spot holds weight x NAV.
    Markers that are not placements (cut:, s:, trim:, zero, budget_*) are skipped."""
    pos = np.asarray(index.searchsorted(pd.to_datetime(events["t"]).values))
    state, out = None, []
    for kind, i in zip(events["kind"].astype(str), pos):
        if kind in ("on", "off"):
            state = kind
        elif state is None or not kind.startswith("recentre"):
            continue
        p0 = price[i]
        if state == "on":
            mode, scale = ("spot", modes["on"]), nav[i]
        elif modes["off"] is None:
            mode, scale = ("cash",), 0.0
        else:
            mode = ("range", *LADDER)
            scale = nav[i] * modes["off"] / vnorm(p0, p0, *LADDER)
        out.append((i, mode, p0, scale, state))
    return out


def counts_of(ev: pd.DataFrame, ctl_ev: pd.DataFrame) -> dict:
    out = {}
    t, tc = pd.to_datetime(ev["t"]), pd.to_datetime(ctl_ev["t"])
    later = ctl_ev.index > ctl_ev.index[0]  # the first row is the placement at the start, not a switch
    for y in YEARS:
        out[y] = {"移倉": int(((t.dt.year == int(y)) & ev["kind"].isin(["recentre", "recentre_h"])).sum()),
                  "換邊": int(((tc.dt.year == int(y)) & ctl_ev["kind"].isin(["on", "off"]) & later).sum())}
        trims = int(((t.dt.year == int(y)) & ev["kind"].astype(str).str.startswith("trim:")).sum())
        if trims:
            out[y]["減倉"] = trims
    return out


def attribution(df: pd.DataFrame, ev: pd.DataFrame, modes: dict) -> tuple[dict, dict]:
    nav, price = df["usd"].to_numpy(), df["price"].astype(float).ffill().to_numpy()
    pe, fe, co, on, _ = decompose(nav, price, segments_share(df.index, nav, price, ev, modes))
    co[0] += nav[0] - g.USD  # the buy-in from cash at the first bar
    out = {}
    for y in YEARS:
        idx = np.nonzero(df.index.year == int(y))[0]
        base = nav[idx[0] - 1] if idx[0] > 0 else g.USD
        ret = nav[idx[-1]] / base - 1
        a = {"on": float(pe[idx][on[idx]].sum() / base), "off": float(pe[idx][~on[idx]].sum() / base),
             "fees": float(fe[idx].sum() / base), "costs": float(co[idx].sum() / base)}
        a["other"] = float(ret - sum(a.values()))
        out[y] = a
    check = {}
    if modes["off"] is not None:  # lp_attribution.fee_check on the share-scaled rebuild
        inside = fe != 0
        d = pd.DataFrame({"r": fe[inside], "m": pe[inside]}, index=df.index[inside]).groupby(pd.Grouper(freq="h")).sum()
        d = d[(d["r"] != 0) | (d["m"] != 0)]
        b, a0 = np.polyfit(d["m"], d["r"], 1)
        check = {"slope_part": float(b * d["m"].sum() / nav[0]), "intercept_part": float(a0 * len(d) / nav[0])}
    return out, check


def main():
    out = {"series": {}, "fee_check": {}}
    ctl_ev = {pk: pd.read_csv(f"{R}/nav/events_{tag('H51C1', pk, 'ctl_n1_h00_100k')}.csv") for pk in ("99ac", "9db9")}
    for key, (opt, pk, v, modes) in SERIES.items():
        df = pd.read_parquet(f"{R}/nav/{tag(opt, pk, v)}.parquet")
        ev = pd.read_csv(f"{R}/nav/events_{tag(opt, pk, v)}.csv")
        nav0 = pd.concat([pd.Series([float(g.USD)], index=[df.index[0] - pd.Timedelta(hours=1)]), df["usd"]])
        s = {"years": yearly(df["usd"], g.USD), "info": counts_of(ev, ctl_ev[pk]), "pool": pk,
             "total": float(df["usd"].iloc[-1] / g.USD - 1), "cagr": g.cagr(nav0),
             "mdd": float((nav0 / nav0.cummax() - 1).min())}
        row = json.load(open(f"{R}/rows/{opt}_{pk}_{v}_continuous_{START}.json"))
        s.update({k: row[k] for k in ("gas", "impact", "swap_fee") if k in row})
        if modes:
            s["attr"], chk = attribution(df, ev, modes)
            if chk:
                out["fee_check"][key] = chk
        out["series"][key] = s
        print(key, {k: round(x, 4) for k, x in s.items() if isinstance(x, float)},
              {y: round(a["other"], 4) for y, a in s.get("attr", {}).items()}, flush=True)
    print(json.dumps(out["fee_check"], indent=1))
    with open(f"{R}/c1_drawdown_ledger.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
