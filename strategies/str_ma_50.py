import numpy as np
import pandas as pd
from indicators.atr import ATR
from indicators.ma import MA
from indicators.rsi import RSI
from models.strategy import Strategy

import core.app_logger as app_logger
logger=app_logger.get_logger(__name__)

class Strategy_MA_50(Strategy):
    def __init__(self, period):
        super().__init__(period)
        self.indicators = [MA('MA50', period, "sma"), RSI("RSI14", 14, True), ATR("ATR", 14)]


    def open_strategy(self, frame):
        logger.info("MA strategy: start frame analis...")
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
        # Таргет вчерашнего бара, позовчерашнего и т.д. 
        frame['target_day_befor_1'] = frame['target'].shift(1)
        
        # Цена закрытия вчерашнего бара, позовчерашнего и тд.
        frame['close_day_befor_1'] = frame['close'].shift(1)
        
        # Цена открытия вчерашнего бара, позовчерашнего и тд
        frame['open_day_befor_1'] = frame['open'].shift(1)

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

        logger.info("Open strategy: Analis complete.")
        return frame
    
    # TODO: Вот это надо поправить (frame[self.name] > 70). Уверен на 1000000% это работать не будет.
    def close_strategy(self, frame):
        logger.info("Close strategy update: start")
        conditions = [
            (frame[self.name] > 70),
            ((frame[self.name] < 30))]
        chois = ["Close_buy", "Close_Sell"]
        frame['close_signal'] = np.select(conditions, chois, default="NaN")
        logger.info("Close strategy update: done")
        return frame