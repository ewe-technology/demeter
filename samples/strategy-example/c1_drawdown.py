"""
H58 and the pre-pool spot books of reports/plan_2026-10-21_c1_drawdown.md (registered in 22db440).

  --h58    C1's ladder and its control (H51's single-slice continuous books, H48's C1 bit for bit), both pools: the 5
           deepest drawdowns of each book (peak -> trough, at least 10%, not overlapping), each split by
           lp_attribution.decompose into gate-on price, gate-off price, fees and costs (fractions of the peak NAV),
           with the other book over the same span. Run on the strategy host, lp_attribution.py next to this file.
  --check  the stylised books reproduce the plan's section 0 numbers (Binance daily, 0.10% a day fee proxy).
  --prepool  H59 - H61 and both bases on Binance BTC daily closes 2018-04-01 .. 2021-12-31, fee proxy 0 / 0.05% /
           0.10% a day while the price is inside the ladder (listed only, plan 4).

Stylised book: EMA100 on the daily close, decided and traded at that close (the 00 h gate); on = 100% BTC, off = a
V3 ladder [p / 1.40, p x 1.01] checked once a day, switches 10 bps, a re-centre pays 40 bps on the BTC it sells.

  --spells   D1 of reports/plan_2026-10-21_c1_spells.md (registered in 0204743): every gate-off spell of C1's ladder
           on both pools, and the five ex-ante measures against the spell's ladder P&L, with the stylised pre-pool spells.
  --h62-diag D2: H62 (hourly lower-edge check) against C1's ladder, by year, by its hourly re-centres, by cost bar.

  PYTHONPATH=../.. python c1_drawdown.py --h58          # writes result/gate-lp-options/h58_episodes.json
  python c1_drawdown.py --check --prepool               # writes result/gate-lp-options/h59_prepool.json
  PYTHONPATH=../.. python c1_drawdown.py --spells --h62-diag   # d1_spells.json, d2_h62.json (strategy host)
"""
import argparse
import json
import math

import numpy as np
import pandas as pd

RESULT_DIR = "result/gate-lp-options"
SW, RC = 10e-4, 40e-4
H51 = "H51C1"
START = "2022-01-01"
MODES = {"ladder": {"on": ["spot", 1.0], "off": ["range", 1.40, 1.01]}, "ctl": {"on": ["spot", 1.0], "off": ["cash"]}}


# ---------------------------------------------------------------- H58

def episodes(nav: pd.Series, n: int = 5, floor: float = -0.10) -> list[tuple]:
    dd = nav / nav.cummax() - 1
    used = pd.Series(False, index=nav.index)
    out = []
    for _ in range(n):
        d = dd.where(~used)
        if d.min() > floor:
            break
        tr = d.idxmin()
        pk = nav[:tr].idxmax()
        later = nav[tr:]
        rec = later[later >= nav[pk]]
        end = rec.index[0] if len(rec) else nav.index[-1]
        used[pk:end] = True
        out.append((pk, tr, end))
    return sorted(out)


