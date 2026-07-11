"""
Trading strategies.

Every strategy implements `generate_signals(df) -> pd.Series` where `df`
has at least a 'close' column indexed by date, and the returned Series
holds a target position for each date:
    1  -> fully long
    0  -> flat (out of the market)
   -1  -> fully short (only used if the strategy explicitly supports shorting)

The backtester shifts this position series by one day before applying it
to returns, so signals generated using day T's close are only acted on
starting day T+1 (no look-ahead bias).
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder's Average True Range -- used by several trend-following strategies below."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _adx_di(df: pd.DataFrame, period: int):
    """Wilder's +DI / -DI / ADX (trend direction + trend strength)."""
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    atr = _atr(df, period)
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return plus_di, minus_di, adx.fillna(0)


class Strategy:
    name = "base"
    #: human-readable parameter schema, used by the CLI for validation/help
    param_info = {}
    #: {param_name: default_value} used to auto-build UI forms (e.g. Streamlit)
    default_params = {}

    def __init__(self, **params):
        self.params = params

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def __repr__(self):
        return f"{self.name}({self.params})"


class BuyAndHold(Strategy):
    name = "buy_and_hold"
    param_info = {}
    default_params = {}

    def generate_signals(self, df):
        return pd.Series(1, index=df.index)


class SmaCrossStrategy(Strategy):
    """Classic golden/death cross: long when fast SMA > slow SMA."""
    name = "sma_cross"
    param_info = {"fast": "fast SMA window (default 50)", "slow": "slow SMA window (default 200)"}
    default_params = {"fast": 50, "slow": 200}

    def generate_signals(self, df):
        fast = int(self.params.get("fast", 50))
        slow = int(self.params.get("slow", 200))
        sma_fast = df["close"].rolling(fast).mean()
        sma_slow = df["close"].rolling(slow).mean()
        signal = pd.Series(0, index=df.index)
        signal[sma_fast > sma_slow] = 1
        return signal


class RsiMeanReversionStrategy(Strategy):
    """Buy when RSI < oversold, exit when RSI > overbought."""
    name = "rsi_mean_reversion"
    param_info = {
        "period": "RSI lookback period (default 14)",
        "oversold": "RSI level to enter long (default 30)",
        "overbought": "RSI level to exit (default 60)",
    }
    default_params = {"period": 14, "oversold": 30, "overbought": 60}

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def generate_signals(self, df):
        period = int(self.params.get("period", 14))
        oversold = float(self.params.get("oversold", 30))
        overbought = float(self.params.get("overbought", 60))

        rsi = self._rsi(df["close"], period)
        signal = pd.Series(np.nan, index=df.index)
        signal[rsi < oversold] = 1
        signal[rsi > overbought] = 0
        signal = signal.ffill().fillna(0)
        return signal


class BollingerBandStrategy(Strategy):
    """Long when price closes below the lower band, exit above the middle band."""
    name = "bollinger_bands"
    param_info = {
        "period": "rolling window (default 20)",
        "num_std": "number of std deviations for the bands (default 2)",
    }
    default_params = {"period": 20, "num_std": 2}

    def generate_signals(self, df):
        period = int(self.params.get("period", 20))
        num_std = float(self.params.get("num_std", 2))

        mid = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        lower = mid - num_std * std
        upper = mid + num_std * std  # noqa: F841 (kept for reference / potential short logic)

        signal = pd.Series(np.nan, index=df.index)
        signal[df["close"] < lower] = 1
        signal[df["close"] > mid] = 0
        signal = signal.ffill().fillna(0)
        return signal


class MacdStrategy(Strategy):
    """Long when MACD line crosses above the signal line."""
    name = "macd"
    param_info = {
        "fast": "fast EMA span (default 12)",
        "slow": "slow EMA span (default 26)",
        "signal": "signal EMA span (default 9)",
    }
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def generate_signals(self, df):
        fast = int(self.params.get("fast", 12))
        slow = int(self.params.get("slow", 26))
        signal_span = int(self.params.get("signal", 9))

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_span, adjust=False).mean()

        signal = pd.Series(0, index=df.index)
        signal[macd_line > signal_line] = 1
        return signal


