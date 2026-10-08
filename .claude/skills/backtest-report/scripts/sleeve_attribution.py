"""
Calendar-year return, max drawdown and P&L attribution for the multi-pool spot gate and anything else built on
samples/strategy-example/sleeve_sim.py. Import it from a driver that sits in samples/strategy-example (it needs the
repo's modules on the path, like every backtest there):

    import sys; sys.path.insert(0, "../../.claude/skills/backtest-report/scripts")
    from sleeve_attribution import attribute, hold_bench

A sleeve's unit value is price x index (index: a wstETH ratio, an LP index, a parking index; 1 when there is none),
and the run is sleeve_sim.simulate with the holdings recorded, so each hour's NAV change splits exactly into
  units(t-1) x index(t-1) x (price(t) - price(t-1))      <sleeve>:price   the coin's move
  units(t-1) x price(t) x (index(t) - index(t-1))        <sleeve>:index   the yield layer
minus the swap cost and gas paid at trades and the gas of LP re-centres. 'other' (return minus the rest) is ~0;
anything bigger means the driver's values frame and parts disagree.

One continuous run (no restart each year); a year's return is its last NAV over the NAV just before it starts.

Example driver (the multi-pool report of 2026-10-08):

    prices, _, _ = load_prices()
    PX = {"eth": prices["eth"], "btc": prices["btc"]}
    IX = {"ratio": wsteth_ratio(prices.index, "causal").bfill(), "park": index_on(park["nav"], prices.index, FULL[0])}
    C = pd.DataFrame({"eth": PX["eth"] * IX["ratio"], "btc": PX["btc"], "cash": IX["park"]})
    out = attribute(cm.changes(gate(1)), C, {"eth": ("eth", "ratio"), "btc": ("btc", None), "cash": (None, "park")},
                    PX, IX, cost_bps={"eth": 11, "btc": 10}, cash_cost_bps=0.5,
                    carve=[("depeg", "park", "2023-03-10", "2023-04-01")],
                    names={"btc:price": "btc", "eth:price": "eth", "eth:index": "wsteth", "cash:index": "park"})

carve takes a window out of one index's component into its own key (the March 2023 USDC depeg in the parking
index, reports/btc_eth_tri_pool_research.md 7.4), so an artefact shows apart instead of inside the yield.
"""
import numpy as np
import pandas as pd

INITIAL = 100_000.0


def simulate_rec(weights, values, start, end, cost_bps, cash_cost_bps=0.0, gas=None, lp=None):
    """sleeve_sim.simulate (no threshold, resize="split") that also returns the units held and the costs per hour."""
    v = values.loc[start:end]
    w = weights.loc[start:end]
    w = w[w.index.isin(v.index)]
    sleeves = list(w.columns)
    cost = {s: (cost_bps[s] if isinstance(cost_bps, dict) else cost_bps) / 10_000 for s in sleeves}
    c_cash = cash_cost_bps / 10_000
    gas, lp = gas or {}, lp or {}
    q = [0.0] * len(sleeves)
    units = INITIAL / float(v["cash"].iloc[0])
    last, rows, fees, trade_gas = None, [], {}, {}
    for t, want in zip(w.index, w[sleeves].to_numpy()):
        if tuple(want) == last:
            continue
        px = [v.at[t, s] for s in sleeves]
        pc = v.at[t, "cash"]
        held = [qi * pi for qi, pi in zip(q, px)]
        value = sum(held) + units * pc
        moved = [abs(wi * value - hi) for wi, hi in zip(want, held)]
        cash_before, cash_after = units * pc, (1 - sum(want)) * value
        fee = sum(m * cost[s] for m, s in zip(moved, sleeves)) + abs(cash_after - cash_before) * c_cash
        spent = 0.0
        for name, before, after in [*zip(sleeves, held, (wi * value for wi in want)), ("cash", cash_before, cash_after)]:
            if name not in gas or abs(after - before) <= 1:
                continue
            if before <= 1 or after <= 1:
                kind = "enter" if before <= 1 else "exit"
            else:
                kind = "grow" if after > before else "shrink"
            spent += gas[name](kind, t)
        value -= fee + spent
        q = [wi * value / pi for wi, pi in zip(want, px)]
        units = value * (1 - sum(want)) / pc
        last = tuple(want)
        fees[t], trade_gas[t] = fee, spent
        rows.append((t, *q, units))
    held = pd.DataFrame(rows, columns=["t", *sleeves, "cash"]).set_index("t")
    held = held.reindex(v.index, method="ffill").fillna({**{s: 0.0 for s in sleeves}, "cash": INITIAL})
    fee_s = pd.Series(fees, dtype=float).reindex(v.index, fill_value=0.0)
    gas_s = pd.Series(trade_gas, dtype=float).reindex(v.index, fill_value=0.0)
    lp_gas = pd.Series(0.0, index=v.index)
    for name, events in lp.items():
        if name not in gas:
            continue
        for t in events[(events >= v.index[0]) & (events <= v.index[-1])]:
            if held[name].asof(t) * v[name].asof(t) > 1:
                lp_gas.loc[lp_gas.index.asof(t)] += gas[name]("recentre", t)
    nav = sum(held[s] * v[s] for s in [*sleeves, "cash"]) - lp_gas.cumsum()
    return nav, held, fee_s, gas_s + lp_gas, v


