"""
Spot simulator with sleeves, for the yield layer and the per-coin gate basket (reports/next_backtest_plan.md).

A sleeve is one way of holding something: a coin, wstETH instead of ETH, or a coin inside an LP position. Each
sleeve has a USD value index per unit held; whatever the target shares leave over goes to the "cash" sleeve, which
is plain USDC (index 1) or a parking position. Given the ETH and BTC prices, a cash index of 1 and one cost for every
coin, this reproduces spot_robustness.simulate exactly (checked by `python sleeve_sim.py`).

Run from samples/strategy-example:
  PYTHONPATH=../.. python sleeve_sim.py   # check against spot_robustness.simulate on the base rule
"""
from typing import Callable

import pandas as pd

from spot_btc_eth_gate import IN_SAMPLE

INITIAL = 100_000.0
COST_BPS = 10

# gas units per sleeve event on mainnet, built from tri_btc_eth_gate.GAS_UNITS: entering an LP is a swap and an
# add, leaving it a remove, a collect and a swap, a re-centre all four
GAS_EVENT_UNITS = {"enter": 130_000 + 450_000, "exit": 150_000 + 120_000 + 130_000,
                   "recentre": 150_000 + 120_000 + 130_000 + 450_000, "swap": 130_000}


def mainnet_gas(eth_usd: pd.Series, scale: float = 1.0, swap_only: bool = False) -> Callable[[str, pd.Timestamp], float]:
    """
    USD gas of one sleeve event at time t, from the yearly gwei of tri_btc_eth_gate and the ETH price.
    swap_only: the sleeve is a token held on chain (wstETH), so every event is a single swap.
    """
    from tri_btc_eth_gate import GAS_GWEI

    def gas(kind: str, t: pd.Timestamp) -> float:
        gwei = GAS_GWEI.get(t.year, min(GAS_GWEI.values()))
        units = GAS_EVENT_UNITS["swap" if swap_only else kind]
        return scale * units * gwei * 1e-9 * float(eth_usd.asof(t))

    return gas