class DonchianBreakoutStrategy(Strategy):
    """Long on an N-day high breakout, exit on an M-day low breakdown (turtle-style)."""
    name = "donchian_breakout"
    param_info = {
        "entry_window": "days for the entry high channel (default 20)",
        "exit_window": "days for the exit low channel (default 10)",
    }
    default_params = {"entry_window": 20, "exit_window": 10}

    def generate_signals(self, df):
        entry_w = int(self.params.get("entry_window", 20))
        exit_w = int(self.params.get("exit_window", 10))

        entry_high = df["close"].rolling(entry_w).max()
        exit_low = df["close"].rolling(exit_w).min()

        signal = pd.Series(np.nan, index=df.index)
        signal[df["close"] >= entry_high] = 1
        signal[df["close"] <= exit_low] = 0
        signal = signal.ffill().fillna(0)
        return signal


class SupertrendStrategy(Strategy):
    """
    Classic ATR-based trend follower. Flips long/short when price crosses
    a volatility-adjusted band that trails the trend; stays long/flat for
    the whole duration of an uptrend rather than exiting on every wiggle.
    Good default for 'ride the trend' behavior on trending stocks.
    """
    name = "supertrend"
    param_info = {
        "period": "ATR lookback period (default 10)",
        "multiplier": "ATR multiplier controlling band width -- larger = fewer, later signals (default 3)",
    }
    default_params = {"period": 10, "multiplier": 3.0}

    def generate_signals(self, df):
        period = int(self.params.get("period", 10))
        multiplier = float(self.params.get("multiplier", 3.0))

        atr = _atr(df, period)
        hl2 = (df["high"] + df["low"]) / 2
        basic_upper = (hl2 + multiplier * atr).to_numpy()
        basic_lower = (hl2 - multiplier * atr).to_numpy()
        close = df["close"].to_numpy()
        n = len(df)

        final_upper = np.full(n, np.nan)
        final_lower = np.full(n, np.nan)
        trend = np.ones(n, dtype=int)

        # ATR needs `period` bars to warm up (NaN before that); start the
        # recursive band calculation at the first bar where it's valid,
        # otherwise a leading NaN silently propagates through every later
        # bar via the "hold previous band" branch below.
        valid = ~np.isnan(basic_upper)
        if not valid.any():
            return pd.Series(0, index=df.index)
        start = np.argmax(valid)  # index of first True

        final_upper[start] = basic_upper[start]
        final_lower[start] = basic_lower[start]
        trend[start] = 1

        for i in range(start + 1, n):
            final_upper[i] = (basic_upper[i] if (basic_upper[i] < final_upper[i - 1]
                               or close[i - 1] > final_upper[i - 1]) else final_upper[i - 1])
            final_lower[i] = (basic_lower[i] if (basic_lower[i] > final_lower[i - 1]
                               or close[i - 1] < final_lower[i - 1]) else final_lower[i - 1])
            if trend[i - 1] == 1 and close[i] < final_lower[i]:
                trend[i] = -1
            elif trend[i - 1] == -1 and close[i] > final_upper[i]:
                trend[i] = 1
            else:
                trend[i] = trend[i - 1]

        signal = (trend == 1).astype(int)
        signal[:start] = 0  # no signal during ATR warm-up
        return pd.Series(signal, index=df.index)


class AdxTrendStrategy(Strategy):
    """
    Trend-strength filter: goes long only when +DI is above -DI (upward
    directional pressure) AND ADX confirms the market is actually trending
    (as opposed to choppy/sideways). Designed to sit out low-conviction periods.
    """
    name = "adx_trend"
    param_info = {
        "period": "ADX/DMI lookback period (default 14)",
        "adx_threshold": "minimum ADX to treat the market as trending, typically 20-25 (default 20)",
    }
    default_params = {"period": 14, "adx_threshold": 20}

    def generate_signals(self, df):
        period = int(self.params.get("period", 14))
        threshold = float(self.params.get("adx_threshold", 20))
        plus_di, minus_di, adx = _adx_di(df, period)
        signal = pd.Series(0, index=df.index)
        signal[(plus_di > minus_di) & (adx > threshold)] = 1
        return signal


