import pandas as pd
import talib


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

    return macd_data, macd_signal, macd_hist

def resample_data(prices: pd.Series, time_frame: str = '1h'):
    """
    time_frame:  '30min', '1h', '4h', '8h', '1d'

    """
    # return prices.resample('h').last()
    # return prices.resample('30min').last()
    return prices.resample(time_frame).last()