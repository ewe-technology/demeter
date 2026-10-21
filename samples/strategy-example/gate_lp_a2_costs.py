"""
A2's costs by year (reports/plan_2026-10-19_gate_lp_options.md, after the fact, listed only): the three A2 books
(control holding WETH, holding wstETH, the wstETH/WETH LP up-skew) rerun from 2024-01-01 exactly as
gate_lp_options.run does, but keeping every cost with its time, so the PnL page and deck can show costs as their own
block instead of netted inside the three differences.

Two kinds of cost, both in USD:
- pool: inside the Demeter book (quote WETH): gas and the price impact charged per action, plus the pool fee of each
  swap (already inside Demeter's NAV; recorded here to show it).
- conv: converting between the quote token and USDC at each gate switch (gate_lp_options.to_usd): the spot bps and
  one swap's gas.

Each run is checked against the continuous NAV already on disk (the same run, same code).

Run from samples/strategy-example on the strategy host:
  PYTHONPATH=../.. python gate_lp_a2_costs.py      # writes result/gate-lp-options/a2_costs.json
"""
import json
import math
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

import gate_lp_options as g

R = g.RESULT_DIR
START = date(2024, 1, 1)
YEARS = ["2024", "2025", "2026"]
BOOKS = {"ctl": "ctl", "wst": "hold_wsteth", "lp": "up_02_08"}


def to_usd_costs(net_q, on, q_usd, asset, eth, initial):
    """gate_lp_options.to_usd, also returning each bar's conversion cost in USD."""
    idx = net_q.index
    q = q_usd.reindex(idx, method="ffill").to_numpy()
    eth_px = eth.reindex(idx.normalize(), method="ffill").to_numpy()
    gw = np.array([g.GAS_GWEI.get(y, g.GAS_GWEI[2025]) for y in idx.year], dtype=float)
    swap_gas = g.GAS_UNITS["SwapAction"] * gw * 1e-9 * eth_px
    nq, st = net_q.to_numpy(), on.to_numpy()
    out, cost = np.empty(len(nq)), np.zeros(len(nq))
    usd_prev, nq_prev, was_on, scale = float(initial * q[0]), float(initial), False, 1.0
    bps = g.SPOT_BPS[asset] * 1e-4
    for i in range(len(nq)):
        if st[i]:
            if not was_on:
                scale = (usd_prev * (1 - bps) - swap_gas[i]) / (q[i] * nq_prev)
                cost[i] = usd_prev * bps + swap_gas[i]
            out[i] = nq[i] * q[i] * scale
        elif was_on:
            gross = nq[i] * q[i] * scale
            out[i] = gross * (1 - bps) - swap_gas[i]
            cost[i] = gross * bps + swap_gas[i]
        else:
            out[i] = usd_prev * (nq[i] / nq_prev if nq_prev else 1.0)
        usd_prev, nq_prev, was_on = out[i], nq[i], bool(st[i])
    return pd.Series(out, index=idx), pd.Series(cost, index=idx)


def run_costs(c, start, end):
    """gate_lp_options.run for one A2 book, keeping per-action costs (quote token) and conversion costs (USD)."""
    p = g.batch.POOLS[c.pool_key]
    base = p.token1 if p.quote == p.token0 else p.token0
    q_usd = g.quote_usd(p.quote)
    data = g.hourly_market(c.pool_key, start, end)
    price = data["price"].astype(float)
    initial = c.initial / float(q_usd.asof(price.index[0]))
    market = g.UniLpMarket(g.KEY, c.pool())
    market.data = data
    actuator = g.Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(p.quote, Decimal(initial))
    actuator.set_price(pd.DataFrame({base.name: price, p.quote.name: 1.0}, index=price.index), p.quote)
    strategy = g.robust.RobustGated(c, g.gate_series(c.gate_spec, c.gate_hour))
    actuator.strategy = strategy
    actuator.run(print_result=False)
    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    eth = g.eth_daily()
    liq = data["currentLiquidity"].astype(float)
    quote_is_1, scale = g.batch.raw_price_scale(p)
    rows, charged = [], {}
    for a in actuator.actions:
        ts = pd.Timestamp(a.timestamp)
        name = type(a).__name__
        gas = g.gas_quote(ts, name, p, eth, q_usd, None)
        impact = fee = 0.0
        if name == "SwapAction":
            px = float(price.asof(ts))
            notional = float(a.amount) * (px if a.amount.unit.upper() == base.name.upper() else 1.0)
            fee = float(a.fee) * (px if a.fee.unit.upper() == base.name.upper() else 1.0)
            p_raw = (px if quote_is_1 else 1 / px) / scale
            raw1 = notional * (1.0 if quote_is_1 else 1 / px) * 10 ** p.token1.decimal
            impact = notional * raw1 / (float(liq.asof(ts)) * math.sqrt(p_raw))
        rows.append((ts, gas, impact, fee))
        charged[ts] = charged.get(ts, 0.0) + gas + impact
    paid = pd.Series(charged, dtype=float).sort_index().cumsum()
    net_q = nav - (paid.reindex(nav.index, method="ffill").fillna(0.0) if len(paid) else 0.0)
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    usd, conv = to_usd_costs(net_q, g.on_state(ev, net_q.index), q_usd, "eth", eth, initial)
    acts = pd.DataFrame(rows, columns=["t", "gas", "impact", "fee"]).set_index("t")
    acts.index = pd.DatetimeIndex(acts.index)  # empty for the control, which never acts in the pool
    q = q_usd.ffill()
    acts = acts.mul(q.reindex(acts.index, method="ffill").to_numpy(), axis=0)  # quote token -> USD
    return usd, conv, acts


def main():
    with open(f"{R}/h46_choice.json") as f:
        choice = json.load(f)
    cfgs = {c.name: c for c in g.h48_configs(choice["btc"], choice["eth"]) if c.option == "A2" and c.pool_key == "1098"}
    out = {}
    for key, v in BOOKS.items():
        usd, conv, acts = run_costs(cfgs[v], START, g.LAST_DAY)
        saved = pd.read_parquet(f"{R}/nav/A2_1098_{v}_continuous_{START}.parquet")["usd"]
        diff = float((usd.reindex(saved.index) - saved).abs().max())
        print(key, "max diff vs saved NAV", diff, flush=True)
        assert diff < 1e-6 * float(saved.abs().max()), key
        nav0 = pd.concat([pd.Series([float(g.USD)], index=[usd.index[0] - pd.Timedelta(hours=1)]), usd])
        res = {}
        for y in YEARS:
            before = nav0[nav0.index < pd.Timestamp(f"{y}-01-01")]
            start_nav = float(before.iloc[-1]) if len(before) else float(g.USD)
            end_nav = float(usd[usd.index.year == int(y)].iloc[-1])
            a = acts[acts.index.year == int(y)]
            res[y] = {"start": start_nav, "ret": end_nav / start_nav - 1,
                      "gas": float(a["gas"].sum()), "impact": float(a["impact"].sum()), "fee": float(a["fee"].sum()),
                      "conv": float(conv[conv.index.year == int(y)].sum())}
        out[key] = res
        print(key, {y: {k: round(x, 2) for k, x in r.items()} for y, r in res.items()}, flush=True)
    with open(f"{R}/a2_costs.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
