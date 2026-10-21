"""
The standard metric set for the H46 - H57 books (reports/plan_2026-10-19_gate_lp_options.md), descriptive only:
return (total, CAGR, fee income, excess over HODL), risk (max drawdown, annual volatility, downside deviation),
risk-adjusted (Sharpe and Sortino at a 4% and a 0% risk-free rate, Calmar), LP-specific (in-range share of the hours
the LP is deployed, impermanent loss, LVR, fee / LVR, moves, switches, gas, impact and swap fees) and robustness
(rolling 90-day returns, mean monthly return in bull / bear / sideways months).

Benchmarks per option, on the option's own period: HODL of its base coin, the pool's two tokens 50/50 rebalanced
every day at 00:00 (paying the spot bps on the traded amount and one swap's gas), and a fixed +-20% LP in the same
pool with no gate (re-centred when out of range at the 00:00 check; run here as option FIX, gate "all").

Conventions:
- Every book starts at $100k one hour before its first bar, so the entry cost is in the returns (as gate_lp_pnl).
- Daily returns from each day's last hourly NAV; annualised with 365 days. The risk-free rate is an assumption (there
  is no lending-rate data in the repo): 4% a year in the main columns, 0% beside them.
- LP metrics come from lp_attribution's position rebuild on the book in its quote token (USD / USD-per-quote for the
  WBTC- and WETH-quoted pools), converted back to USD by the hour. LVR is the hourly-rebalancing loss
  L * dP^2 / (4 P^1.5) while the price is inside the range, so it is a lower bound of continuous LVR.
- Regimes: a calendar month is bull when the option's base coin rose more than 10% in it, bear when it fell more than
  10%, otherwise sideways.

Run from samples/strategy-example on the strategy host, with lp_attribution.py copied next to it:
  PYTHONPATH=../.. python gate_lp_metrics.py      # writes result/gate-lp-options/metrics.json
"""
import json
import os
from datetime import date

import numpy as np
import pandas as pd

import gate_lp_options as g
from lp_attribution import decompose, segments, vnorm
from pool_lp_windows import eth_daily

R = g.RESULT_DIR
D22, D24, A1D = date(2022, 1, 1), date(2024, 1, 1), date(2024, 10, 13)
END = pd.Timestamp("2026-09-30 23:00")
END_IS = pd.Timestamp("2025-12-31 23:00")
RF = {"4": 0.04, "0": 0.0}


def on_off(on, off):
    return {"on": on, "off": off}


