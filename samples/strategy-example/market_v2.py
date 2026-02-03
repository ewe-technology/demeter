from decimal import Decimal
from demeter.uniswap import UniLpMarket
from math_const import ZERO
from demeter.uniswap.helper import base_unit_price_to_tick

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