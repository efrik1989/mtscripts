import numpy as np
import pandas as pd
from models.strategy import Strategy

from indicators.rsi import RSI
from indicators.atr import ATR
from indicators.bollinger_bands import Bollinger
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.ma import MA

import core.app_logger as app_logger
logger = app_logger.get_logger(__name__)


class Strategy_BB(Strategy):
    def __init__(self, period: int, rsi_open: float, adx_open: float, open_triger: str = 'close', close_triger: str = 'close'):
        super().__init__(period)
        self.period = period
        self.rsi_open = rsi_open
        self.rsi_sell = 100 - rsi_open
        self.adx_open = adx_open
        self.open_triger = open_triger
        self.close_triger = close_triger

        self.bbu_col = f'BBU_{period}_2.0_2.0'
        self.bbm_col = f'BBM_{period}_2.0_2.0'
        self.bbl_col = f'BBL_{period}_2.0_2.0'

        self.indicators = [
            Bollinger("BB", period),
            RSI("RSI", 11, True),
            MACD('MACD', 12, 8, 21, 5),
            ADX('ADX', 16),
            ATR("ATR", 14),
            MA("EMA", 50, "ema")
        ]

    def open_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        # 1. Режим рынка: флэт (ADX < 25) ИЛИ торговля строго в сторону тренда EMA 50
        is_flat = frame['ADX'] < 25
        uptrend = (frame['close'] > frame['EMA']) & (frame['EMA'] > frame['EMA'].shift(5))
        downtrend = (frame['close'] < frame['EMA']) & (frame['EMA'] < frame['EMA'].shift(5))

        # 2. Касание/прокол границы канала на прошлой свече и возврат внутрь канала на текущей
        touch_lower = (frame['low'].shift(1) <= frame[self.bbl_col].shift(1)) & (frame['close'] > frame[self.bbl_col])
        touch_upper = (frame['high'].shift(1) >= frame[self.bbu_col].shift(1)) & (frame['close'] < frame[self.bbu_col])

        # 3. Разворот импульса по MACD
        macd_up = frame['macd_hist'] > frame['macd_hist_sh1']
        macd_down = frame['macd_hist'] < frame['macd_hist_sh1']

        # 4. Фильтр минимального потенциала сделки (защита от комиссий):
        # Расстояние от текущей цены до противоположной границы канала должно быть минимум 1.5 * ATR
        min_profit_room_buy = (frame[self.bbu_col] - frame['close']) >= (frame['ATR'] * 1.5)
        min_profit_room_sell = (frame['close'] - frame[self.bbl_col]) >= (frame['ATR'] * 1.5)

        # 5. Немного строже фильтр RSI (отсекаем слабые отскоки)
        buy_cond = (
            touch_lower &
            (frame['RSI'] < (self.rsi_open - 3)) &
            macd_up &
            (is_flat | uptrend) &
            min_profit_room_buy
        )
        sell_cond = (
            touch_upper &
            (frame['RSI'] > (self.rsi_sell + 3)) &
            macd_down &
            (is_flat | downtrend) &
            min_profit_room_sell
        )

        frame['signal'] = np.select([buy_cond, sell_cond], ["Open_buy", "Open_sell"], default="NaN")
        return frame


    def close_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        # Отдаём закрытие динамическому TP (BBU/BBL) и Trailing Stop,
        # чтобы не резать прибыль на средней линии BBM
        frame['close_signal'] = "NaN"
        return frame

    def sltp_startegy(self, frame: pd.DataFrame, atr_mult: float = 2.5):
        super().sltp_startegy(frame)
        if frame.empty:
            return
        df = frame.iloc[-1]
        try:
            close_p = float(df['close'])
            atr = float(df['ATR'])
            self.buy_sl = close_p - (atr * atr_mult)
            self.buy_tp = float(df[self.bbu_col])

            self.sell_sl = close_p + (atr * atr_mult)
            self.sell_tp = float(df[self.bbl_col])

            signal = df.get('signal', "NaN")
            self.stop_loss = self.sell_sl if signal == "Open_sell" else self.buy_sl
            self.take_profit = self.sell_tp if signal == "Open_sell" else self.buy_tp
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка расчёта SL/TP: {e}")