# key: (label, option, pool, [names], start, end, modes or None, control key, option family for the benchmarks)
SERIES = {
    "a1_ctl": ("A1 對照組", "A1", "e8f7", ["ctl"], A1D, END, None, None, "A1"),
    "a1_lp": ("A1 ±0.25%", "A1", "e8f7", ["w0.25"], A1D, END, on_off(["range", 1.0025, 1.0025], ["cash"]), "a1_ctl", "A1"),
    "a2_ctl": ("A2 對照組", "A2", "1098", ["ctl"], D24, END, None, None, "A2"),
    "a2_lp": ("A2 往上偏", "A2", "1098", ["up_02_08"], D24, END, on_off(["range", 1.002, 1.008], ["cash"]), "a2_ctl", "A2"),
    "b1_ctl": ("B1 對照組", "B1", "4585", ["ctl"], D22, END, None, None, "B1"),
    "b1_lp": ("B1 ±20%", "B1", "4585", ["w20"], D22, END, on_off(["range", 1.20, 1.20], ["cash"]), "b1_ctl", "B1"),
    "c1_ctl": ("C1 對照組", "H51C1", "99ac", ["ctl_n1_h00_100k"], D22, END, None, None, "C1"),
    "c1_ladder": ("C1 買單", "H51C1", "99ac", ["ladder_n1_h00_100k"], D22, END,
                  on_off(["spot", 1.0], ["range", 1.40, 1.01]), "c1_ctl", "C1"),
    "c1_ctl3": ("C1 對照組 3 份", "H51C1", "99ac", [f"ctl_n3_h{h:02d}_100k" for h in (0, 8, 16)], D22, END, None, None, "C1"),
    "c1_ladder3": ("C1 買單 3 份", "H51C1", "99ac", [f"ladder_n3_h{h:02d}_100k" for h in (0, 8, 16)], D22, END,
                   on_off(["spot", 1.0], ["range", 1.40, 1.01]), "c1_ctl3", "C1"),
    "h56_ctl100": ("C1 現行 EMA100 現貨（2022～2025）", "H56C1", "99ac", ["ema100_ctl"], D22, END_IS, None, None, "C1_IS"),
    "h56_l140": ("C1 原本 EMA100 + p/1.40（2022～2025）", "H56C1", "99ac", ["ema100_l140"], D22, END_IS,
                 on_off(["spot", 1.0], ["range", 1.40, 1.01]), "h56_ctl100", "C1_IS"),
    "h56_ctl50": ("C1 EMA50 現貨（2022～2025）", "H56C1", "99ac", ["ema50_ctl"], D22, END_IS, None, None, "C1_IS"),
    "h56_pick": ("C1 選中 EMA50 + p/1.20（2022～2025）", "H56C1", "99ac", ["ema50_l120"], D22, END_IS,
                 on_off(["spot", 1.0], ["range", 1.20, 1.01]), "h56_ctl50", "C1_IS"),
    "c2_ctl": ("C2 對照組", "C2", "99ac", ["ctl50"], D22, END, None, None, "C2"),
    "c2_lp": ("C2 ±20%", "C2", "99ac", ["w20"], D22, END, on_off(["range", 1.20, 1.20], ["cash"]), "c2_ctl", "C2"),
    "c3_ctl": ("C3 對照組", "C3", "8ad5", ["ctl"], D22, END, None, None, "C3"),
    "c3_lp": ("C3 ±10%", "C3", "8ad5", ["w10"], D22, END, on_off(["spot", 1.0], ["range", 1.10, 1.10]), "c3_ctl", "C3"),
    "c4_ctl": ("C4 對照組", "C4", "8ad5", ["ctl50"], D22, END, None, None, "C4"),
    "c4_lp": ("C4 ±30%", "C4", "8ad5", ["w30"], D22, END, on_off(["range", 1.30, 1.30], ["cash"]), "c4_ctl", "C4"),
}
# the A2 + C1 mix from 2024-01-01: half of each $100k book (gate_lp_combo)
MIX = {"mix_ctl": ("兩個對照組各半", [("A2", "1098", "ctl"), ("C1", "99ac", "ctl")], None),
       "mix": ("A2 + C1 各半", [("A2", "1098", "up_02_08"), ("C1", "99ac", "ladder")], "mix_ctl")}

# family: (base coin for HODL and regimes, the pool's pair for the 50/50, its bps, fixed LP pool, start, end)
FAMILY = {"A1": ("btc", ("wbtc", "cbbtc"), 1, "e8f7", A1D, END), "A2": ("eth", ("weth", "wsteth"), 1, "1098", D24, END),
          "B1": ("5050", ("wbtc", "weth"), 10, "4585", D22, END), "C1": ("btc", ("wbtc", "usd"), 10, "99ac", D22, END),
          "C1_IS": ("btc", ("wbtc", "usd"), 10, "99ac", D22, END_IS),
          "C2": ("btc", ("wbtc", "usd"), 10, "99ac", D22, END), "C3": ("eth", ("weth", "usd"), 11, "8ad5", D22, END),
          "C4": ("eth", ("weth", "usd"), 11, "8ad5", D22, END), "MIX": ("5050", None, None, None, D24, END)}
FIXED = {"e8f7": A1D, "1098": D24, "4585": D22, "99ac": D22, "8ad5": D22}
COIN_COL = {"btc": "wbtc", "eth": "weth", "5050": "wbtc"}
TOKEN_NAME = {"wbtc": "WBTC", "weth": "WETH", "cbbtc": "cbBTC", "wsteth": "wstETH", "usd": "USDC"}


# ---------------------------------------------------------------- prices and benchmarks

