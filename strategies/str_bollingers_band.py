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
logger=app_logger.get_logger(__name__)

# TODO: Стратегию есть куда улучшить!!!
# Есть идея отсекать или как-то помечать тренды, чтобы не открывать сделки в противоположный тренд.
# Или не открывать сделки при сильном тренде, а только в период консолидации и на проколах. 
#  
# Класс описывающий поведение стратегии(Покупка\Продажа) с Bollingers_bands
class Strategy_BB(Strategy):
        def __init__(self, period, rsi_open, adx_open, open_triger: str, close_triger: str):
                super().__init__(period)
                self.indicators = [Bollinger("BB", period), 
                                   RSI("RSI", 11, True), 
                                   # MACD изначальные параметры 12, 26, 9
                                   MACD('MACD', 12, 8, 21, 5), 
                                   ADX('ADX', 16), 
                                   ATR("ATR", 14), MA("EMA", 200, "ema")]
                self.rsi_open = rsi_open
                self.adx_open = adx_open
                self.open_triger = open_triger
                self.close_triger = close_triger

        # Проставление сигналов открытия сделок
        def open_strategy(self, frame):
            logger.info("BB strategy: start frame analis...")

            condition_macd_confirm = (frame['ADX'] >= 17) & \
                         (frame['ADX'] < 25) & \
                         (frame['macd_hist'] > frame['macd_hist_sh1'])

            condition_strong_trend = (frame['ADX'] >= 25)
            
            conditions = [
                (frame[self.open_triger] <= frame['BBL_16_2.0_2.0']) & 
                (frame['RSI'] < self.rsi_open) &
                (frame['ADX'] > self.adx_open) &
                # condition_ema_filter &
                (condition_macd_confirm | condition_strong_trend)
                ,
                (frame['high'] >= frame['BBU_16_2.0_2.0']) & 
                (frame['RSI'] > 75) & 
                (frame['ADX'] > 18) &
                (frame['macd_hist'] < frame['macd_hist_sh1'])]
            chois = ["Open_buy", "Open_sell"]
            frame['signal'] = np.select(conditions, chois, default="NaN")   
            return frame
        
        # Проставление сигналов закрытия сделок
        def close_strategy(self, frame):
            conditions = [
                (frame['close'] >= frame['BBM_16_2.0_2.0']),
                (frame['close'] <= frame['BBM_16_2.0_2.0']) & (frame['ADX'] < 25)
                ]
            chois = ["Close_buy", "Close_sell"]
            frame['close_signal'] = np.select(conditions, chois, default="NaN")

            logger.info("strategy: Analis complete.")
            return frame
        
        # Помечаем значения SLTP для данной стратегии    
        def sltp_startegy(self, frame: pd.DataFrame):
            super().sltp_startegy(frame)
            df = frame.tail(1)
            try:
                self.stop_loss = df['BBM_16_2.0_2.0'].item()
                self.take_profit = df['BBU_16_2.0_2.0'].item()
            except:
                 logger.warning("Нет значенийй BBM/BBU.")