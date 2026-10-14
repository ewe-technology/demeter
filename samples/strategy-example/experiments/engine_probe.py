"""
Engine probe for engine_check.py: drives the demeter engine that this python imports (python demeter/ or the Rust
package) through every market operation on real pool minutes, and writes every value it sees as the full `str()` of
the Decimal, one line per value. Two engines are equal when the two traces are equal byte for byte; a last-digit
difference anywhere shows up here even when a backtest's rounded CSVs hide it.

    python experiments/engine_probe.py <out.txt>      # cwd: a folder inside samples/ (pool data paths are ../)

Operations: add_liquidity_by_tick (around the price, ending exactly at the current tick, below it),
add_liquidity (by price), add_liquidity_by_value, collect_fee, partial and full remove_liquidity, buy, sell, swap,
even_rebalance; every minute the account net value; every 30 minutes market balance, position status and balances.
"""
import sys
from datetime import date, timedelta
from decimal import Decimal

import demeter
from demeter import Actuator, ChainType, MarketInfo, Snapshot, Strategy, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool

# pool -> (token0, token1, quote index, fee %, data dir, first day): both quote sides, 6/8/18 decimals, a non-USD pair
POOLS = {
    "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": (("usdc", 6), ("eth", 18), 0, 0.05, "../real-data", date(2022, 6, 13)),
    "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": (("wbtc", 8), ("usdc", 6), 1, 0.3, "../holdout-data", date(2021, 11, 3)),
    "0x4585fe77225b41b697c938b018e2ac67ac5a20c0": (("wbtc", 8), ("eth", 18), 1, 0.05, "../holdout-data", date(2022, 5, 9)),
}
DAYS = 2


