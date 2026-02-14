import numpy as np
from models.strategy import Strategy

from indicators.rsi import RSI
from indicators.atr import ATR
from indicators.bollinger_bands import Bollinger
from indicators.macd import MACD
from indicators.adx import ADX

import core.app_logger as app_logger
logger=app_logger.get_logger(__name__)


# Класс описывающий поведение стратегии(Покупка\Продажа) с Bollingers_bands
# MACD("MACD", None, 8, 17, 9) еще раздумываю добавить ли индикатор в стратегию
class Strategy_BB(Strategy):
        def __init__(self, period):
                super().__init__(period)
                self.indicators = [Bollinger('BB', period), RSI("RSI", 14, True), MACD('MACD', 12, 12, 26, 9), ADX('ADX', 14), ATR("ATR", 14)]


        # TODO: Прописать суммарные сигналы для BB, MACD, RSI   
        # Проставление сигналов открытия сделок
        def open_strategy(self, frame):
            logger.info("BB strategy: start frame analis...")

            # frame['atr_ma'] = frame['ATR'].rolling(window=100).mean()
            # volatility_filter = frame['ATR'] > frame['atr_ma']
            
            # ADX '(frame['ADX'] > 18)' заменяем на 'ATR frame['ATR'] > frame['atr_ma']'
            # MACD long (frame['macd_hist'] > frame['macd_hist_sh1']) short (frame['macd_hist'] < frame['macd_hist_sh1'])

            conditions = [
                (frame['low'] <= frame['BBL_20_2.0_2.0']) & 
                (frame['RSI'] < 40) & 
                (frame['ADX'] > 18) &
                (frame['macd_hist'] > frame['macd_hist_sh1']),
                (frame['high'] >= frame['BBU_20_2.0_2.0']) & 
                (frame['RSI'] > 75) & 
                (frame['ADX'] > 18) &
                (frame['macd_hist'] < frame['macd_hist_sh1'])]
            chois = ["Open_buy", "Open_sell"]
            frame['signal'] = np.select(conditions, chois, default="NaN")   
            return frame
        
        # Проставление сигналов закрытия сделок
        def close_strategy(self, frame):
            conditions = [
                (frame['close'] >= frame['BBM_20_2.0_2.0']),
                (frame['close'] <= frame['BBM_20_2.0_2.0'])
                ]
            chois = ["Close_buy", "Close_sell"]
            frame['close_signal'] = np.select(conditions, chois, default="NaN")

            logger.info("strategy: Analis complete.")
            return frame
            