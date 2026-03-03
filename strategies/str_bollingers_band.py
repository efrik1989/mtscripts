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


# Класс описывающий поведение стратегии(Покупка\Продажа) с Bollingers_bands
# MACD("MACD", None, 8, 17, 9) еще раздумываю добавить ли индикатор в стратегию
class Strategy_BB(Strategy):
        def __init__(self, period, rsi_open, adx_open, open_triger: str, close_triger: str):
                super().__init__(period)
                self.indicators = [Bollinger('BB', period), 
                                   RSI("RSI", 14, True), 
                                   MACD('MACD', 12, 12, 26, 9), 
                                   ADX('ADX', 14), 
                                   ATR("ATR", 14), MA("EMA", 200, "ema")]
                self.rsi_open = rsi_open
                self.adx_open = adx_open
                self.open_triger = open_triger
                self.close_triger = close_triger


        # TODO: Прописать суммарные сигналы для BB, MACD, RSI   
        # Проставление сигналов открытия сделок
        def open_strategy(self, frame):
            logger.info("BB strategy: start frame analis...")

            # frame['atr_ma'] = frame['ATR'].rolling(window=100).mean()
            # volatility_filter = frame['ATR'] > frame['atr_ma']
                
            
            # ADX '(frame['ADX'] > 18)' заменяем на 'ATR frame['ATR'] > frame['atr_ma']'
            # MACD long (frame['macd_hist'] > frame['macd_hist_sh1']) short (frame['macd_hist'] < frame['macd_hist_sh1'])
            #Вариант 2. Long - RSI < 45 & ADX > 15 & (frame['macd_hist'] > frame['macd_hist_sh1']) 65% эффективности.
            #Вариант 3. (пока фаворит) 64,6% эффективности, но сделок больше в 2 раза.
            condition_macd_confirm = (frame['ADX'] >= 15) & \
                         (frame['ADX'] < 25) & \
                         (frame['macd_hist'] > frame['macd_hist_sh1'])

            # Условие Б: Сильный тренд, где MACD можно игнорировать
            condition_strong_trend = (frame['ADX'] >= 25)
            # Вариант 4: Результат: отсеклась львиная часть сделок, на некоторыхх инструментах повысилась эффективность. Но прибыль рухнула в 3 раза.
            # condition_ema_filter = (frame['close'] > frame['EMA'])
            # open rsi < 45, adx >18
            

            conditions = [
                (frame[self.open_triger] <= frame['BBL_20_2.0_2.0']) & 
                (frame['RSI'] < self.rsi_open) & 
                (frame['ADX'] > self.adx_open) &
                (condition_macd_confirm | condition_strong_trend),
                (frame['high'] >= frame['BBU_20_2.0_2.0']) & 
                (frame['RSI'] > 75) & 
                (frame['ADX'] > 18) &
                (frame['macd_hist'] < frame['macd_hist_sh1'])]
            chois = ["Open_buy", "Open_sell"]
            frame['signal'] = np.select(conditions, chois, default="NaN")   
            return frame
        
        # Проставление сигналов закрытия сделок
        def close_strategy(self, frame):
            # Выход.
            # Вариант 1:
            # TODO: [Priority: 1]Допилить стратегию выхода
            condition_rsi_momentum = (frame['RSI'] >= 60) & (frame['RSI'] < 70)
            condition_macd_hold = (frame['macd_hist'] > frame['macd_hist_sh1']) | \
                      (frame['macd_hist'] > 0)
            
            conditions = [
                # Попытка отключить Close_buy и проверить как себя поведет стратегия в симуляции
                # (0 > 2)
                (frame['close'] >= frame[f'{self.close_triger}_20_2.0_2.0']) &
                (frame['macd_hist'] < frame['macd_hist_sh1']) &
                # Условия ниже нужны. но нужно доработать адаптивность TP и трэйлинг-стоп по ATR.
                (frame['ADX'] < 30)
                # ~(condition_macd_hold | condition_rsi_momentum)
                ,
                (frame['close'] <= frame['BBM_20_2.0_2.0']) & (frame['ADX'] < 25)
                ]
            chois = ["Close_buy", "Close_sell"]
            frame['close_signal'] = np.select(conditions, chois, default="NaN")

            logger.info("strategy: Analis complete.")
            return frame
            
        def sltp_startegy(self, frame: pd.DataFrame):
            super().sltp_startegy(frame)
            df = frame.tail(1)
            try:
                self.stop_loss = df['BBM_20_2.0_2.0'].item()
                self.take_profit = df['BBU_20_2.0_2.0'].item()
            except:
                 logger.warning("Нет значенийй BBM/BBU.")