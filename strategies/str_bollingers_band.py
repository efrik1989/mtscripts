import numpy as np
from indicators.macd import MACD
from models.strategy import Strategy
import core.app_logger as app_logger
from indicators.rsi import RSI
from indicators.atr import ATR
from indicators.bollinger_bands import Bollinger

logger=app_logger.get_logger(__name__)


# Класс описывающий поведение стратегии(Покупка\Продажа) с Bollingers_bands
# MACD("MACD", None, 8, 17, 9) еще раздумываю добавить ли индикатор в стратегию
class Strategy_BB(Strategy):
        def __init__(self, period):
                super().__init__(period)
                self.indicators = [Bollinger('BB', period), RSI("RSI", 14, True), ATR("ATR", 14)]


        # TODO: Прописать суммарные сигналы для BB, MACD, RSI   
        # Проставление сигналов открытия сделок
        def open_strategy(self, frame):
            logger.info("BB strategy: start frame analis...")
            
            """frame['close_day_befor_1'] = frame['close'].shift(1)
            frame['close_day_befor_2'] = frame['close'].shift(2)
            
            frame['MA_day_befor_1'] = frame['MA'].shift(1)
            frame['MA_day_befor_2'] = frame['MA'].shift(2)"""

            # Добавил RSI и вообще все перестало работать.
            """
            df['signal_buy'] = (df['close'] < df['BBL_20_2.0']) & (df['RSI_14'] < 30)

            # Условия для продажи (Short)
            df['signal_sell'] = (df['close'] > df['BBU_20_2.0']) & (df['RSI_14'] > 70)

            # Выход из сделки (пример по средней линии)
            df['exit_long'] = df['close'] >= df['BBM_20_2.0']
            """
            conditions = [
                (frame['close'] < frame['BBL_20_2.0_2.0']) & (frame['RSI'] < 30) & (frame['RSI'] < 30),
                (frame['close'] > frame['BBU_20_2.0_2.0']) & (frame['RSI'] > 70)]
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
            