def attribute(weights, values, parts, PX, IX, years=("2022", "2023", "2024", "2025", "2026"),
              start="2022-01-01", end="2026-09-30 23:00", carve=(), names=None, **kw):
    """
    weights: target share per sleeve (sleeve_sim convention; cost_matrix.changes() keeps it short).
    values: unit value per sleeve plus "cash", hourly; values[s] must equal PX[price key] x IX[index key].
    parts: {sleeve: (price key or None, index key or None)}, "cash" included when it has an index.
    carve: [(name, index key, from, to)]: that index's component inside [from, to) goes to `name` instead.
    names: {"<sleeve>:price" | "<sleeve>:index": component name} for the output keys.
    kw: cost_bps, cash_cost_bps, gas, lp as in sleeve_sim.simulate.
    Returns {"years": {y: {ret, mdd}}, "attr": {y: {component: fraction}}, "info": {y: {...}}}.
    """
    nav, held, fee_s, gas_s, v = simulate_rec(weights, values, start, end, **kw)
    prev = held.shift(1).fillna(0.0)  # units held over each hour; nothing before the first bar
    contrib, index_of = {}, {}
    for s, (pk, ik) in parts.items():
        P = PX[pk].reindex(nav.index) if pk else None
        I = IX[ik].reindex(nav.index) if ik else None
        if P is not None:
            contrib[f"{s}:price"] = (prev[s] * (I.shift(1) if I is not None else 1.0) * P.diff()).fillna(0.0)
        if I is not None:
            contrib[f"{s}:index"] = (prev[s] * (P if P is not None else 1.0) * I.diff()).fillna(0.0)
            index_of[f"{s}:index"] = ik
    names = names or {}
    idle_cols = [c for c in held.columns if c == "cash" or (c in parts and parts[c][0] is None)]
    out = {"years": {}, "attr": {}, "info": {}}
    for y in years:
        idx = np.nonzero((nav.index >= f"{y}-01-01") & (nav.index < f"{int(y) + 1}-01-01"))[0]
        if not len(idx):
            continue
        base = float(nav.iloc[idx[0] - 1]) if idx[0] > 0 else INITIAL
        path = np.concatenate([[base], nav.iloc[idx].to_numpy()])
        ret = float(path[-1] / base - 1)
        out["years"][y] = {"ret": ret, "mdd": float((path / np.maximum.accumulate(path) - 1).min())}
        a = {}
        for k, c in contrib.items():
            part = c.iloc[idx]
            for cname, ikey, lo, hi in carve:
                if index_of.get(k) == ikey:
                    inside = (part.index >= lo) & (part.index < hi)
                    a[cname] = a.get(cname, 0.0) + float(part[inside].sum()) / base
                    part = part[~inside]
            key = names.get(k, k)
            a[key] = a.get(key, 0.0) + float(part.sum()) / base
        a["swap"] = -float(fee_s.iloc[idx].sum()) / base
        a["gas"] = -float(gas_s.iloc[idx].sum()) / base
        a["other"] = ret - sum(a.values())
        out["attr"][y] = a
        idle = sum(held[c].iloc[idx] * v[c].iloc[idx] for c in idle_cols)
        out["info"][y] = {"持倉時間比例": f"{float((1 - idle / nav.iloc[idx]).mean()):.0%}",
                          "交易次數": int((fee_s.iloc[idx] > 0).sum())}
    return out


def hold_bench(prices, years=("2022", "2023", "2024", "2025", "2026"), start="2022-01-01", weights=None):
    """Buy-and-hold controls, cut into calendar years. Returns {y: {name: {ret, mdd}}} with
      <column>        each coin alone, bought at `start` and never touched
      basket_yearly   the weighted basket, put back to its weights every Jan 1: the fair yardstick for one year's
                      price P&L (the timing effect), but its compounded return is NOT buy-and-hold
      basket_hold     the weighted basket bought at `start` and never rebalanced: what "50/50 持有" means to a
                      reader, so label and compound this one in the yearly tables
    Default weights: equal over prices' columns."""
    weights = weights or {c: 1 / len(prices.columns) for c in prices.columns}
    dd = lambda x: float((x / x.cummax() - 1).min())
    whole = prices.loc[start:]
    whole = whole / whole.iloc[0]
    held = sum(w * whole[c] for c, w in weights.items())
    out = {}
    for y in years:
        lo = f"{int(y) - 1}-12-31 23:00" if int(y) > int(start[:4]) else start
        p = prices.loc[lo:f"{y}-12-31 23:00"]
        p = p / p.iloc[0]
        yearly = sum(w * p[c] for c, w in weights.items())
        h = held.loc[lo:f"{y}-12-31 23:00"]
        h = h / h.iloc[0]
        out[y] = {**{c: {"ret": float(p[c].iloc[-1] - 1), "mdd": dd(p[c])} for c in prices.columns},
                  "basket_yearly": {"ret": float(yearly.iloc[-1] - 1), "mdd": dd(yearly)},
                  "basket_hold": {"ret": float(h.iloc[-1] - 1), "mdd": dd(h)}}
    return out
