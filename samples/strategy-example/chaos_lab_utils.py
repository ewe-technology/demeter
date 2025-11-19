import pandas as pd
import talib
from sys import float_info as sflt


def standard_deviation_over_last(prices: pd.Series, minutes: int) -> pd.Series:

    # rolling_std = prices.rolling(window=minutes).std()
    rolling_std = talib.STDDEV(prices, timeperiod=minutes)
    return rolling_std


def average_true_range(lows: pd.Series, highs: pd.Series, closes: pd.Series, minutes: int) -> pd.Series:
    # tr1 = highs - lows
    # tr2 = abs(highs - closes.shift(1))
    # tr3 = abs(lows - closes.shift(1))
    # tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    #
    # atr = tr.rolling(window=minutes, min_periods=1).mean()
    atr = talib.ATR(highs, lows, closes, timeperiod=minutes)

    return atr

def macd(prices: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:

    macd_data, macd_signal, macd_hist = talib.MACD(prices, fastperiod=fast_period, slowperiod=slow_period, signalperiod=signal_period)
    macd_delta = macd_hist

    return macd_data, macd_signal, macd_delta


def stochRSI(prices: pd.Series, time_period = 14, fastk_period = 5, fastd_period = 3, fastd_matype = 0) -> tuple[pd.Series, pd.Series, pd.Series]:

    """
     talib's stoch RSI is weird, dont use
    """

    fastk, fastd = talib.STOCHRSI(prices, timeperiod=time_period, fastk_period=fastk_period, fastd_period=fastd_period, fastd_matype=fastd_matype) #
    diff = fastk - fastd
    return fastk, fastd, diff


def stochRSI_self_implement(prices: pd.Series, time_period = 14, fastk_period = 5, fastd_period = 3, fastd_matype = 0) -> tuple[pd.Series, pd.Series, pd.Series]:

    """
    https://github.com/TA-Lib/ta-lib-python/issues/594#issuecomment-1560640283
     ‘note that this snippet uses talib RSI so be careful with "very small numbers" (first case)’
    """
    rsi_ = talib.RSI(prices, time_period)
    print(len(prices))
    print("====rsi=====")
    print(len(rsi_))
    print(','.join(map(str, rsi_.values)))
    print("============")

    _rolling = rsi_.rolling(time_period)
    lowest_rsi = _rolling.min()
    highest_rsi = _rolling.max()
    print("====highest rsi=====")
    print(len(highest_rsi))
    print(','.join(map(str, highest_rsi.values)))
    print("============")

    stoch = 100 * (rsi_ - lowest_rsi)
    _diff = highest_rsi - lowest_rsi
    if _diff.eq(0).any().any():
        _diff += sflt.epsilon
    stoch /= _diff

    print("====stoch=====")
    print(len(stoch))
    print(','.join(map(str, stoch.values)))
    print("============")

    if fastd_matype == 0: #SMA
        stochrsi_k = talib.SMA(stoch, fastk_period)
        stochrsi_d = talib.SMA(stochrsi_k, fastd_period)
    else: # 1 = EMA
        stochrsi_k = talib.EMA(stoch, fastk_period)
        stochrsi_d = talib.EMA(stochrsi_k, fastd_period)
    diff = stochrsi_k - stochrsi_d
    return stochrsi_k, stochrsi_d, diff


def resample_data(prices: pd.Series, time_frame: str = '1h'):
    """
    time_frame:  '30min', '1h', '4h', '8h', '1d'

    """
    # return prices.resample('h').last()
    # return prices.resample('30min').last()
    return prices.resample(time_frame).last()
