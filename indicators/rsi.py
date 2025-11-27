from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

from models.indicator import Indicator

class RSI(Indicator):
    def __init__(self, name, period, ema):
        self.name = name
        self.period = period
        self.ema = ema

    def update_values(self, frame):
        logger.info("update_RSI_values(): Начато обновление данных RSI.")
        close_delta = frame['close'].diff()
        # Делаем две серий: одну для низких закрытий и одну для высоких закрытий
        up = close_delta.clip(lower=0)
        down = -1 * close_delta.clip(upper=0)
        
        if self.ema == True:
        # Использование экспоненциальной скользящей средней
            ma_up = up.ewm(com = self.period - 1, adjust=True, min_periods = self.period).mean()
            ma_down = down.ewm(com = self.period - 1, adjust=True, min_periods = self.period).mean()
        else:
            # Использование простой скользящей средней
            ma_up = up.rolling(window = self.period, adjust=False).mean()
            ma_down = down.rolling(window = self.period, adjust=False).mean()
            
        rsi = ma_up / ma_down
        rsi = 100 - (100/(1 + rsi))
        frame[self.name] = rsi
        logger.info("update_RSI_values(): Закончено обновление данных RSI.")
        return frame
    
    # Функция опрделения точки выходи из сделки
    # Это порно конечно т.к. RSI вспомомгательный осцилятор.
    # TODO: Его надо с чем-то комбинировать.
    def strategy(self, frame):
        logger.info("RSI update strategy: start")
        conditions = [
            (frame[self.name] > 70),
            ((frame[self.name] < 30))]
        chois = ["Close_buy", "Close_Sell"]
        frame['close_signal'] = np.select(conditions, chois, default="NaN")
        logger.info("RSI update strategy: done")
        return frame