def run_h58():
    from lp_attribution import decompose, segments
    out = {}
    for pk in ("99ac", "9db9"):
        books = {}
        for v in ("ladder", "ctl"):
            tag = f"{H51}_{pk}_{v}_n1_h00_100k_continuous_{START}"
            df = pd.read_parquet(f"{RESULT_DIR}/nav/{tag}.parquet")
            ev = pd.read_csv(f"{RESULT_DIR}/nav/events_{tag}.csv")
            nav, price = df["usd"].to_numpy(), df["price"].astype(float).ffill().to_numpy()
            pe, fe, co, on, _ = decompose(nav, price, segments(df.index, nav, price, ev, MODES[v]))
            books[v] = (df, ev, pe, fe, co, on)
        for v, other in (("ladder", "ctl"), ("ctl", "ladder")):
            df, ev, pe, fe, co, on = books[v]
            nav = df["usd"]
            px = df["price"].astype(float).ffill()
            t_ev = pd.to_datetime(ev["t"])
            rows = []
            for p_t, t_t, e_t in episodes(nav):
                i0, i1 = nav.index.get_loc(p_t), nav.index.get_loc(t_t)
                sl = slice(i0 + 1, i1 + 1)
                base = float(nav.iloc[i0])
                o = books[other][0]["usd"].loc[p_t:t_t]
                inside = (t_ev > p_t) & (t_ev <= t_t)
                r = {"peak": str(p_t), "trough": str(t_t), "recovered": str(e_t) if e_t != nav.index[-1] else None,
                     "dd": float(nav.iloc[i1] / base - 1), "days": (t_t - p_t).days,
                     "off_share": float((~on[sl]).mean()), "btc": float(px.iloc[i1] / px.iloc[i0] - 1),
                     "on_price": float(pe[sl][on[sl]].sum() / base), "off_price": float(pe[sl][~on[sl]].sum() / base),
                     "fees": float(fe[sl].sum() / base), "costs": float(co[sl].sum() / base),
                     "moves": int((inside & (ev["kind"] == "recentre")).sum()),
                     "switches": int((inside & ev["kind"].isin(["on", "off"])).sum()),
                     f"{other}_ret": float(o.iloc[-1] / o.iloc[0] - 1),
                     f"{other}_mdd": float((o / o.cummax() - 1).min())}
                r["other"] = r["dd"] - r["on_price"] - r["off_price"] - r["fees"] - r["costs"]
                rows.append(r)
                print(f"{pk} {v:6s} {p_t:%Y-%m-%d} -> {t_t:%Y-%m-%d} {r['dd']:+.1%} ({r['days']}d, off {r['off_share']:.0%},"
                      f" BTC {r['btc']:+.1%}): on {r['on_price']:+.1%} off {r['off_price']:+.1%} fees {r['fees']:+.1%}"
                      f" costs {r['costs']:+.1%} other {r['other']:+.1%}; {other} same span {r[f'{other}_ret']:+.1%}"
                      f" (mdd {r[f'{other}_mdd']:+.1%})", flush=True)
            out[f"{pk}_{v}"] = rows
    with open(f"{RESULT_DIR}/h58_episodes.json", "w") as f:
        json.dump(out, f, indent=1)


# ---------------------------------------------------------------- stylised daily books

def pv(L, a, b, p):
    sp = math.sqrt(min(max(p, a), b))
    x, y = L * (1 / sp - 1 / math.sqrt(b)), L * (sp - math.sqrt(a))
    return x * p + y, x * p


def mk(value, p, down, up=1.01):
    a, b = p / down, p * up
    sp = math.sqrt(p)
    return value / ((1 / sp - 1 / math.sqrt(b)) * p + (sp - math.sqrt(a))), a, b


