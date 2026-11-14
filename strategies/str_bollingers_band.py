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
        # Оставляем твои проверенные фильтры с 60% винрейтом
        is_tradeable_regime = (frame['ADX'] < 35) | (frame['ADX'] < frame['ADX'].shift(1))

        lower_breaches = (frame['close'] < frame[self.bbl_col]).rolling(8).sum()
        upper_breaches = (frame['close'] > frame[self.bbu_col]).rolling(8).sum()
        no_cascade_down = lower_breaches <= 1
        no_cascade_up = upper_breaches <= 1

        touch_lower = (
            (frame['low'].shift(1) <= frame[self.bbl_col].shift(1)) &
            (frame['close'] > frame[self.bbl_col]) &
            (frame['close'] > frame['open'])
        )
        touch_upper = (
            (frame['high'].shift(1) >= frame[self.bbu_col].shift(1)) &
            (frame['close'] < frame[self.bbu_col]) &
            (frame['close'] < frame['open'])
        )

        momentum_up = (frame['macd_hist'] > frame['macd_hist_sh1']) & (frame['RSI'] > frame['RSI'].shift(1))
        momentum_down = (frame['macd_hist'] < frame['macd_hist_sh1']) & (frame['RSI'] < frame['RSI'].shift(1))

        min_profit_room_buy = (frame[self.bbm_col] - frame['close']) >= (frame['ATR'] * 1.3)
        min_profit_room_sell = (frame['close'] - frame[self.bbm_col]) >= (frame['ATR'] * 1.3)

        buy_cond = (
            touch_lower &
            (frame['RSI'] < self.rsi_open) &
            momentum_up &
            is_tradeable_regime &
            no_cascade_down &
            min_profit_room_buy
        )
        sell_cond = (
            touch_upper &
            (frame['RSI'] > self.rsi_sell) &
            momentum_down &
            is_tradeable_regime &
            no_cascade_up &
            min_profit_room_sell
        )

        swing_low = np.minimum(frame['low'], frame['low'].shift(1)).fillna(frame['low'])
        swing_high = np.maximum(frame['high'], frame['high'].shift(1)).fillna(frame['high'])

        frame['calc_buy_sl'] = np.clip(
            swing_low - (frame['ATR'] * 0.4),
            frame['close'] - (frame['ATR'] * 1.5),
            frame['close'] - (frame['ATR'] * 1.2)
        )
        frame['calc_sell_sl'] = np.clip(
            swing_high + (frame['ATR'] * 0.4),
            frame['close'] + (frame['ATR'] * 1.2),
            frame['close'] + (frame['ATR'] * 1.5)
        )

        # Ставим дальний тейк-профит (4.5 * ATR), чтобы не резать сильные импульсы,
        # а всю прибыль забирать через трейлинг-стоп движка
        frame['calc_buy_tp'] = frame['close'] + (frame['ATR'] * 4.5)
        frame['calc_sell_tp'] = frame['close'] - (frame['ATR'] * 4.5)

        frame['signal'] = np.select([buy_cond, sell_cond], ["Open_buy", "Open_sell"], default="NaN")
        return frame

    def close_strategy(self, frame: pd.DataFrame) -> pd.DataFrame:
        # Не закрываем сделку на BBM — даем прибыли расти по трейлинг-стопу!
        frame['close_signal'] = "NaN"
        return frame

    def sltp_startegy(self, frame: pd.DataFrame, atr_mult: float = 1.8):
        super().sltp_startegy(frame)
        if frame.empty:
            return

        df = frame.iloc[-1]
        try:
            close_p = float(df['close'])
            atr = float(df['ATR'])

            self.buy_sl = float(df.get('calc_buy_sl', close_p - atr * atr_mult))
            self.buy_tp = float(df.get('calc_buy_tp', df[self.bbu_col]))

            self.sell_sl = float(df.get('calc_sell_sl', close_p + atr * atr_mult))
            self.sell_tp = float(df.get('calc_sell_tp', df[self.bbl_col]))

            signal = df.get('signal', "NaN")
            self.stop_loss = self.sell_sl if signal == "Open_sell" else self.buy_sl
            self.take_profit = self.sell_tp if signal == "Open_sell" else self.buy_tp
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка расчёта SL/TP: {e}")