def usd_prices() -> pd.DataFrame:
    btc = g.hourly_close("99ac").ffill()
    df = pd.DataFrame({"wbtc": btc, "weth": g.hourly_close("88e6").ffill().reindex(btc.index).ffill()})
    for col, pool, ref in (("cbbtc", "e8f7", "wbtc"), ("wsteth", "1098", "weth")):
        ratio = g.hourly_close(pool).reindex(df.index).ffill().bfill()  # before the pool's first trade: its first ratio
        df[col] = ratio * df[ref]
    df["usd"] = 1.0
    return df.loc[:END]


def nav0(usd: pd.Series) -> pd.Series:
    """The book with its $100k one hour before the first bar, so returns include the entry."""
    return pd.concat([pd.Series([float(g.USD)], index=[usd.index[0] - pd.Timedelta(hours=1)]), usd])


def hodl(px: pd.DataFrame, coin: str, start, end) -> pd.Series:
    p = px.loc[pd.Timestamp(start) - pd.Timedelta(hours=1):end]
    if coin == "5050":
        return g.USD * 0.5 * (p["wbtc"] / p["wbtc"].iloc[0] + p["weth"] / p["weth"].iloc[0])
    c = COIN_COL[coin]
    return g.USD * p[c] / p[c].iloc[0]


def rebalanced(px: pd.DataFrame, pair: tuple, bps: float, start, end) -> pd.Series:
    """50/50 of the pool's two tokens, back to half each at every 00:00 bar; bps on the traded USD plus one swap's gas."""
    sl = px.loc[pd.Timestamp(start) - pd.Timedelta(hours=1):end]
    p, idx = sl[list(pair)].to_numpy(), sl.index
    eth_px = eth_daily().reindex(idx.normalize(), method="ffill").to_numpy()
    gwei = np.array([g.GAS_GWEI.get(y, g.GAS_GWEI[2025]) for y in idx.year], dtype=float)
    swap_gas = g.GAS_UNITS["SwapAction"] * gwei * 1e-9 * eth_px
    units = 0.5 * g.USD / p[0]
    out = np.empty(len(idx))
    out[0] = g.USD
    for i in range(1, len(idx)):
        tot = float((units * p[i]).sum())
        if idx[i].hour == 0:
            traded = abs(units[0] * p[i][0] - tot / 2)
            tot -= traded * bps * 1e-4 + (swap_gas[i] if traded > 0 else 0.0)
            units = 0.5 * tot / p[i]
        out[i] = tot
    return pd.Series(out, index=idx)


# ---------------------------------------------------------------- books

def read_book(opt, pool, names, start, end):
    parts = [pd.read_parquet(f"{R}/nav/{opt}_{pool}_{v}_continuous_{start}.parquet").loc[:end] for v in names]
    usd = pd.concat([p["usd"] for p in parts], axis=1).ffill().sum(axis=1)
    return usd, parts


def events(opt, pool, v, start, end):
    ev = pd.read_csv(f"{R}/nav/events_{opt}_{pool}_{v}_continuous_{start}.csv")
    return ev[pd.to_datetime(ev["t"]) <= end].reset_index(drop=True)


def ensure_fixed():
    for pk, start in FIXED.items():
        if not os.path.exists(f"{R}/nav/FIX_{pk}_w20_continuous_{start}.parquet"):
            row = g.task(g.gcfg("FIX", pk, "w20", "99ac:all:0", width=0.20, on="range"), start, g.LAST_DAY, "continuous")
            print("fixed LP", pk, {k: row.get(k) for k in ("net", "maxDD", "recentres", "secs")}, flush=True)


def q_usd(pool: str, index) -> np.ndarray:
    q = g.quote_usd(g.batch.POOLS[pool].quote)
    return np.ones(len(index)) if q is None else q.reindex(index, method="ffill").to_numpy()


