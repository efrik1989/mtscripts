from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

from models.indicator import Indicator

"""
timeframe - от 1 минуты до 1 месяца примеры тут https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py
window - число значений для расчета обозначается как окно.
"""
class MA(Indicator):

    def __init__(self, name:str, window:int):
        self.name = name
        self.window = window

    def get_MA_values(self, period):
            if period == "all" or period == None or period == "":
                return self.frame
            elif period > 0:
                 return self.frame.tail(period)
            
    def update_values(self, frame):
        close_pos_list = frame['close']
        window_size = self.window

        numbers_series = pd.Series(close_pos_list)
        windows= numbers_series.rolling(window_size)
        moving_avarages = windows.mean()
        moving_avarages_list = moving_avarages.tolist()
        frame[self.name] = moving_avarages_list
        return frame
    
    # Стратегия подсвечивает сигналы при работе с индикатором MA50 на исторических данных
    def strategy(self, frame):
        logger.info("strategy: start frame analis...")
        frame['diff'] = pd.to_numeric(frame['close']) - pd.to_numeric(frame[self.name])
        # TODO: Priority: 1 [general] Определение тренда хромает. Для направления сделки этого маловато. Нужно расчитать вектор, куда идет тренд.
        frame['trend'] = pd.Series(frame['diff']) > 0
        frame['MA_day_befor3'] = frame[self.name].shift(3)
        frame['MA_trend'] = np.array(frame[self.name]) > np.array(frame['MA_day_befor3'])

        d = {True: 'UP', False: 'DOWN'}
        frame['trend'] = frame['trend'].map(d)
        frame['MA_trend'] = frame['MA_trend'].map(d)

        # В отдельную функцию вынести
        frame['target'] = (pd.to_numeric(frame['low']) < frame[self.name]) & ( frame[self.name]< pd.to_numeric(frame['high']))
        # Трагет вчерашнего бара, позовчерашнего и т.д. 
        frame['target_day_befor_1'] = frame['target'].shift(1)
        # frame['target_day_befor_2'] = frame['target'].shift(2)
        # frame['target_day_befor_3'] = frame['target'].shift(3)
        
        # Цена закрытия вчерашнего бара, позовчерашнего и тд.
        frame['close_day_befor_1'] = frame['close'].shift(1)
        # frame['close_day_befor_2'] = frame['close'].shift(2)
        # frame['close_day_befor_3'] = frame['close'].shift(3)
        
        # Цена открытия вчерашнего бара, позовчерашнего и тд
        frame['open_day_befor_1'] = frame['open'].shift(1)
        # frame['open_day_befor_2'] = frame['open'].shift(2)
        # frame['open_day_befor_3'] = frame['open'].shift(3)

        # Ну вроде как ок. стоит зафиксировать!!!
        # Логика такая: Прокол т.е. (low < MA < high), затем следующий бар выше MA, и цена закрытия выше цены открытия если trend == UP и MA_trend == UP 
        # и наоборот если DOWN, тогда кидаем сигнал на открытие сделки 
        # trend - показывает цена ниже или выше MA
        # MA_trend - показывает направление тренда. без учетта консолидации к сожалению.
        conditions = [
            (frame['target_day_befor_1'] == True) & (frame['trend'] == "UP") & (frame['close'] > frame[self.name]) 
                & (frame['open'] < frame['close']),
            (frame['target_day_befor_1'] == True) & (frame['trend'] == "DOWN") & (frame['close'] < frame[self.name]) 
                & (frame['open'] > frame['close'])]
        chois = ["Open_buy", "Open_sell"]
        frame['signal'] = np.select(conditions, chois, default="NaN")

        logger.info("strategy: Analis complete.")
        return frame