def run(pool: str, out):
    (n0, d0), (n1, d1), qi, fee, path, day = POOLS[pool]
    t0, t1 = TokenInfo(name=n0, decimal=d0), TokenInfo(name=n1, decimal=d1)
    quote = t0 if qi == 0 else t1
    base = t1 if qi == 0 else t0
    market = UniLpMarket(MarketInfo("lp"), UniV3Pool(t0, t1, fee, quote))
    market.data_path = f"{path}/{pool}"
    market.load_data(ChainType.ethereum.name, pool, day, day + timedelta(days=DAYS - 1))
    spacing = int(fee * 200)
    keys = {}

    def w(*parts):
        out.write(" ".join(str(p) for p in parts) + "\n")

    def step(name, fn):
        try:
            r = fn()
        except Exception as e:  # both engines must fail the same way
            w(name, "raised", type(e).__name__)
            return None
        w(name, *(r if isinstance(r, tuple) else (r,)))
        return r

    class Probe(Strategy):
        def on_bar(self, s: Snapshot):
            i = s.timestamp.hour * 60 + s.timestamp.minute + 1440 * (s.timestamp.date() - day).days
            st = market.market_status.data
            tick = int(st.closeTick)
            at = (tick // spacing) * spacing
            price = st.price
            if i == 0:
                # each add names its own amounts (fractions of the capital), so none drains a balance
                b, q = lambda f: Decimal(f) * self.cap, lambda f: Decimal(f) * self.cap * price
                r = step("add_around", lambda: market.add_liquidity_by_tick(at - 20 * spacing, at + 20 * spacing,
                                                                             b("0.3"), q("0.3"), tick=tick))
                keys["around"] = r and r[0]
                r = step("add_to_tick", lambda: market.add_liquidity_by_tick(at - 30 * spacing, at, b("0.2"), q("0.2"),
                                                                              tick=tick))
                keys["to_tick"] = r and r[0]
                r = step("add_below", lambda: market.add_liquidity_by_tick(at - 80 * spacing, at - 40 * spacing,
                                                                            b("0.15"), q("0.15"), tick=tick))
                keys["below"] = r and r[0]
                r = step("add_by_price", lambda: market.add_liquidity(price * Decimal("0.9"), price * Decimal("1.07"),
                                                                       q("0.15"), b("0.15")))
                keys["by_price"] = r and r[0]
                r = step("add_by_value", lambda: market.add_liquidity_by_value(at - 10 * spacing, at + 50 * spacing,
                                                                                q("0.15")))
                keys["by_value"] = r and r[0]
            elif i == 240 and keys.get("around"):
                step("collect", lambda: market.collect_fee(keys["around"]))
            elif i == 300 and keys.get("to_tick"):
                liq = market.positions[keys["to_tick"]].liquidity
                step("remove_part", lambda: market.remove_liquidity(keys["to_tick"], liq // 3))
            elif i == 400:
                step("buy", lambda: market.buy(Decimal("0.013") * self.cap))
                step("sell", lambda: market.sell(Decimal("0.007") * self.cap))
            elif i == 500:
                step("swap", lambda: market.swap(Decimal("0.05") * self.cap * price, quote, base))
            elif i == 600:
                step("even_rebalance", lambda: market.even_rebalance())
            elif i == 700:
                v = Decimal("0.1") * self.cap * price
                for k in ("around", "below", "by_value"):
                    if keys.get(k):
                        step(f"estimate_liquidity_{k}", lambda k=k: market.estimate_liquidity(v, keys[k]))
                step("estimate_amount", lambda: market.estimate_amount(v, at - 15 * spacing, at + 25 * spacing))
                step("price_to_tick", lambda: market.price_to_tick(price * Decimal("1.0137")))
                step("tick_to_price", lambda: market.tick_to_price(at + 7 * spacing))
            elif i == 900 and keys.get("by_price"):
                step("remove_all", lambda: market.remove_liquidity(keys["by_price"]))
            elif i == 1500:
                for k, v in list(keys.items()):
                    if v and v in market.positions:
                        step(f"close_{k}", lambda v=v: market.remove_liquidity(v))

        def after_bar(self, s: Snapshot):
            a = self.broker.get_account_status(s.prices, s.timestamp)
            w("net", s.timestamp, a.net_value)
            if s.timestamp.minute % 30 == 0:
                b = market.get_market_balance()
                w("market", *(Decimal(x) for x in (b.net_value, b.base_uncollected, b.quote_uncollected,
                                                   b.base_in_position, b.quote_in_position, b.liquidity_value)))
                w("balances", self.broker.get_token_balance(base), self.broker.get_token_balance(quote))
                for k, v in keys.items():
                    if v and v in market.positions:
                        p = market.get_position_status(v)
                        w("position", k, p.liquidity, p.amount0, p.amount1, p.value, p.pending_amount0, p.pending_amount1)

    act = Actuator()
    act.broker.add_market(market)
    first_price = Decimal(str(market.data.price.iloc[0]))
    probe = Probe()
    probe.cap = Decimal(3)   # capital: 3 base tokens and their value in quote
    act.broker.set_balance(base, probe.cap)
    act.broker.set_balance(quote, probe.cap * first_price)
    act.strategy = probe
    act.set_price(market.get_price_from_data())
    act.print_action = False
    act.run(print_result=False)
    # the frame a strategy reads in finalize(): every 60th row, every column. Values are compared as
    # numbers (normalize()): the Rust bridge ships whole Decimal columns at one scale, so a cell can
    # print trailing zeros python's own frame does not have (same value; see rust/README.md)
    df = act.account_status_df
    out.write("account_status_df " + " ".join("|".join(map(str, c)) if isinstance(c, tuple) else str(c)
                                              for c in df.columns) + "\n")
    for ts, row in df.iloc[::60].iterrows():
        out.write(f"row {ts} " + " ".join(str(v.normalize() if isinstance(v, Decimal) else v) for v in row.tolist())
                  + "\n")


def main():
    with open(sys.argv[1], "w") as out:
        for pool in POOLS:
            out.write(f"== {pool}\n")
            run(pool, out)
    print(f"engine_probe: {'rust' if hasattr(demeter, '_rs') else 'python'} engine -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