def lp_parts(part: pd.DataFrame, ev: pd.DataFrame, modes: dict, pool: str) -> dict:
    """Fees, IL, LVR in USD and in-range hours of one slice, from the rebuilt positions."""
    q = q_usd(pool, part.index)
    nav = part["usd"].to_numpy() / q
    price = part["price"].astype(float).ffill().to_numpy()
    segs = segments(part.index, nav, price, ev, modes)
    _, fe, _, _, _ = decompose(nav, price, segs)
    pos = np.array([s[0] for s in segs])
    n = len(nav)
    prev = np.concatenate([[-1], (np.searchsorted(pos, np.arange(n), side="right") - 1)[:-1]])
    il, lvr = np.zeros(n), np.zeros(n)
    deployed = inside = 0
    for s, (_, mode, p0, scale, _) in enumerate(segs):
        if mode[0] != "range":
            continue
        idx = np.nonzero(prev == s)[0]
        idx = idx[idx > 0]
        if not len(idx):
            continue
        pa, pb = p0 / mode[1], p0 * mode[2]
        p1, pp = price[idx], price[idx - 1]
        x0 = scale * (1 / np.sqrt(p0) - 1 / np.sqrt(pb))  # base units at the placement
        il[idx] = scale * (vnorm(p1, p0, mode[1], mode[2]) - vnorm(pp, p0, mode[1], mode[2])) - x0 * (p1 - pp)
        lvr[idx] = np.where((pp >= pa) & (pp <= pb), scale * (p1 - pp) ** 2 / (4 * pp ** 1.5), 0.0)
        deployed += len(idx)
        inside += int(((p1 >= pa) & (p1 <= pb)).sum())
    return {"fees": float((fe * q).sum()), "il": float((il * q).sum()), "lvr": float((lvr * q).sum()),
            "deployed": deployed, "inside": inside, "hours": n}


def lp_metrics(lp: list[dict]) -> dict:
    fees, il, lvr = (sum(x[k] for x in lp) for k in ("fees", "il", "lvr"))
    return {"fee_income": fees / g.USD, "il": il / g.USD, "lvr": lvr / g.USD, "fee_lvr": fees / lvr if lvr > 0 else None,
            "in_range": sum(x["inside"] for x in lp) / max(sum(x["deployed"] for x in lp), 1),
            "deployed": sum(x["deployed"] for x in lp) / sum(x["hours"] for x in lp)}


# ---------------------------------------------------------------- metrics

def daily(nav: pd.Series) -> pd.Series:
    return nav.resample("1D").last().dropna()


def risk(nav: pd.Series) -> dict:
    """nav includes the $100k start one hour before the first bar."""
    years = (nav.index[-1] - nav.index[0]).total_seconds() / 86400 / 365.25
    total = float(nav.iloc[-1] / nav.iloc[0] - 1)
    cagr = float((1 + total) ** (1 / years) - 1)
    mdd = float((nav / nav.cummax() - 1).min())
    r = daily(nav).pct_change().dropna()
    vol = float(r.std() * np.sqrt(365))
    out = {"total": total, "cagr": cagr, "mdd": mdd, "vol": vol, "calmar": float(cagr / abs(mdd)) if mdd < 0 else None}
    for k, rf in RF.items():
        ex = r - ((1 + rf) ** (1 / 365) - 1)
        dd = float(np.sqrt((np.minimum(ex, 0) ** 2).mean()) * np.sqrt(365))
        out[f"dd_dev{k}"] = dd
        out[f"sharpe{k}"] = float(ex.mean() * 365 / vol)
        out[f"sortino{k}"] = float(ex.mean() * 365 / dd) if dd > 0 else None
    return out


def rolling(nav: pd.Series, ctl: pd.Series | None, days: int = 90) -> dict:
    d = daily(nav)
    r = (d / d.shift(days) - 1).dropna()
    out = {"median": float(r.median()), "worst": float(r.min()), "best": float(r.max()), "pos": float((r > 0).mean()),
           "n": int(len(r))}
    if ctl is not None:
        c = daily(ctl)
        out["beat_ctl"] = float((r > (c / c.shift(days) - 1).reindex(r.index)).mean())
    return out


def regimes(nav: pd.Series, base: pd.Series) -> dict:
    m = nav.resample("ME").last()
    m = (m / m.shift(1) - 1).dropna()
    b = base.resample("ME").last()
    b = (b / b.shift(1) - 1).reindex(m.index)
    label = np.where(b > 0.10, "bull", np.where(b < -0.10, "bear", "flat"))
    return {k: {"mean": float(m[label == k].mean()), "months": int((label == k).sum())}
            for k in ("bull", "bear", "flat") if (label == k).any()}


