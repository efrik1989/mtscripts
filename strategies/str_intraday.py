
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


class Strategy_Intraday(Strategy):
    def __init__(
        self,
        period: int = 12,
        rsi_open: float = 45.0,
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

        # Быстрое сопровождение для интрадея: безубыток на 1.0 ATR, трал 1.6 ATR
        self.atr_trailing_mult = 1.6
        self.breakeven_atr_mult = 1.0

        # Ускоренные индикаторы для внутридневных импульсов (M15 / M10)
        self.indicators = [
            RSI("RSI", 7, True),
            MACD('MACD', 6, 13, 5),
            ADX('ADX', 12),
            ATR("ATR", 10),
            MA("EMA_FAST", period, "ema"),
            MA("EMA_SLOW", 34, "ema")
        ]

    def _get_bar_hours_minutes(self, frame: pd.DataFrame) -> pd.Series:
        """Извлекает время бара в минутах от начала суток (UTC/МСК в зависимости от времени сервера MT5)."""
        if 'time' not in frame.columns:
            return pd.Series(720, index=frame.index)  # Заглушка 12:00, если колонки time нет

        dt = pd.to_datetime(frame['time'], unit='s') if pd.api.types.is_numeric_dtype(frame['time']) else pd.to_datetime(frame['time'])
        return dt.dt.hour * 60 + dt.dt.minute

    def open_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        fast_col = 'EMA_FAST' if 'EMA_FAST' in frame.columns else f'EMA_{self.period}'
        slow_col = 'EMA_SLOW' if 'EMA_SLOW' in frame.columns else 'EMA_34'

        # 1. Входим в активное время дня (10:15 - 17:30 МСК)
        mins = self._get_bar_hours_minutes(frame)
        is_active_hours = (mins >= 10 * 60 + 15) & (mins <= 17 * 60 + 30)

        # 2. Фильтр волатильности от комиссии: ATR >= 0.14%
        enough_volatility = (frame['ATR'] / frame['close']) >= 0.0014

        # 3. Защита от торговли против сильного нисходящего/восходящего тренда
        not_bear_trend = frame[slow_col] >= frame[slow_col].shift(8) - (frame['ATR'] * 0.5)
        not_bull_trend = frame[slow_col] <= frame[slow_col].shift(8) + (frame['ATR'] * 0.5)

        lower_band = frame[fast_col] - (frame['ATR'] * 1.6)
        upper_band = frame[fast_col] + (frame['ATR'] * 1.6)

        no_cascade_down = (frame['close'] < lower_band).rolling(8).sum() <= 1
        no_cascade_up = (frame['close'] > upper_band).rolling(8).sum() <= 1

        bounce_up = (
            (frame['low'].shift(1) <= lower_band.shift(1)) &
            (frame['close'] > lower_band) &
            (frame['close'] > frame['open']) &
            (frame['RSI'] < 38) &
            (frame['RSI'] > frame['RSI'].shift(1)) &
            (frame['macd_hist'] > frame['macd_hist_sh1'])
        )
        bounce_down = (
            (frame['high'].shift(1) >= upper_band.shift(1)) &
            (frame['close'] < upper_band) &
            (frame['close'] < frame['open']) &
            (frame['RSI'] > 62) &
            (frame['RSI'] < frame['RSI'].shift(1)) &
            (frame['macd_hist'] < frame['macd_hist_sh1'])
        )

        buy_cond = is_active_hours & enough_volatility & not_bear_trend & no_cascade_down & bounce_up
        sell_cond = is_active_hours & enough_volatility & not_bull_trend & no_cascade_up & bounce_down

        swing_low = np.minimum(frame['low'], frame['low'].shift(1)).fillna(frame['low'])
        swing_high = np.maximum(frame['high'], frame['high'].shift(1)).fillna(frame['high'])

        frame['calc_buy_sl'] = np.clip(swing_low - frame['ATR'] * 0.4, frame['close'] - frame['ATR'] * 1.6, frame['close'] - frame['ATR'] * 1.2)
        frame['calc_sell_sl'] = np.clip(swing_high + frame['ATR'] * 0.4, frame['close'] + frame['ATR'] * 1.2, frame['close'] + frame['ATR'] * 1.6)

        frame['calc_buy_tp'] = frame['close'] + (frame['ATR'] * 2.8)
        frame['calc_sell_tp'] = frame['close'] - (frame['ATR'] * 2.8)

        self.breakeven_atr_mult = 1.5
        self.atr_trailing_mult = 2.0
        frame['calc_be_dist'] = frame['ATR'] * self.breakeven_atr_mult
        frame['calc_trail_dist'] = frame['ATR'] * self.atr_trailing_mult

        frame['signal'] = np.select([buy_cond, sell_cond], ["Open_buy", "Open_sell"], default="NaN")
        return frame

    def close_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Закрываем позиции только в пятницу вечером (в 23:30), чтобы не переносить риск через выходные."""
        if 'time' not in frame.columns:
            frame['close_signal'] = "NaN"
            return frame

        dt = pd.to_datetime(frame['time'], unit='s') if pd.api.types.is_numeric_dtype(frame['time']) else pd.to_datetime(frame['time'])
        is_friday_evening = (dt.dt.dayofweek == 4) & ((dt.dt.hour * 60 + dt.dt.minute) >= 23 * 60 + 30)

        frame['close_signal'] = np.where(is_friday_evening, "Close_buy", "NaN")
        return frame




    def sltp_startegy(self, frame: pd.DataFrame, atr_mult: float = 1.2):
        super().sltp_startegy(frame)
        if frame.empty:
            return

        df = frame.iloc[-1]
        try:
            close_p = float(df['close'])
            atr = float(df['ATR'])

            self.buy_sl = float(df.get('calc_buy_sl', close_p - atr * atr_mult))
            self.buy_tp = float(df.get('calc_buy_tp', close_p + atr * 2.8))

            self.sell_sl = float(df.get('calc_sell_sl', close_p + atr * atr_mult))
            self.sell_tp = float(df.get('calc_sell_tp', close_p - atr * 2.8))

            signal = df.get('signal', "NaN")
            self.stop_loss = self.sell_sl if signal == "Open_sell" else self.buy_sl
            self.take_profit = self.sell_tp if signal == "Open_sell" else self.buy_tp
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка расчёта SL/TP в Strategy_Intraday: {e}")
