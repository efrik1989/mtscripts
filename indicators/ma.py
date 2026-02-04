import numpy as np
import pandas as pd
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

from models.indicator import Indicator

"""
timeframe - от 1 минуты до 1 месяца примеры тут https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py
window - число значений для расчета обозначается как окно.
"""
class MA(Indicator):

    def __init__(self, name:str, period:int, in_type):
        super().__init__(name, period)
        self.in_type = in_type

    def get_MA_values(self, period):
            if period == "all" or period == None or period == "":
                return self.frame
            elif period > 0:
                 return self.frame.tail(period)
    # Обновление значении индикатора        
    def update_values(self, frame):
        logger.info("MA Начато обновление данных.")
        if (self.in_type == "ema"):
            frame = self.update_ema(frame)
        elif (self.in_type == "sma"):
            frame = self.update_sma(frame)     
        return frame
    
    
    def update_ema(self, frame: pd.DataFrame):
         frame['MA'] = frame['close'].ewm(span=self.period, adjust=False).mean()
         return frame
    
    def update_sma(self, frame):
        close_pos_list = frame['close']

        numbers_series = pd.Series(close_pos_list)
        windows= numbers_series.rolling(self.period)
        moving_avarages = windows.mean()
        moving_avarages_list = moving_avarages.tolist()
        frame[self.name] = moving_avarages_list
        return frame