def stylised(px: pd.Series, gate: pd.Series, start: str, end: str, fee: float = 0.0, size: float = 1.0,
             max_days: int | None = None, dd_scale: float | None = None, vol_t: float | None = None,
             sw: float = SW) -> pd.Series:
    """size 0 is the control; dd_scale is H59's D, max_days H60's N; vol_t is H64's T (with dd_scale: H65, both
    shares multiplied and sized from the whole book at every placement); sw the switch cost."""
    rv = np.log(px).diff().rolling(30).std() * math.sqrt(365)
    p_, g = px[start:end], gate[start:end]
    nav, peak, state = 1.0, 1.0, None
    L = a = b = None
    cash = 0.0
    days_off = 0
    out, prev = [], None
    for t, p in p_.items():
        on = bool(g[t])
        if prev is not None:
            if state:
                nav *= p / prev
            elif L is not None:
                if fee and (a <= prev <= b or a <= p <= b):
                    L *= 1 + fee  # fees reinvested in the ladder
                nav = pv(L, a, b, p)[0] + cash
        peak = max(peak, nav)
        s_vol = min(1.0, vol_t / rv[t]) if vol_t and rv[t] > 0 else 1.0
        if state is None or on != state:
            nav *= 1 - sw
            L = None
            if not on:
                days_off = 0
                s = size * s_vol * (max(0.0, 1 - (1 - nav / peak) / dd_scale) if dd_scale else 1.0)
                if s > 0:
                    L, a, b = mk(nav * s, p, 1.40)
                cash = nav * (1 - s)
            state = on
        elif not on:
            days_off += 1
            if max_days and days_off == max_days and L is not None:
                v, btc = pv(L, a, b, p)
                nav = v - btc * RC + cash
                L, cash = None, nav
            elif L is not None and not (a <= p <= b):
                v, btc = pv(L, a, b, p)
                v -= btc * RC
                tot = v + cash
                s_dd = max(0.0, 1 - (1 - tot / peak) / dd_scale) if dd_scale else 1.0
                if vol_t:
                    lad = tot * s_vol * s_dd
                else:
                    lad = min(v, tot * s_dd) if dd_scale else v
                L, a, b = mk(lad, p, 1.40) if lad > 0 else (None, None, None)
                cash, nav = tot - lad, tot
        out.append(nav)
        prev = p
    return pd.Series(out, index=p_.index)


def stats(s: pd.Series) -> dict:
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = s.iloc[-1] ** (1 / yrs) - 1
    mdd = float((s / s.cummax() - 1).min())
    return {"cagr": float(cagr), "mdd": mdd, "calmar": float(cagr / -mdd)}


VERSIONS = {"ctl": dict(size=0.0), "ladder": {}, "dd20": dict(dd_scale=0.20), "dd30": dict(dd_scale=0.30),
            "dd40": dict(dd_scale=0.40), "tc30": dict(max_days=30), "tc60": dict(max_days=60),
            "tc90": dict(max_days=90), "dd30_tc60": dict(dd_scale=0.30, max_days=60)}
# plan section 0 (fee proxy 0.10% a day): (CAGR, MDD) rounded to 0.1 pt
SECTION0 = {("2022-01-01", "ctl"): (0.303, -0.318), ("2022-01-01", "ladder"): (0.339, -0.366),
            ("2022-01-01", "dd30"): (0.304, -0.306), ("2022-01-01", "tc30"): (0.318, -0.265),
            ("2022-01-01", "tc60"): (0.336, -0.310), ("2018-01-01", "ctl"): (0.372, -0.698),
            ("2018-01-01", "ladder"): (0.187, -0.859), ("2018-01-01", "dd30"): (0.377, -0.698),
            ("2018-01-01", "tc30"): (0.225, -0.805), ("2018-01-01", "tc60"): (0.215, -0.813)}


def daily():
    px = pd.read_csv("binance_btcusdt_1d.csv", index_col=0, parse_dates=True)["close"].astype(float)
    return px, px > px.ewm(span=100, adjust=False).mean()


def check():
    px, gate = daily()
    ok = True
    for (s, v), (c, m) in SECTION0.items():
        r = stats(stylised(px, gate, s, "2025-12-31", fee=0.001, **VERSIONS[v]))
        same = round(r["cagr"], 3) == c and round(r["mdd"], 3) == m
        ok &= same
        print(f"{s} {v:7s} CAGR {r['cagr']:+.4f} MDD {r['mdd']:+.4f} vs {c:+.3f} {m:+.3f} {'ok' if same else 'DIFF'}")
    print("CHECK OK" if ok else "CHECK MISMATCH")


