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

  PYTHONPATH=../.. python c1_drawdown.py --h58          # writes result/gate-lp-options/h58_episodes.json
  python c1_drawdown.py --check --prepool               # writes result/gate-lp-options/h59_prepool.json
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
    a = a.parse_args()
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
