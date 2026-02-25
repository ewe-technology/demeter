from decimal import Decimal

from demeter import (
    Strategy,
    Snapshot,
)
from demeter.uniswap import UniLpMarket, liquitidy_math
from math_const import ZERO, ONE
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

    def calculate_swap_amount(self, current_tick: int, lower_tick: int, upper_tick: int, base_amount: Decimal, quote_amount: Decimal) -> tuple[Decimal, Decimal]:
        """
        using current_tick to calculate if a liquidity range of lower_tick to upper_tick to be placed with given base_amount and quote_amount, how much base or quote is needed to be swapped in order to allocate most asset into the liquidity
        """
        lp_market: UniLpMarket = self.broker.markets[self.utils.market_key]
        token0_is_quote = lp_market.pool_info.is_token0_quote

        sqrt_price_x96 = liquitidy_math.get_sqrt_ratio_at_tick(current_tick)
        sqrt_a = liquitidy_math.get_sqrt_ratio_at_tick(lower_tick)
        sqrt_b = liquitidy_math.get_sqrt_ratio_at_tick(upper_tick)

        if sqrt_a > sqrt_b:
            sqrt_a, sqrt_b = sqrt_b, sqrt_a

        if sqrt_price_x96 <= sqrt_a:
            # All token0
            if token0_is_quote:
                return base_amount, ZERO # swap all base to quote (token0)
            else:
                return ZERO, quote_amount # swap all quote to base (token0)
        elif sqrt_price_x96 >= sqrt_b:
            # All token1
            if token0_is_quote:
                return ZERO, quote_amount # swap all quote to base (token1)
            else:
                return base_amount, ZERO # swap all base to quote (token1)
        else:
            # In range
            ratio = Decimal(liquitidy_math.amounts_relation(current_tick, lower_tick, upper_tick, lp_market.pool_info.token0.decimal, lp_market.pool_info.token1.decimal))
            # amount0 = ratio * amount1
            
            # Price of token0 in terms of token1
            p0 = (Decimal(sqrt_price_x96) / Decimal(2**96))**2 * Decimal(10**(lp_market.pool_info.token0.decimal - lp_market.pool_info.token1.decimal))
            
            if token0_is_quote:
                # token0 = quote, token1 = base
                # ratio = amount1 / amount0 = base / quote
                # target: base_final = ratio * quote_final
                
                # If swap dq (quote) to base:
                # base + dq * p0 = ratio * (quote - dq)
                # dq * (ratio + p0) = ratio * quote - base
                # dq = (ratio * quote - base) / (ratio + p0)
                
                delta_quote = (ratio * quote_amount - base_amount) / (ratio + p0)
                if delta_quote > 0:
                    return ZERO, delta_quote # swap delta_quote quote to base
                else:
                    # swap base to quote
                    # base_final = base - db
                    # quote_final = quote + db / p0
                    # base - db = ratio * (quote + db / p0)
                    # db * (1 + ratio / p0) = base - ratio * quote
                    delta_base = (base_amount - ratio * quote_amount) / (ONE + ratio / p0)
                    return delta_base, ZERO
            else:
                # token0 = base, token1 = quote
                # ratio = amount1 / amount0 = quote / base
                # target: quote_final = ratio * base_final
                
                # If swap db (base) to quote:
                # quote + db * p0 = ratio * (base - db)
                # db * (ratio + p0) = ratio * base - quote
                # db = (ratio * base - quote) / (ratio + p0)
                
                delta_base = (ratio * base_amount - quote_amount) / (ratio + p0)
                if delta_base > 0:
                    return delta_base, ZERO # swap delta_base base to quote
                else:
                    # swap quote to base
                    # quote_final = quote - dq
                    # base_final = base + dq / p0
                    # quote - dq = ratio * (base + dq / p0)
                    # dq * (1 + ratio / p0) = quote - ratio * base
                    delta_quote = (quote_amount - ratio * base_amount) / (ONE + ratio / p0)
                    return ZERO, delta_quote

    def execute_swap(self, lp_market: UniLpMarket, base_to_swap: Decimal, quote_to_swap: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Execute the swap using buy and sell as needed.
        :return: (swapped_base_amount, swapped_quote_amount, fee_base, fee_quote)
        """
        fee_base, fee_quote = ZERO, ZERO
        swapped_base, swapped_quote = ZERO, ZERO

        if base_to_swap > ZERO:
            # sell base to get quote
            fee_base, _, swapped_quote = lp_market.sell(base_to_swap)
            swapped_base = base_to_swap
        elif quote_to_swap > ZERO:
            # buy base using quote
            # calculate base_to_buy from quote_to_swap
            # quote_amount_with_fee = base_token_amount * price / (1 - self._pool.fee_rate)
            # base_token_amount = quote_amount_with_fee * (1 - self._pool.fee_rate) / price
            price = lp_market.market_status.data.price
            base_to_buy = quote_to_swap * (ONE - Decimal(lp_market.pool_info.fee_rate)) / price
            fee_quote, _, swapped_base = lp_market.buy(base_to_buy)
            swapped_quote = quote_to_swap

        return swapped_base, swapped_quote, fee_base, fee_quote

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