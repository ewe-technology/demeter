"""
Calendar-year return, max drawdown and P&L attribution for single-pool Uniswap V3 runs (pool_lp_windows.py,
pool_lp_batch.py and anything else that writes the same files):

  nav_<tag>.csv     minute index, columns net (after every cost) and price (base coin in the quote)
  events_<tag>.csv  t, kind: start | recentre | on | off  (on / off = the gate switching, at that minute)

The position is rebuilt minute by minute from the events. A range [p/kd, p*ku] is placed at the event's price and
sized to the NAV right after the event; a spot sleeve holds a fixed base-coin share; cash holds nothing. Then each
minute's NAV change splits into
  price   the held position's model value change (V3 curve included, so impermanent loss is in here)
  fees    what is left at minutes without an action, inside a range: the LP fees
  costs   what is left at action minutes (swap fee + price impact + gas), split by a windows CSV if given
and the components below are fractions of the year's starting NAV:
  LP runs     hold (the year's first mix held still), il (price - hold), fees, swap, impact, gas | costs, other
  gated runs  on (price while the gate is on), off (price while off), fees, swap, impact, gas | costs, other
'other' is the remainder (actual return minus the rest); it should stay within a point or two.

Check the fee estimate with fee_check() before trusting it: a mis-sized model shows up as a slope of the hourly
residual on the hourly price change; real fees are an intercept.

Spec (JSON), run from the folder the dirs are relative to (samples/strategy-example on the backtest host):
{
  "years": ["2022", "2023", "2024", "2025", "2026"],
  "files": {"2026": {"start": "2025-10-01", "from": "2026-01-01"}},   // default: start "<y>-01-01", whole file
  "costs_csv": "result/pool-lp-windows/windows*.csv",                   // optional: width,start,swap_fee,impact,gas
  "runs": [
    {"name": "w20", "dir": "result/pool-lp-windows", "prefix": "w20", "initial": 100000,
     "modes": {"lp": ["range", 1.2, 1.2]}},
    {"name": "g_down", "dir": "result/pool-lp-windows", "prefix": "g_down", "initial": 100000,
     "modes": {"on": ["spot", 1.0], "off": ["range", 1.4, 1.01]}},
    {"name": "g_spot100", "dir": "...", "prefix": "...", "initial": 100000, "modes": {"on": ["spot", 1.0], "off": ["cash"]}},
    {"name": "gd_half", "dir": "...", "prefix": "...", "initial": 100000, "modes": null}      // returns only
  ]
}
  python lp_attribution.py spec.json out.json
The output maps each run name to {"years": {y: {ret, mdd}}, "attr": {y: {...}}, "info": {y: {...}}} (the series
shape of assets/pnl_lib.js) plus "_bench": {y: {"hold_base": {ret, mdd}, "hold_5050": {ret, mdd}}} from the
price column of the first run that has the year.
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd


def vnorm(p, p0, kd, ku):
    """V3 position value per unit of liquidity at price p, for a range placed at p0."""
    pa, pb = p0 / kd, p0 * ku
    q = np.clip(p, pa, pb)
    return (1 / np.sqrt(q) - 1 / np.sqrt(pb)) * p + (np.sqrt(q) - np.sqrt(pa))


def base_share(p, p0, kd, ku):
    """Value share of the base coin in that position."""
    pa, pb = p0 / kd, p0 * ku
    q = np.clip(p, pa, pb)
    x = (1 / np.sqrt(q) - 1 / np.sqrt(pb)) * p
    return x / (x + np.sqrt(q) - np.sqrt(pa))


def segments(index, nav, price, events, modes):
    """Per event: (position in index, mode, placement price, scale, state)."""
    pos = np.asarray(index.searchsorted(pd.to_datetime(events["t"]).values))
    state, out = None, []
    for kind, i in zip(events["kind"], pos):
        if kind in ("on", "off"):
            state = kind
        mode, st = (modes["lp"], "lp") if "lp" in modes else (modes[state], state)
        p0 = price[i]
        if mode[0] == "range":
            scale = nav[i] / vnorm(p0, p0, mode[1], mode[2])
        else:
            scale = nav[i] if mode[0] == "spot" else 0.0
        out.append((i, tuple(mode), p0, scale, st))
    return out


def decompose(nav, price, segs):
    """Per minute: model price change, fee residual, cost residual, gate-on flag, base-coin share."""
    n = len(nav)
    pos = np.array([s[0] for s in segs])
    seg_of = np.searchsorted(pos, np.arange(n), side="right") - 1  # the segment held after minute t's action
    prev = np.concatenate([[-1], seg_of[:-1]])                     # the segment held over minute t's move
    is_event = np.zeros(n, bool)
    is_event[pos] = True
    dnav = np.diff(nav, prepend=nav[0])
    price_eff, fees, cost, on = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n, bool)
    share = np.full(n, np.nan)
    for s, (_, mode, p0, scale, st) in enumerate(segs):
        own = np.nonzero(seg_of == s)[0]
        if mode[0] == "range":
            share[own] = base_share(price[own], p0, mode[1], mode[2])
        else:
            share[own] = mode[1] if mode[0] == "spot" else 0.0
        idx = np.nonzero(prev == s)[0]
        if not len(idx):
            continue
        p1, pp = price[idx], price[idx - 1]
        if mode[0] == "range":
            pe = scale * (vnorm(p1, p0, mode[1], mode[2]) - vnorm(pp, p0, mode[1], mode[2]))
        elif mode[0] == "spot":
            pe = scale * mode[1] * (p1 - pp) / p0
        else:
            pe = np.zeros(len(idx))
        price_eff[idx] = pe
        res = dnav[idx] - pe
        ev = is_event[idx]
        cost[idx[ev]] = res[ev]
        if mode[0] == "range":
            fees[idx[~ev]] = res[~ev]
        on[idx] = st == "on"
    return price_eff, fees, cost, on, share


def fee_check(nav_df, events, modes):
    """Hourly regression of the fee residual on the model price change, inside range segments.
    Returns fractions of the first NAV. Trust the fee split when slope_part is small next to intercept_part
    (|slope_part| was <= 3 pt a year in reports/single_pool_loop.md)."""
    nav, price = nav_df["net"].to_numpy(), nav_df["price"].astype(float).ffill().to_numpy()
    pe, fe, _, _, _ = decompose(nav, price, segments(nav_df.index, nav, price, events, modes))
    inside = fe != 0
    df = pd.DataFrame({"r": fe[inside], "m": pe[inside]}, index=nav_df.index[inside]).groupby(pd.Grouper(freq="h")).sum()
    df = df[(df["r"] != 0) | (df["m"] != 0)]
    b, a = np.polyfit(df["m"], df["r"], 1)
    return {"slope": float(b), "intercept_part": float(a * len(df) / nav[0]),
            "slope_part": float(b * df["m"].sum() / nav[0]), "residual_total": float(df["r"].sum() / nav[0])}


def mdd(x):
    return float((x / np.maximum.accumulate(x) - 1).min())


def run_years(run, years, files, costs, bench):
    out = {"years": {}, "attr": {}, "info": {}}
    for y in years:
        f = files.get(y, {"start": f"{y}-01-01", "from": None})
        path = f"{run['dir']}/nav_{run['prefix']}_{f['start']}.csv"
        if not os.path.exists(path):
            continue
        nav_df = pd.read_csv(path, index_col=0, parse_dates=True)
        if f.get("from") is None and nav_df.index[-1] < pd.Timestamp(f"{y}-12-30") and y != years[-1]:
            print(f"  {run['name']} {y}: {path} ends {nav_df.index[-1].date()}, skipped (overwritten by a test run?)")
            continue
        nav, price = nav_df["net"].to_numpy(), nav_df["price"].astype(float).ffill().to_numpy()
        lo = 0 if f.get("from") is None else int(nav_df.index.searchsorted(pd.Timestamp(f["from"])))
        base = run["initial"] if lo == 0 else nav[lo - 1]
        pbase = price[0] if lo == 0 else price[lo - 1]
        out["years"][y] = {"ret": float(nav[-1] / base - 1), "mdd": mdd(np.concatenate([[base], nav[lo:]]))}
        if y not in bench:
            pp = np.concatenate([[pbase], price[lo:]]) / pbase
            bench[y] = {"hold_base": {"ret": float(pp[-1] - 1), "mdd": mdd(pp)},
                        "hold_5050": {"ret": float(0.5 * (pp[-1] - 1)), "mdd": mdd(0.5 + 0.5 * pp)}}
        evf = f"{run['dir']}/events_{run['prefix']}_{f['start']}.csv"
        if not run.get("modes") or not os.path.exists(evf):
            continue
        events = pd.read_csv(evf)
        pe, fe, co, on, share = decompose(nav, price, segments(nav_df.index, nav, price, events, run["modes"]))
        sl = slice(max(lo, 1), None)
        entry = nav[0] - run["initial"] if lo == 0 else 0.0  # the buy-in from cash at the first bar
        a = {}
        if "lp" in run["modes"]:
            a["hold"] = float(share[lo]) * float(price[-1] / pbase - 1)
            a["il"] = float(pe[sl].sum()) / base - a["hold"]
        else:
            a["on"] = float(pe[sl][on[sl]].sum()) / base
            a["off"] = float(pe[sl][~on[sl]].sum()) / base
        if fe[sl].any():
            a["fees"] = float(fe[sl].sum()) / base
        total_cost = (float(co[sl].sum()) + entry) / base
        c = costs.get((run["prefix"], f["start"]))
        if c is not None and sum(c) > 0:
            a.update({"swap": total_cost * c[0] / sum(c), "impact": total_cost * c[1] / sum(c), "gas": total_cost * c[2] / sum(c)})
        else:
            a["costs"] = total_cost
        a["other"] = out["years"][y]["ret"] - sum(a.values())
        out["attr"][y] = a
        after = pd.to_datetime(events["t"]) >= nav_df.index[lo]
        out["info"][y] = {"重建次數": int((after & (events["kind"] == "recentre")).sum()),
                          "濾網切換": int((after & events["kind"].isin(["on", "off"])).sum())}
        print(f"  {run['name']} {y}: ret {out['years'][y]['ret']:+.4f} mdd {out['years'][y]['mdd']:+.4f} "
              + " ".join(f"{k} {v:+.4f}" for k, v in a.items()), flush=True)
    return out


def main(spec_path, out_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    costs = {}
    for f in glob.glob(spec["costs_csv"]) if spec.get("costs_csv") else []:
        for _, r in pd.read_csv(f).iterrows():
            costs[(r["width"], str(r["start"]))] = (r["swap_fee"], r["impact"], r["gas"])
    result, bench = {}, {}
    for run in spec["runs"]:
        print(run["name"], flush=True)
        result[run["name"]] = run_years(run, spec["years"], spec.get("files", {}), costs, bench)
    result["_bench"] = bench
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