def simulate(weights: pd.DataFrame, values: pd.DataFrame, start: str = IN_SAMPLE[0], cost_bps: float | dict = COST_BPS,
             cash_cost_bps: float = 0.0, threshold: float | None = None,
             gas: dict[str, Callable[[str, pd.Timestamp], float]] | None = None,
             lp: dict[str, pd.DatetimeIndex] | None = None) -> tuple[pd.Series, int, dict]:
    """
    weights: target value share per sleeve (its columns), from each timestamp on; the rest goes to cash.
    values: hourly USD value of one unit of every sleeve in `weights`, plus a "cash" column.
    cost_bps: one number for every sleeve or {sleeve: bps}, paid on the notional moved into or out of that sleeve.
    cash_cost_bps: paid on the notional moved into or out of cash (a parking LP takes a swap to enter and leave).
    threshold: None trades whenever the target changes; a number trades when any share drifted further than that.
    gas: {sleeve: f(kind, t) -> USD} for the sleeves (cash included) that live on chain; the others pay none.
        Entering or leaving one pays f("enter" / "exit"), resizing it f("recentre").
    lp: {sleeve: the times its LP position was re-centred}; each one pays gas[sleeve]("recentre") while it is held.
    Returns hourly net value, the number of rebalances, and {"swap": USD, "gas": USD} paid.
    """
    v = values.loc[start:]
    w = weights.loc[start:]
    w = w[w.index.isin(v.index)]
    sleeves = list(w.columns)
    cost = {s: (cost_bps[s] if isinstance(cost_bps, dict) else cost_bps) / 10_000 for s in sleeves}
    c_cash = cash_cost_bps / 10_000
    gas, lp = gas or {}, lp or {}
    q = [0.0] * len(sleeves)
    units = INITIAL / float(v["cash"].iloc[0])
    last, trades, swap, gas_paid, rows = None, 0, 0.0, 0.0, []
    for t, want in zip(w.index, w[sleeves].to_numpy()):
        px = [v.at[t, s] for s in sleeves]
        pc = v.at[t, "cash"]
        held = [qi * pi for qi, pi in zip(q, px)]
        value = sum(held) + units * pc
        if threshold is None:
            go = tuple(want) != last
        else:
            go = max(abs(wi - hi / value) for wi, hi in zip(want, held)) > threshold
        if go:
            moved = [abs(wi * value - hi) for wi, hi in zip(want, held)]
            cash_before, cash_after = units * pc, (1 - sum(want)) * value
            fee = sum(m * cost[s] for m, s in zip(moved, sleeves)) + abs(cash_after - cash_before) * c_cash
            spent = 0.0
            for name, before, after in [*zip(sleeves, held, (wi * value for wi in want)), ("cash", cash_before, cash_after)]:
                if name not in gas or abs(after - before) <= 1:
                    continue
                kind = "enter" if before <= 1 else "exit" if after <= 1 else "recentre"  # resizing = remove + add
                spent += gas[name](kind, t)
            value -= fee + spent
            q = [wi * value / pi for wi, pi in zip(want, px)]
            units = value * (1 - sum(want)) / pc
            last, trades = tuple(want), trades + (sum(moved) > 1)
            swap, gas_paid = swap + fee, gas_paid + spent
        rows.append((t, *q, units))
    held = pd.DataFrame(rows, columns=["t", *sleeves, "cash"]).set_index("t")
    held = held.reindex(v.index, method="ffill").fillna({**{s: 0.0 for s in sleeves}, "cash": INITIAL})
    nav = sum(held[s] * v[s] for s in sleeves) + held["cash"] * v["cash"]
    if lp:
        # re-centres inside an LP sleeve, paid out of the net value while the sleeve is held
        spent = pd.Series(0.0, index=v.index)
        for name, events in lp.items():
            if name not in gas:
                continue
            for t in events[(events >= v.index[0]) & (events <= v.index[-1])]:
                if held[name].asof(t) * v[name].asof(t) > 1:
                    spent.loc[spent.index.asof(t)] += gas[name]("recentre", t)
        gas_paid += float(spent.sum())
        nav = nav - spent.cumsum()
    return nav, trades, {"swap": swap, "gas": gas_paid}


def _check():
    """The base rule through both simulators must give the same net value and trade count."""
    import spot_robustness as sr
    from spot_btc_eth_gate import load_prices

    prices, _, _ = load_prices()
    w = sr.gate(prices)
    old, old_trades = sr.simulate(w, prices)
    new, new_trades, paid = simulate(w, prices.assign(cash=1.0))
    gap = float((new / old - 1).abs().max())
    s = sr.summary("base", new, new_trades)
    print(f"base via sleeve_sim: total {s['total']:+.1%}, maxDD {s['maxDD']:+.1%}, trades {new_trades}, "
          f"swap ${paid['swap']:,.0f}; max gap to spot_robustness {gap:.2e}, trades there {old_trades}")
    assert gap < 1e-9 and new_trades == old_trades, "sleeve_sim does not reproduce spot_robustness.simulate"
    # a cash index growing 3% a year must match spot_robustness' cash_yield
    t0 = prices.loc[IN_SAMPLE[0]:].index[0]
    grown = prices.assign(cash=1.03 ** ((prices.index - t0).total_seconds() / (365.25 * 86400)))
    old_y, _ = sr.simulate(w, prices, cash_yield=0.03)
    new_y, _, _ = simulate(w, grown)
    gap_y = float((new_y / old_y - 1).abs().max())
    print(f"3% cash yield: max gap {gap_y:.2e}")
    assert gap_y < 1e-9, "cash index does not match cash_yield"
    print("SLEEVE_CHECK_OK")


if __name__ == "__main__":
    _check()