def prepool():
    px, gate = daily()
    out = {}
    for fee in (0.0, 0.0005, 0.001):
        key = f"{fee * 100:.2f}%"
        out[key] = {v: stats(stylised(px, gate, "2018-04-01", "2021-12-31", fee=fee, **kw)) for v, kw in VERSIONS.items()}
        print(f"fee proxy {key}/day, 2018-04-01 .. 2021-12-31:")
        for v, r in out[key].items():
            print(f"  {v:10s} CAGR {r['cagr']:+6.1%}  MDD {r['mdd']:6.1%}  Calmar {r['calmar']:5.2f}")
    with open(f"{RESULT_DIR}/h59_prepool.json", "w") as f:
        json.dump(out, f, indent=1)


# ---------------------------------------------------------------- D1, D2 (plan 2026-10-21 c1_spells)

def load_book(tag: str, modes: dict) -> dict:
    from lp_attribution import decompose, segments
    df = pd.read_parquet(f"{RESULT_DIR}/nav/{tag}.parquet")
    ev = pd.read_csv(f"{RESULT_DIR}/nav/events_{tag}.csv")
    nav, price = df["usd"].to_numpy(), df["price"].astype(float).ffill().to_numpy()
    pe, fe, co, on, share = decompose(nav, price, segments(df.index, nav, price, ev, modes))
    return {"nav": df["usd"], "price": df["price"].astype(float).ffill(), "ev": ev, "pe": pe, "fe": fe, "co": co,
            "on": on, "share": share}


def er(close: pd.Series) -> float:
    """Net log return over the sum of absolute daily log returns: -1 a straight fall, near 0 a chop."""
    lr = np.log(close).diff().dropna()
    s = float(lr.abs().sum())
    return float(lr.sum() / s) if s > 0 else 0.0


def ann_vol(close: pd.Series) -> float:
    return float(np.log(close).diff().dropna().std() * math.sqrt(365))


def spearman(a, b) -> float:
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return float(a.rank().corr(b.rank()))


def p00() -> pd.Series:
    """99ac's price at each 00:00 UTC (the close of the hour that ends then), from the hourly close cache."""
    import gate_lp_options as g
    hc = g.hourly_close("99ac").ffill()
    s = hc.shift(1)
    return s[s.index.hour == 0].dropna()


def off_spells(nav: pd.Series, ev: pd.DataFrame) -> list[tuple[int, int]]:
    """(bar of an off event, bar before the next on event) by position in nav."""
    sw = ev[ev["kind"].isin(["on", "off"])].copy()
    sw["t"] = pd.to_datetime(sw["t"])
    sw = sw.sort_values("t", kind="stable")
    out = []
    for i, r in enumerate(sw.itertuples()):
        if r.kind != "off":
            continue
        nxt = sw.iloc[i + 1:]
        nxt = nxt[nxt["kind"] == "on"]
        i0 = int(nav.index.searchsorted(r.t))
        i1 = int(nav.index.searchsorted(nxt["t"].iloc[0])) - 1 if len(nxt) else len(nav) - 1
        if i1 > i0:
            out.append((i0, i1))
    return out


MEASURES = ("M1", "M2", "M3", "M4", "M5")