def row_costs(opt, pool, names, start) -> dict:
    try:
        rs = [json.load(open(f"{R}/rows/{opt}_{pool}_{v}_continuous_{start}.json")) for v in names]
    except FileNotFoundError:
        return {}
    return {k: float(np.mean([r[k] for r in rs])) for k in ("gas", "impact", "swap_fee")}


def counts(evs) -> dict:
    m = s = 0
    for ev in evs:
        later = ev.index > ev.index[0]  # the first row is the placement at the start, not a switch
        m += int((ev["kind"] == "recentre").sum())
        s += int((ev["kind"].isin(["on", "off"]) & later).sum())
    return {"moves": m, "switches": s}


def full(label: str, nav: pd.Series, ctl: pd.Series | None, px: pd.DataFrame, coin: str, extra: dict) -> dict:
    """nav with its start bar; ctl the same for the control."""
    out = {"label": label, "from": str(nav.index[1]), "to": str(nav.index[-1]), **risk(nav)}
    h = risk(hodl(px, coin, nav.index[1], nav.index[-1]))
    out["excess_hodl"], out["excess_hodl_cagr"] = out["total"] - h["total"], out["cagr"] - h["cagr"]
    out["roll90"] = rolling(nav, ctl)
    out["regimes"] = regimes(nav, px[COIN_COL[coin]].loc[nav.index[0]:nav.index[-1]])
    out.update(extra)
    return out


def main():
    ensure_fixed()
    px = usd_prices()
    out = {"series": {}, "bench": {}, "notes": __doc__}
    navs = {}
    for key, (label, opt, pool, names, start, end, modes, ctl, fam) in SERIES.items():
        usd, parts = read_book(opt, pool, names, start, end)
        navs[key] = nav0(usd)
        evs = [events(opt, pool, v, start, end) for v in names]
        extra = {"family": fam, "control": ctl, **counts(evs)}
        if end == END:
            extra.update(row_costs(opt, pool, names, start))
        if modes:
            extra.update(lp_metrics([lp_parts(p, e, modes, pool) for p, e in zip(parts, evs)]))
        out["series"][key] = full(label, navs[key], navs.get(ctl), px, FAMILY[fam][0], extra)
        print(key, {k: round(v, 4) for k, v in out["series"][key].items() if isinstance(v, float)}, flush=True)
    for key, (label, parts, ctl) in MIX.items():
        usd = sum(0.5 * pd.read_parquet(f"{R}/nav/{o}_{pk}_{v}_continuous_{D24}.parquet")["usd"] for o, pk, v in parts)
        navs[key] = nav0(usd.ffill().loc[:END])
        out["series"][key] = full(label, navs[key], navs.get(ctl), px, "5050", {"family": "MIX", "control": ctl})
        print(key, {k: round(v, 4) for k, v in out["series"][key].items() if isinstance(v, float)}, flush=True)

    for fam, (coin, pair, bps, fixed_pool, start, end) in FAMILY.items():
        b = {}
        h = hodl(px, coin, start, end)
        b["hodl"] = full({"btc": "持有 BTC", "eth": "持有 ETH", "5050": "持有 BTC/ETH 各半（不動）"}[coin], h, None, px,
                         coin, {})
        if pair:
            name = "／".join(TOKEN_NAME[t] for t in pair)
            b["rebal"] = full(f"50/50 每天再平衡（{name}）", rebalanced(px, pair, bps, start, end), None, px, coin, {})
        if fixed_pool:
            part = pd.read_parquet(f"{R}/nav/FIX_{fixed_pool}_w20_continuous_{FIXED[fixed_pool]}.parquet").loc[:end]
            ev = events("FIX", fixed_pool, "w20", FIXED[fixed_pool], end)
            extra = {**counts([ev]), **lp_metrics([lp_parts(part, ev, {"lp": ["range", 1.20, 1.20]}, fixed_pool)])}
            if end == END:
                extra.update(row_costs("FIX", fixed_pool, ["w20"], FIXED[fixed_pool]))
            b["fixed"] = full(f"固定 ±20% LP（{fixed_pool}，不加濾網）", nav0(part["usd"]), None, px, coin, extra)
        out["bench"][fam] = b
        print(fam, {k: (round(v["total"], 4), round(v["sharpe4"], 2)) for k, v in b.items()}, flush=True)
    with open(f"{R}/metrics.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
