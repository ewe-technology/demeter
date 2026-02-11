from decimal import Decimal

from demeter import DemeterError
from demeter.uniswap import UniLpMarket, PositionInfo
from demeter.uniswap.liquitidy_math import estimate_ratio
from math_const import ZERO
from demeter.uniswap.helper import base_unit_price_to_tick, nearest_usable_tick, MIN_ERROR, get_swap_value_with_part_balance_used


class UniLpMarketV2(UniLpMarket):
    def even_rebalance(self, price: Decimal | None = None):
        """
        Divide assets equally between two tokens and return the fees.

        :param price: price of quote token. e.g. 1234 eth/usdc, if leave to None, will use pool price
        :type price: Decimal
        :return: (base_fee, quote_fee)
        """
        if price is None:
            price = self._market_status.data.price

        amount_quote = self.broker.get_token_balance(self.quote_token)
        amount_base = self.broker.get_token_balance(self.base_token)

        delta_base = (amount_quote / price - amount_base) / (Decimal(2) + self.pool_info.fee_rate)
        if delta_base >= 0:
            # buy returns: fee_in_quote, quote_amount_with_fee, base_amount_got
            fee_in_quote, _, _ = self.buy(delta_base, price)
            return ZERO, fee_in_quote

        delta_quote = (amount_base - amount_quote / price) / (Decimal(2) - self.pool_info.fee_rate)
        if delta_quote >= 0:
            # sell returns: fee_in_base, base_token_amount spend, quote_token_amount got
            fee_in_base, _, _ = self.sell(delta_quote, price)
            return fee_in_base, ZERO
        
        return ZERO, ZERO

    def price_to_raw_tick(self, price: Decimal | float) -> int:
        """
        convert price to tick

        :param price: price
        :type price:  Decimal | float
        :return: tick
        :rtype: int
        """
        return base_unit_price_to_tick(
                price,
                self._pool.token0.decimal,
                self._pool.token1.decimal,
                self._is_token0_quote,
            )


    def add_liquidity_by_value_ext(
        self,
        lower_tick: int,
        upper_tick: int,
        value_to_use: Decimal | None = None,
        trim_tick: bool = True,
        base_fee: Decimal = ZERO,
        quote_fee: Decimal = ZERO,
    ) -> (PositionInfo, Decimal, Decimal, int, Decimal, Decimal):
        """
        Add liquidity from balance with value defined, and swap if necessary.
        e.g. you have 1 eth and 3000 usdc, and eth price is 1000. If you want to invest at 1:1,
        you have to swap 1000 usdc to eth, so your balance will be 2 eth and 2000 usdc, but swap fee is not counted.
        this function will calculate the best swap amount(1005.025, if fee is 1%),
        which will make the balance at: 1.99975 eth and 1994.975 usdc, which is just 1:1, So all balance will be used.
        This function to free you from complex calculation.


        :param lower_tick: lower tick
        :type lower_tick: int
        :param upper_tick: upper tick
        :type upper_tick: int
        :param trim_tick: trim tick according to tick spacing, default is True
        :type trim_tick: bool
        :param value_to_use: Value you want to add liquidity(in quote token). Actual value used would be less than this value because swap fee might be charged.
        :param base_fee: base token fee earned, will be subtracted from balance and not used in calculation
        :param quote_fee: quote token fee earned, will be subtracted from balance and not used in calculation
        :return: added get_position, base token used, quote token used, liquidity, base swap fee, quote swap fee
        :rtype: (PositionInfo, Decimal, Decimal, int, Decimal, Decimal)
        """
        if trim_tick:
            lower_tick = nearest_usable_tick(lower_tick, self.pool_info.tick_spacing)
            upper_tick = nearest_usable_tick(upper_tick, self.pool_info.tick_spacing)
        price = self._market_status.data.price
        tick = self.price_to_tick(price)
        price0, price1 = self._convert_pair(price, Decimal(1))

        quote_balance = self.broker.get_token_balance(self.quote_token) - quote_fee
        base_balance_value = (self.broker.get_token_balance(self.base_token) - base_fee) * price

        balance = quote_balance + base_balance_value

        if value_to_use is None:
            value_to_use = balance

        if value_to_use > balance:
            raise DemeterError("Not enough balance to add liquidity")
        if lower_tick >= upper_tick:
            raise DemeterError("Lower tick is larger than upper tick")

        base_swap_fee = ZERO
        quote_swap_fee = ZERO

        # price is greater than upper price
        if (self._is_token0_quote and tick >= upper_tick) or (not self._is_token0_quote and tick <= lower_tick):
            # all base
            base_amount = value_to_use / self._market_status.data.price
            diff = base_amount - (self.broker.get_token_balance(self.base_token) - base_fee)
            fee_in_quote = Decimal(0)
            if diff > MIN_ERROR:
                fee_in_quote, to_amount = self.swap(diff * price, self.quote_token, self.base_token)
                quote_swap_fee = fee_in_quote
            res = self.add_liquidity_by_tick(lower_tick, upper_tick, base_amount - fee_in_quote / price, Decimal(0))
            return res[0], res[1], res[2], res[3], base_swap_fee, quote_swap_fee

        # price is lower than lower price
        if (self._is_token0_quote and tick <= lower_tick) or (not self._is_token0_quote and tick >= upper_tick):
            # all quote
            diff = value_to_use - (self.broker.get_token_balance(self.quote_token) - quote_fee)
            fee_in_base = Decimal(0)
            if diff > 0:
                fee_in_base, quote_got = self.swap(diff / price, self.base_token, self.quote_token)
                base_swap_fee = fee_in_base
            res = self.add_liquidity_by_tick(lower_tick, upper_tick, Decimal(0), value_to_use - fee_in_base * price)
            return res[0], res[1], res[2], res[3], base_swap_fee, quote_swap_fee

        # price is in tick range

        ratio = estimate_ratio(tick, lower_tick, upper_tick)
        ratio_in_amount = ratio * 10 ** (self.pool_info.token1.decimal - self.pool_info.token0.decimal)
        ratio_in_value = Decimal(ratio_in_amount) / price if self._is_token0_quote else Decimal(ratio_in_amount) * price

        token1_value = value_to_use / (ratio_in_value + 1)
        token0_value = value_to_use - token1_value
        balance0_value = (self.broker.get_token_balance(self.token0) - (quote_fee if self._is_token0_quote else base_fee)) * price0
        balance1_value = (self.broker.get_token_balance(self.token1) - (base_fee if self._is_token0_quote else quote_fee)) * price1
        if token0_value <= balance0_value and token1_value <= balance1_value:
            # do not need swap
            base_value, quote_value = self._convert_pair(token0_value, token1_value)
            res = self.add_liquidity_by_tick(lower_tick, upper_tick, base_value / price, quote_value)
            return res[0], res[1], res[2], res[3], base_swap_fee, quote_swap_fee
        elif token0_value > balance0_value and token1_value > balance1_value:
            raise DemeterError("Not enough balance to add liquidity")
        elif token0_value < balance0_value and token1_value > balance1_value:
            # need swap from token0 to token1
            actual_token0_value, actual_token1_value, swap_value = get_swap_value_with_part_balance_used(
                balance0_value, balance1_value, value_to_use, self.pool_info.fee_rate, ratio_in_value
            )
            if self._is_token0_quote:
                fee, to_amount = self.swap(swap_value, self.quote_token, self.base_token)
                quote_swap_fee = fee
            else:
                fee, to_amount = self.swap(swap_value / price, self.base_token, self.quote_token)
                base_swap_fee = fee
            base_value, quote_value = self._convert_pair(actual_token0_value, actual_token1_value)
            res = self.add_liquidity_by_tick(lower_tick, upper_tick, base_value / price, quote_value)
            return res[0], res[1], res[2], res[3], base_swap_fee, quote_swap_fee
        elif token0_value > balance0_value and token1_value < balance1_value:
            # need to swap from token1 to token 0
            actual_token1_value, actual_token0_value, swap_value = get_swap_value_with_part_balance_used(
                balance1_value, balance0_value, value_to_use, self.pool_info.fee_rate, 1 / ratio_in_value
            )
            if self._is_token0_quote:
                fee, to_amount = self.swap(swap_value / price, self.base_token, self.quote_token)
                base_swap_fee = fee
            else:
                fee, to_amount = self.swap(swap_value, self.quote_token, self.base_token)
                quote_swap_fee = fee
            base_value, quote_value = self._convert_pair(actual_token0_value, actual_token1_value)
            res = self.add_liquidity_by_tick(lower_tick, upper_tick, base_value / price, quote_value)
            return res[0], res[1], res[2], res[3], base_swap_fee, quote_swap_fee
        else:
            raise NotImplementedError()
        pass