def measure_rows(close: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> dict:
    before = close[(close.index > t0 - pd.Timedelta(days=31)) & (close.index <= t0)]
    first7 = close[(close.index >= t0) & (close.index <= t0 + pd.Timedelta(days=7))]
    inside = close[(close.index >= t0) & (close.index <= t1)]
    return {"M1": ann_vol(before), "M2": er(before), "M3": float(before.iloc[-1] / before.iloc[0] - 1),
            "M4": er(first7), "er": er(inside),
            "btc_max_fall": float((inside / inside.cummax() - 1).min()) if len(inside) else 0.0}


def corr_table(rows: list[dict], m5: bool = True) -> dict:
    out = {}
    for m in MEASURES if m5 else MEASURES[:4]:
        late = m in ("M4", "M5")
        use = [r for r in rows if r["days"] >= (14 if late else 5) and r.get(m) is not None]
        y = [r["pnl_from7"] if late else r["pnl"] for r in use]
        out[m] = {"rho": spearman([r[m] for r in use], y), "n": len(use)}
    return out


def run_spells():
    close = p00()
    out = {"pools": {}}
    for pk in ("99ac", "9db9"):
        b = load_book(f"{H51}_{pk}_ladder_n1_h00_100k_continuous_{START}", MODES["ladder"])
        nav, ev = b["nav"], b["ev"]
        t_ev = pd.to_datetime(ev["t"])
        rows = []
        for i0, i1 in off_spells(nav, ev):
            t0, t1 = nav.index[i0], nav.index[i1]
            base = float(nav.iloc[i0])
            sl = slice(i0 + 1, i1 + 1)
            i7 = int(nav.index.searchsorted(t0 + pd.Timedelta(days=7)))
            days = (t1 - t0).total_seconds() / 86400
            r = {"start": str(t0), "end": str(t1), "days": round(days, 2),
                 "btc": float(b["price"].iloc[i1] / b["price"].iloc[i0] - 1),
                 "pnl": float(nav.iloc[i1] / base - 1), "off_price": float(b["pe"][sl].sum() / base),
                 "fees": float(b["fe"][sl].sum() / base), "costs": float(b["co"][sl].sum() / base),
                 "fee_yield": float(b["fe"][sl].sum() / base / max(days, 1e-9) * 365),
                 "max_btc_share": float(np.nanmax(b["share"][i0:i1 + 1])),
                 "moves": int(((t_ev > t0) & (t_ev <= t1) & (ev["kind"] == "recentre")).sum()),
                 **measure_rows(close, t0, t1)}
            if i7 < i1:
                r["pnl_from7"] = float(nav.iloc[i1] / nav.iloc[i7] - 1)
                r["M5"] = float(b["fe"][i0 + 1:i7 + 1].sum() / base / 7 * 365)
            else:
                r["pnl_from7"], r["M5"] = None, None
            rows.append(r)
        losses = sorted((r["pnl"] for r in rows if r["pnl"] < 0))
        summary = {"spells": len(rows), "losing_share": sum(r["pnl"] < 0 for r in rows) / len(rows),
                   "top3_loss_share": float(sum(losses[:3]) / sum(losses)) if losses else 0.0,
                   "corr": corr_table(rows)}
        out["pools"][pk] = {"rows": rows, "summary": summary}
        print(f"\n{pk}: {len(rows)} spells, losing {summary['losing_share']:.0%}, top 3 losses "
              f"{summary['top3_loss_share']:.0%} of all losses")
        for r in rows:
            print(f"  {r['start'][:10]} -> {r['end'][:10]} {r['days']:6.1f}d BTC {r['btc']:+6.1%} ER {r['er']:+.2f} "
                  f"pnl {r['pnl']:+6.1%} = off {r['off_price']:+6.1%} fees {r['fees']:+5.1%} costs {r['costs']:+5.1%}"
                  f" | fee/yr {r['fee_yield']:5.0%} maxBTC {r['max_btc_share']:4.0%} moves {r['moves']}"
                  f" | M1 {r['M1']:.0%} M2 {r['M2']:+.2f} M3 {r['M3']:+.1%} M4 {r['M4']:+.2f}", flush=True)
        print("  corr:", {m: (round(v["rho"], 2), v["n"]) for m, v in summary["corr"].items()})
    # the stylised pre-pool spells (Binance daily, 10 bps switches, 0.10% a day fee proxy)
    px, gate = daily()
    s0, s1 = "2018-04-01", "2021-12-31"
    nav = stylised(px, gate, s0, s1, fee=0.001, sw=10e-4)
    g = gate[s0:s1]
    rows = []
    run_id = (g != g.shift()).cumsum()
    for _, seg in g[~g].groupby(run_id[~g]):
        t0, t1 = seg.index[0], seg.index[-1]
        days = (t1 - t0).days
        r = {"start": str(t0.date()), "end": str(t1.date()), "days": days,
             "pnl": float(nav[t1] / nav[t0] - 1), **measure_rows(px, t0, t1)}
        t7 = t0 + pd.Timedelta(days=7)
        r["pnl_from7"] = float(nav[t1] / nav.asof(t7) - 1) if t7 < t1 else None
        rows.append(r)
    out["prepool"] = {"rows": rows, "corr": corr_table(rows, m5=False)}
    print("\nprepool stylised spells:", len(rows), {m: (round(v["rho"], 2), v["n"]) for m, v in out["prepool"]["corr"].items()})
    verdict = {}
    for m in MEASURES:
        a, b_ = out["pools"]["99ac"]["summary"]["corr"][m]["rho"], out["pools"]["9db9"]["summary"]["corr"][m]["rho"]
        ok = abs(a) >= 0.4 and abs(b_) >= 0.4 and np.sign(a) == np.sign(b_)
        if m != "M5":
            c = out["prepool"]["corr"][m]["rho"]
            ok = ok and np.sign(c) == np.sign(a) and abs(c) >= 0.2
        verdict[m] = bool(ok)
    out["verdict"] = verdict
    print("worth registering:", verdict)
    with open(f"{RESULT_DIR}/d1_spells.json", "w") as f:
        json.dump(out, f, indent=1)


def run_h62_diag():
    out = {}
    for pk in ("99ac", "9db9"):
        lad = load_book(f"{H51}_{pk}_ladder_n1_h00_100k_continuous_{START}", MODES["ladder"])
        hd = load_book(f"H62_{pk}_hdown_continuous_{START}", MODES["ladder"])
        idx = lad["nav"].index.intersection(hd["nav"].index)
        rel = (hd["nav"].reindex(idx) / lad["nav"].reindex(idx))
        years = {}
        for y in range(2022, 2027):
            parts = {}
            for k, b in (("ladder", lad), ("hdown", hd)):
                ix = np.nonzero(b["nav"].index.year == y)[0]
                base = float(b["nav"].iloc[ix[0] - 1]) if ix[0] > 0 else float(b["nav"].iloc[0])
                on = b["on"][ix]
                parts[k] = {"ret": float(b["nav"].iloc[ix[-1]] / base - 1),
                            "on": float(b["pe"][ix][on].sum() / base), "off": float(b["pe"][ix][~on].sum() / base),
                            "fees": float(b["fe"][ix].sum() / base), "costs": float(b["co"][ix].sum() / base)}
            years[str(y)] = {k: parts["hdown"][k] - parts["ladder"][k] for k in parts["hdown"]}
        moves = []
        ev = hd["ev"]
        for t in pd.to_datetime(ev.loc[ev["kind"] == "recentre_h", "t"]):
            i = int(idx.searchsorted(t))
            j = int(idx.searchsorted(t + pd.Timedelta(days=7)))
            j = min(j, len(idx) - 1)
            k = int(hd["nav"].index.searchsorted(t))
            moves.append({"t": str(t), "price": float(hd["price"].iloc[k]), "cost": float(hd["co"][k] / hd["nav"].iloc[k - 1]),
                          "rel_7d": float(rel.iloc[j] / rel.iloc[i - 1] - 1)})
        gap22 = float(rel[rel.index < pd.Timestamp("2022-12-31 23:59")].iloc[-1] / rel.iloc[0] - 1)
        in22 = [m for m in moves if m["t"].startswith("2022")]
        same = sorted((m["rel_7d"] for m in in22 if np.sign(m["rel_7d"]) == np.sign(gap22)), key=abs, reverse=True)[:3]
        top3 = float(sum(same))
        nav = hd["nav"]
        dd = nav / nav.cummax() - 1
        tr = dd.idxmin()
        pk_t = nav[:tr].idxmax()
        ln = lad["nav"].loc[pk_t:tr]
        costs = {}
        for k, b in (("ladder", lad), ("hdown", hd)):
            c = pd.Series(b["co"] / b["nav"].shift(1).bfill().to_numpy(), index=b["nav"].index)
            costs[k] = [{"t": str(t), "cost": float(v)} for t, v in c.nsmallest(10).items()]
        out[pk] = {"years": years, "hourly_moves": moves, "gap_2022": gap22, "top3_same_sign_2022": top3,
                   "concentrated": bool(abs(top3) >= 0.5 * abs(gap22)) if gap22 else False,
                   "hdown_mdd": {"peak": str(pk_t), "trough": str(tr), "dd": float(dd[tr]),
                                 "ladder_same_span_ret": float(ln.iloc[-1] / ln.iloc[0] - 1),
                                 "ladder_same_span_mdd": float((ln / ln.cummax() - 1).min())},
                   "top_cost_bars": costs}
        print(f"\n{pk}: H62 - C1 by year (ret / on / off / fees / costs):")
        for y, d in years.items():
            print(f"  {y}: " + " ".join(f"{k} {v:+.1%}" for k, v in d.items()))
        print(f"  hourly re-centres: {len(moves)}; " + "; ".join(f"{m['t'][:16]} cost {m['cost']:+.2%} 7d {m['rel_7d']:+.1%}" for m in moves))
        print(f"  2022 gap (relative NAV) {gap22:+.1%}, 3 largest same-sign hourly moves {top3:+.1%} -> "
              f"{'concentrated' if out[pk]['concentrated'] else 'price path'}")
        print(f"  H62 mdd {dd[tr]:+.1%} {pk_t} -> {tr}; C1 same span {out[pk]['hdown_mdd']['ladder_same_span_ret']:+.1%}")
        print("  top cost bars hdown:", [(c['t'][:16], round(c['cost'] * 100, 2)) for c in costs["hdown"][:5]])
        print("  top cost bars ladder:", [(c['t'][:16], round(c['cost'] * 100, 2)) for c in costs["ladder"][:5]])
    with open(f"{RESULT_DIR}/d2_h62.json", "w") as f:
        json.dump(out, f, indent=1)


VOL_VERSIONS = {"ctl": dict(size=0.0), "ladder": {}, "vol30": dict(vol_t=0.30), "vol40": dict(vol_t=0.40),
                "vol50": dict(vol_t=0.50), "vol40_dd30": dict(vol_t=0.40, dd_scale=0.30)}


def prepool_vol():
    """Plan cost_vol section 4, listed: H64, H65 and both bases, fee proxy 0 / 0.05% / 0.10%, switches 10 / 50 bps."""
    px, gate = daily()
    out = {}
    for sw in (10e-4, 50e-4):
        for fee in (0.0, 0.0005, 0.001):
            key = f"sw{sw * 1e4:.0f}bps_fee{fee * 100:.2f}%"
            out[key] = {v: stats(stylised(px, gate, "2018-04-01", "2021-12-31", fee=fee, sw=sw, **kw))
                        for v, kw in VOL_VERSIONS.items()}
            print(f"{key}, 2018-04-01 .. 2021-12-31:")
            for v, r in out[key].items():
                print(f"  {v:10s} CAGR {r['cagr']:+6.1%}  MDD {r['mdd']:6.1%}  Calmar {r['calmar']:5.2f}")
    with open(f"{RESULT_DIR}/h64_prepool.json", "w") as f:
        json.dump(out, f, indent=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--h58", action="store_true")
    a.add_argument("--check", action="store_true")
    a.add_argument("--prepool", action="store_true")
    a.add_argument("--prepool-vol", action="store_true")
    a.add_argument("--spells", action="store_true")
    a.add_argument("--h62-diag", action="store_true")
    a = a.parse_args()
    if a.spells:
        run_spells()
    if a.h62_diag:
        run_h62_diag()
    if a.prepool_vol:
        prepool_vol()
    if a.h58:
        run_h58()
    if a.check:
        check()
    if a.prepool:
        prepool()


if __name__ == "__main__":
    main()
