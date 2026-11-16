import numpy as np
import pandas as pd
from models.strategy import Strategy

from indicators.rsi import RSI
from indicators.atr import ATR
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.ma import MA

import core.app_logger as app_logger
logger = app_logger.get_logger(__name__)


class Strategy_Trend(Strategy):
    def __init__(
        self,
        period: int,
        rsi_open: float,
        adx_open: float,
        open_triger: str = 'close',
        close_triger: str = 'close'
    ):
        super().__init__(period)
        self.atr_trailing_mult = 4.5
        self.breakeven_atr_mult = 2.5
        self.period = period
        self.rsi_open = rsi_open
        self.rsi_sell = 100 - rsi_open
        self.adx_open = adx_open
        self.open_triger = open_triger
        self.close_triger = close_triger

        # Используем только существующие в проекте индикаторы.
        # EMA(240) на M15 выступает фильтром старшего таймфрейма (аналог H1 EMA 60)
        self.indicators = [
            RSI("RSI", 14, True),
            MACD('MACD', 12, 26, 9),
            ADX('ADX', 16),
            ATR("ATR", 14),
            MA("EMA_SHORT", 20, "ema"),
            MA("EMA_FAST", 50, "ema"),
            MA("EMA_SLOW", 200, "ema")
        ]

    def open_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        fast_col = 'EMA_FAST' if 'EMA_FAST' in frame.columns else 'EMA_50'
        slow_col = 'EMA_SLOW' if 'EMA_SLOW' in frame.columns else 'EMA_200'

        # 1. Явный направленный тренд: цена выше EMA 200, EMA 50 выше EMA 200 и обе растут
        uptrend = (
            (frame[fast_col] > frame[slow_col]) &
            (frame[fast_col] > frame[fast_col].shift(10)) &
            (frame[slow_col] > frame[slow_col].shift(20))
        )
        downtrend = (
            (frame[fast_col] < frame[slow_col]) &
            (frame[fast_col] < frame[fast_col].shift(10)) &
            (frame[slow_col] < frame[slow_col].shift(20))
        )

        # 2. Глубокий откат к зоне EMA 50 (касание или прокол EMA 50) и возврат выше неё бычьей свечой
        pullback_buy = (
            uptrend &
            (frame['low'].shift(1) <= frame[fast_col].shift(1)) &
            (frame['close'] > frame[fast_col]) &
            (frame['close'] > frame['open'])
        )
        pullback_sell = (
            downtrend &
            (frame['high'].shift(1) >= frame[fast_col].shift(1)) &
            (frame['close'] < frame[fast_col]) &
            (frame['close'] < frame['open'])
        )

        # 3. Разворот осциллятора из зоны локальной перепроданности отката (RSI разворачивается вверх из зоны 35-55)
        momentum_up = (frame['RSI'] > frame['RSI'].shift(1)) & (frame['RSI'] < 58) & (frame['ADX'] >= 20)
        momentum_down = (frame['RSI'] < frame['RSI'].shift(1)) & (frame['RSI'] > 42) & (frame['ADX'] >= 20)

        buy_cond = pullback_buy & momentum_up
        sell_cond = pullback_sell & momentum_down

        # 4. Короткий безопасный стоп за минимум отката (1.5 - 2.0 ATR) и дальний тейк (12 ATR)
        swing_low = np.minimum(frame['low'], frame['low'].shift(1)).fillna(frame['low'])
        swing_high = np.maximum(frame['high'], frame['high'].shift(1)).fillna(frame['high'])

        frame['calc_buy_sl'] = np.clip(
            swing_low - (frame['ATR'] * 0.5),
            frame['close'] - (frame['ATR'] * 2.0),
            frame['close'] - (frame['ATR'] * 1.4)
        )
        frame['calc_sell_sl'] = np.clip(
            swing_high + (frame['ATR'] * 0.5),
            frame['close'] + (frame['ATR'] * 1.4),
            frame['close'] + (frame['ATR'] * 2.0)
        )

        frame['calc_buy_tp'] = frame['close'] + (frame['ATR'] * 12.0)
        frame['calc_sell_tp'] = frame['close'] - (frame['ATR'] * 12.0)

        frame['calc_be_dist'] = frame['ATR'] * self.breakeven_atr_mult
        frame['calc_trail_dist'] = frame['ATR'] * self.atr_trailing_mult

        frame['signal'] = np.select([buy_cond, sell_cond], ["Open_buy", "Open_sell"], default="NaN")
        return frame



    def close_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        # Отключаем досрочный выход по close_signal: пусть трендовую волну ведёт широкий трейлинг-стоп!
        frame['close_signal'] = "NaN"
        return frame

    def sltp_startegy(self, frame: pd.DataFrame, atr_mult: float = 2.2):
        super().sltp_startegy(frame)
        if frame.empty:
            return

        df = frame.iloc[-1]
        try:
            close_p = float(df['close'])
            atr = float(df['ATR'])

            self.buy_sl = float(df.get('calc_buy_sl', close_p - atr * atr_mult))
            self.buy_tp = float(df.get('calc_buy_tp', close_p + atr * 15.0))

            self.sell_sl = float(df.get('calc_sell_sl', close_p + atr * atr_mult))
            self.sell_tp = float(df.get('calc_sell_tp', close_p - atr * 15.0))

            signal = df.get('signal', "NaN")
            self.stop_loss = self.sell_sl if signal == "Open_sell" else self.buy_sl
            self.take_profit = self.sell_tp if signal == "Open_sell" else self.buy_tp
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка расчёта SL/TP в Strategy_Trend: {e}")