class ParabolicSarStrategy(Strategy):
    """
    Trailing-stop-style trend follower that flips position whenever price
    crosses the SAR dots; the acceleration factor speeds up as a trend
    extends, so it tightens the stop the longer a trend runs.
    """
    name = "parabolic_sar"
    param_info = {
        "af_start": "initial acceleration factor (default 0.02)",
        "af_step": "how much AF increases per new extreme price (default 0.02)",
        "af_max": "cap on the acceleration factor (default 0.2)",
    }
    default_params = {"af_start": 0.02, "af_step": 0.02, "af_max": 0.2}

    def generate_signals(self, df):
        af_start = float(self.params.get("af_start", 0.02))
        af_step = float(self.params.get("af_step", 0.02))
        af_max = float(self.params.get("af_max", 0.2))

        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        n = len(df)

        sar = np.zeros(n)
        trend = np.ones(n, dtype=int)  # 1 = up, -1 = down
        ep = np.zeros(n)
        af = np.zeros(n)

        trend[0] = 1
        sar[0] = low[0]
        ep[0] = high[0]
        af[0] = af_start

        for i in range(1, n):
            prev_sar, prev_trend, prev_ep, prev_af = sar[i - 1], trend[i - 1], ep[i - 1], af[i - 1]
            candidate_sar = prev_sar + prev_af * (prev_ep - prev_sar)

            if prev_trend == 1:
                candidate_sar = min(candidate_sar, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
                if low[i] < candidate_sar:
                    trend[i], sar[i], ep[i], af[i] = -1, prev_ep, low[i], af_start
                else:
                    trend[i], sar[i] = 1, candidate_sar
                    if high[i] > prev_ep:
                        ep[i], af[i] = high[i], min(prev_af + af_step, af_max)
                    else:
                        ep[i], af[i] = prev_ep, prev_af
            else:
                candidate_sar = max(candidate_sar, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
                if high[i] > candidate_sar:
                    trend[i], sar[i], ep[i], af[i] = 1, prev_ep, high[i], af_start
                else:
                    trend[i], sar[i] = -1, candidate_sar
                    if low[i] < prev_ep:
                        ep[i], af[i] = low[i], min(prev_af + af_step, af_max)
                    else:
                        ep[i], af[i] = prev_ep, prev_af

        return pd.Series((trend == 1).astype(int), index=df.index)


class StochasticOscillatorStrategy(Strategy):
    """Momentum oscillator: long when %D is oversold, exit once it's overbought."""
    name = "stochastic_oscillator"
    param_info = {
        "k_period": "lookback window for %K (default 14)",
        "d_period": "smoothing window for %D (default 3)",
        "oversold": "%D level to enter long, e.g. 20 (default 20)",
        "overbought": "%D level to exit, e.g. 80 (default 80)",
    }
    default_params = {"k_period": 14, "d_period": 3, "oversold": 20, "overbought": 80}

    def generate_signals(self, df):
        k_period = int(self.params.get("k_period", 14))
        d_period = int(self.params.get("d_period", 3))
        oversold = float(self.params.get("oversold", 20))
        overbought = float(self.params.get("overbought", 80))

        low_min = df["low"].rolling(k_period).min()
        high_max = df["high"].rolling(k_period).max()
        percent_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
        percent_d = percent_k.rolling(d_period).mean()

        signal = pd.Series(np.nan, index=df.index)
        signal[percent_d < oversold] = 1
        signal[percent_d > overbought] = 0
        return signal.ffill().fillna(0)


class CciTrendStrategy(Strategy):
    """
    Commodity Channel Index used as a breakout/trend filter: enters long on
    a strong upside breakout (CCI pushing above +100) and exits once
    momentum fades back below zero (or the exit level you set).
    """
    name = "cci_trend"
    param_info = {
        "period": "CCI lookback period (default 20)",
        "entry_level": "CCI level confirming an upside breakout, e.g. 100 (default 100)",
        "exit_level": "CCI level to exit the long, e.g. -100 (default -100)",
    }
    default_params = {"period": 20, "entry_level": 100, "exit_level": -100}

    def generate_signals(self, df):
        period = int(self.params.get("period", 20))
        entry_level = float(self.params.get("entry_level", 100))
        exit_level = float(self.params.get("exit_level", -100))

        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        sma_tp = typical_price.rolling(period).mean()
        mean_dev = typical_price.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        cci = (typical_price - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))

        signal = pd.Series(np.nan, index=df.index)
        signal[cci > entry_level] = 1
        signal[cci < exit_level] = 0
        return signal.ffill().fillna(0)


class WilliamsRStrategy(Strategy):
    """Momentum oscillator (inverted stochastic): long when oversold, exit when overbought."""
    name = "williams_r"
    param_info = {
        "period": "lookback period (default 14)",
        "oversold": "%R level to enter long, e.g. -80 (default -80)",
        "overbought": "%R level to exit, e.g. -20 (default -20)",
    }
    default_params = {"period": 14, "oversold": -80.0, "overbought": -20.0}

    def generate_signals(self, df):
        period = int(self.params.get("period", 14))
        oversold = float(self.params.get("oversold", -80))
        overbought = float(self.params.get("overbought", -20))

        high_max = df["high"].rolling(period).max()
        low_min = df["low"].rolling(period).min()
        williams_r = -100 * (high_max - df["close"]) / (high_max - low_min).replace(0, np.nan)

        signal = pd.Series(np.nan, index=df.index)
        signal[williams_r < oversold] = 1
        signal[williams_r > overbought] = 0
        return signal.ffill().fillna(0)


class IchimokuCloudStrategy(Strategy):
    """
    Trend-following: long only when price trades above the Ichimoku cloud
    AND the short-term conversion line is above the base line -- i.e. both
    the near-term and medium-term trend agree.
    """
    name = "ichimoku_cloud"
    param_info = {
        "tenkan_period": "conversion line period (default 9)",
        "kijun_period": "base line period, also the cloud's forward shift (default 26)",
        "senkou_b_period": "leading span B period (default 52)",
    }
    default_params = {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}

    def generate_signals(self, df):
        tenkan_p = int(self.params.get("tenkan_period", 9))
        kijun_p = int(self.params.get("kijun_period", 26))
        senkou_b_p = int(self.params.get("senkou_b_period", 52))

        high, low, close = df["high"], df["low"], df["close"]
        tenkan = (high.rolling(tenkan_p).max() + low.rolling(tenkan_p).min()) / 2
        kijun = (high.rolling(kijun_p).max() + low.rolling(kijun_p).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(kijun_p)
        senkou_b = ((high.rolling(senkou_b_p).max() + low.rolling(senkou_b_p).min()) / 2).shift(kijun_p)

        cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)

        signal = pd.Series(0, index=df.index)
        signal[(close > cloud_top) & (tenkan > kijun)] = 1
        return signal


class MovingAverageRibbonStrategy(Strategy):
    """
    Trend-confirmation strategy: only long when three SMAs of increasing
    length are stacked in bullish order (short > mid > long), a simple but
    effective way to filter out weak/choppy trends.
    """
    name = "ma_ribbon"
    param_info = {
        "short": "shortest SMA window (default 10)",
        "mid": "middle SMA window (default 30)",
        "long": "longest SMA window (default 60)",
    }
    default_params = {"short": 10, "mid": 30, "long": 60}

    def generate_signals(self, df):
        short_w = int(self.params.get("short", 10))
        mid_w = int(self.params.get("mid", 30))
        long_w = int(self.params.get("long", 60))

        sma_short = df["close"].rolling(short_w).mean()
        sma_mid = df["close"].rolling(mid_w).mean()
        sma_long = df["close"].rolling(long_w).mean()

        signal = pd.Series(0, index=df.index)
        signal[(sma_short > sma_mid) & (sma_mid > sma_long)] = 1
        return signal


STRATEGY_REGISTRY = {
    cls.name: cls
    for cls in [
        BuyAndHold,
        SmaCrossStrategy,
        RsiMeanReversionStrategy,
        BollingerBandStrategy,
        MacdStrategy,
        DonchianBreakoutStrategy,
        SupertrendStrategy,
        AdxTrendStrategy,
        ParabolicSarStrategy,
        StochasticOscillatorStrategy,
        CciTrendStrategy,
        WilliamsRStrategy,
        IchimokuCloudStrategy,
        MovingAverageRibbonStrategy,
    ]
}


def get_strategy(name: str, **params) -> Strategy:
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(STRATEGY_REGISTRY.keys())
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return STRATEGY_REGISTRY[name](**params)
