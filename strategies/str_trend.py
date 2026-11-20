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
        period: int = 20,
        rsi_open: float = 52.0,
        adx_open: float = 22.0,
        open_triger: str = 'close',
        close_triger: str = 'close'
    ):
        super().__init__(period)
        self.period = period
        self.rsi_open = rsi_open
        self.rsi_sell = 100 - rsi_open
        self.adx_open = adx_open
        self.open_triger = open_triger
        self.close_triger = close_triger

        # Широкий трал 5.3 ATR и поздний безубыток 3.2 ATR для высиживания мощных трендов
        self.atr_trailing_mult = 5.3
        self.breakeven_atr_mult = 3.2

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
        short_col = 'EMA_SHORT' if 'EMA_SHORT' in frame.columns else 'EMA_20'
        fast_col = 'EMA_FAST' if 'EMA_FAST' in frame.columns else 'EMA_50'
        slow_col = 'EMA_SLOW' if 'EMA_SLOW' in frame.columns else 'EMA_200'

        # 1. Глобальный сильный тренд: веер EMA 20 > EMA 50 > EMA 200 и отрыв от EMA 200 >= 1.0 ATR
        uptrend = (
            (frame[short_col] > frame[fast_col]) &
            ((frame[fast_col] - frame[slow_col]) >= (frame['ATR'] * 1.0)) &
            (frame[slow_col] > frame[slow_col].shift(15))
        )
        downtrend = (
            (frame[short_col] < frame[fast_col]) &
            ((frame[slow_col] - frame[fast_col]) >= (frame['ATR'] * 1.0)) &
            (frame[slow_col] < frame[slow_col].shift(15))
        )

        # 2. Защита от боковика: цена не должна пилить EMA 50 (не более 3 закрытий ниже за 10 дней)
        not_choppy_up = (frame['close'] < frame[fast_col]).rolling(10).sum() <= 3
        not_choppy_down = (frame['close'] > frame[fast_col]).rolling(10).sum() <= 3

        # 3. Вход на откате к EMA 20 ИЛИ EMA 50 (ловит быстрые трендовые волны, как на скриншоте)
        pullback_buy = (
            uptrend &
            not_choppy_up &
            ((frame['low'].shift(1) <= frame[short_col].shift(1)) | (frame['low'].shift(1) <= frame[fast_col].shift(1))) &
            (frame['close'] > frame[short_col]) &
            (frame['close'] > frame['open'])
        )
        pullback_sell = (
            downtrend &
            not_choppy_down &
            ((frame['high'].shift(1) >= frame[short_col].shift(1)) | (frame['high'].shift(1) >= frame[fast_col].shift(1))) &
            (frame['close'] < frame[short_col]) &
            (frame['close'] < frame['open'])
        )

        momentum_up = (frame['ADX'] >= self.adx_open) & (frame['RSI'] > frame['RSI'].shift(1)) & (frame['RSI'] < 65)
        momentum_down = (frame['ADX'] >= self.adx_open) & (frame['RSI'] < frame['RSI'].shift(1)) & (frame['RSI'] > 35)

        buy_cond = pullback_buy & momentum_up
        sell_cond = pullback_sell & momentum_down

        swing_low = np.minimum(frame['low'], frame['low'].shift(1)).fillna(frame['low'])
        swing_high = np.maximum(frame['high'], frame['high'].shift(1)).fillna(frame['high'])

        frame['calc_buy_sl'] = np.clip(
            swing_low - (frame['ATR'] * 0.5),
            frame['close'] - (frame['ATR'] * 2.2),
            frame['close'] - (frame['ATR'] * 1.5)
        )
        frame['calc_sell_sl'] = np.clip(
            swing_high + (frame['ATR'] * 0.5),
            frame['close'] + (frame['ATR'] * 1.5),
            frame['close'] + (frame['ATR'] * 2.2)
        )

        # Дальний тейк 30 ATR, чтобы сделку закрывал только трейлинг-стоп на развороте всего тренда
        frame['calc_buy_tp'] = frame['close'] + (frame['ATR'] * 30.0)
        frame['calc_sell_tp'] = frame['close'] - (frame['ATR'] * 30.0)

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
