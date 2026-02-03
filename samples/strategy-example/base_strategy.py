from decimal import Decimal

from demeter import (
    Strategy,
    Snapshot,
)
from demeter.uniswap import UniLpMarket
from math_const import ZERO
from rm_types import TestParams, GlobalParams
from remix_dao_utils import RemixDaoUtils, near_zero

class BaseRemixDaoStrategy(Strategy):

    def __init__(self, _utils: RemixDaoUtils, _params: TestParams, _gp: GlobalParams):
        super().__init__()
        self.utils = _utils
        self.params = _params
        self.gp = _gp
        self.was_in_range = False
        self.last_rescale_tick = 0
        self.total_base_fee = ZERO
        self.total_quote_fee = ZERO
        self.export_actions = []
        self.lock_until_time = None
        self.balance_data = {}

    def is_quote_zero(self, amount: Decimal):
        return near_zero(amount, self.gp.quote_token.decimal)

    def is_base_zero(self, amount: Decimal):
        return near_zero(amount, self.gp.base_token.decimal)

    def round_to_tick_space(self, lower: int, upper: int) -> tuple[int, int]:
        tick_space = self.utils.params.tick_spacing
        return self.utils.ceiling_tick(lower, tick_space), self.utils.floor_tick(upper, tick_space)

    def is_in_lock(self, row_data: Snapshot) -> bool:
        return self.lock_until_time is not None and row_data.timestamp <= self.lock_until_time

    @staticmethod
    def calculate_quantity(price: Decimal, amount_b: Decimal) -> Decimal:
        # Calculate quantity of Token A
        quantity_a = amount_b / price
        return Decimal(quantity_a)

    def even_rebalance(self, lp_market: UniLpMarket, base: Decimal | None = None, quote: Decimal | None = None,
                       price: Decimal | None = None) -> tuple[Decimal, Decimal, Decimal | None, Decimal | None]:
        """
        return: final base, final quote, fee in base token, fee in quote token
        """
        if price is None:
            price = lp_market.market_status.data.price

        if quote is None:
            amount_quote = lp_market.broker.get_token_balance(lp_market.quote_token)
        else:
            amount_quote = quote
        if base is None:
            amount_base = lp_market.broker.get_token_balance(lp_market.base_token)
        else:
            amount_base = base




            """
                    if price is None:
            price = self._market_status.data.price

        amount_quote = self.broker.get_token_balance(self.quote_token)
        amount_base = self.broker.get_token_balance(self.base_token)

        delta_base = (amount_quote / price - amount_base) / (Decimal(2) + self.pool_info.fee_rate)
        if delta_base >= 0:
            self.buy(delta_base)
            return

        delta_quote = (amount_base - amount_quote / price) / (Decimal(2) - self.pool_info.fee_rate)
        if delta_quote >= 0:
            self.sell(delta_quote)
            return
        pass
            """

        delta_base = (amount_quote / price - amount_base) / (Decimal(2) + lp_market.pool_info.fee_rate)
        if delta_base >= 0:
            quote_fee, quote_spent, base_got = lp_market.buy(delta_base)
            # print(f"buy, base_fee: {base_fee}, quote_spent: {quote_spent}, base_got: {base_got}, base: {amount_base}, quote: {amount_quote}")
            f_base, f_quote, b_fee, q_fee = amount_base + base_got, amount_quote - quote_spent, None, quote_fee
            if f_base <= ZERO or f_quote <= ZERO:
                print(
                    f"BAD buy, quote_fee: {quote_fee}, quote_spent: {quote_spent}, base_got: {base_got}, base: {amount_base}, quote: {amount_quote}, f_base: {f_base}, f_quote: {f_quote}")
            self.balance_data = {"amount_base": amount_base, "amount_quote": amount_quote, "quote_fee": quote_fee,
                                 "quote_spent": quote_spent, "base_got": base_got, "f_base": f_base, "f_quote": f_quote,
                                 "b_fee": b_fee, "q_fee": q_fee, "price": price}
            return f_base, f_quote, b_fee, q_fee

        delta_quote = (amount_base - amount_quote / price) / (Decimal(2) - lp_market.pool_info.fee_rate)
        if delta_quote >= 0:
            base_fee, base_spent, quote_got = lp_market.sell(delta_quote)
            # print(f"sell, quote_fee: {quote_fee}, base_spent: {base_spent}, quote_got: {quote_got}, base: {amount_base}, quote: {amount_quote}")
            f_base, f_quote, b_fee, q_fee = amount_base - base_spent, amount_quote + quote_got, base_fee, None
            if f_base <= ZERO or f_quote <= ZERO:
                print(
                    f"BAD sell, base_fee: {base_fee}, base_spent: {base_spent}, quote_got: {quote_got}, base: {amount_base}, quote: {amount_quote}, f_base: {f_base}, f_quote: {f_quote}")
            self.balance_data = {"amount_base": amount_base, "amount_quote": amount_quote, "base_fee": base_fee,
                                 "base_spent": base_spent, "quote_got": quote_got, "f_base": f_base,
                                 "f_quote": f_quote, "b_fee": b_fee, "q_fee": q_fee, "price": price}
            return f_base, f_quote, b_fee, q_fee

        self.balance_data = {"msg": "no rebalance"}
        return base, quote, None, None