from abc import ABCMeta, abstractmethod, abstractproperty
import time
import pandas as pd
from pandas.plotting import register_matplotlib_converters
import numpy as np

from metatrader5EasyT import tick
from core.trade_locker import Locker
import core.app_logger as app_logger
from models.order import Order
from core.mt5_actions import MT5_actions as mt5_a   

logger=app_logger.get_logger(__name__)

import core.global_vars as gv

import core.risk_manager as risk_m
risk_manager = risk_m.RiskManager(gv.global_args.monney_manager, gv.global_args.lost_risk)

class Mode():
    __metaclass__=ABCMeta
    def __init__(self, symbol, indicators ):
        self.symbol = symbol
           
        mt5_a.selectSymbol(self.symbol)
        self.frame = mt5_a.get_rates_frame(self.symbol, 2, gv.global_args.range, gv.global_args.timeframe)
        
        #TODO: RiskManager не должен создаваться для каждого инструмента он единый должен быть...
        self.tick_obj = tick.Tick(self.symbol)
        self.indicators = indicators
        self.is_order_open = mt5_a.check_order(self.symbol)
        self.order_sell = None
        self.order_buy = None
        self.locker = Locker()
        self.locker.is_bar_locked = False

        self.lets_trade(self.symbol)

    # Основная функция с логикой торговли
    def lets_trade(self, symbol):
        """Метод с основной логикой купли продажи по сигналам."""
        while True:
            time.sleep(1)
            if not risk_manager.is_equity_satisfactory():
                raise Exception("Balance is too low!!!")
            
            self.frame = self.update_all_frame(symbol, self.frame, self.indicators, self.is_order_open, self.locker, self.order_buy, self.order_sell, index=np.array(self.frame.index)[-1] + 1)

            # TODO: Возможно стоит ATR записывать в 2 отдельныйх столбца SL и TP. 
            # А затем пост обработкой все значения кроме тех где сигнал на покупку\продажу выставлять NaN. Для более простого анализа.
            signal = self.get_last_column_value(self.frame, 'signal')
            close_signal = self.get_last_column_value(self.frame, 'signal')
            atr_value = float(self.get_last_column_value(self.frame, 'ATR') * 2)    
            current_price = mt5_a.get_price(self.tick_obj)
           
            self.signals_handler(symbol, current_price, signal, atr_value, close_signal)

    def update_all_frame(self, symbol, frame, indicators, is_order_open, locker: Locker, order_buy, order_sell, index):
        """Метод обновления фрейма."""
        last_bar_frame = mt5_a.get_last_bar(symbol, gv.global_args.timeframe, index)
        if self.is_need_update_lst_bar(symbol, frame, last_bar_frame):
            frame = self.update_frame_startegy(symbol, frame, last_bar_frame, indicators)
            # TODO: Priority: 3 Можно оставить один если будет только order.
            frame = self.position_id_in_frame(order_buy, frame, is_order_open)
            frame = self.position_id_in_frame(order_sell, frame, is_order_open)
            frame.to_excel(gv.global_args.logs_directory + '\\frames\\out_' + str(symbol) + '_MA50_frame_signal_test.xlsx')
            logger.info(f"{str(symbol)}: Frames update complete. Frame in: {gv.global_args.logs_directory}\\frames\\{str(symbol)}_MA50_RSI_ATR_signals_test.xlsx to manual analis.")
            locker.is_bar_locked = False
            return frame
        return frame
        
        # Проверка нужно ли обновление фрэйма
    def is_need_update_lst_bar(self, symbol, frame: pd.DataFrame, last_bar_frame):
        """МЕтод проверки необходимости обновлять фрэйм."""
        try:
            if frame.empty:
                    logger.critical(str(symbol) + ": is_need_update_lst_bar(): Frame is empty!")
            
            last_bar_time = np.array(last_bar_frame['time'])[-1]
            last_bar_time_frame = np.array(frame['time'].tail(1))[-1]
            if np.array(last_bar_time_frame < last_bar_time):
                return True
            else:
                return False
        except(AttributeError):
            logger.critical(str(symbol) + ": is_need_update_lst_bar(): 1 оr more objects become 'None/Null'")

    def update_frame_startegy(self, symbol, frame: pd.DataFrame, last_bar_frame, indicators):
        """Метод обновления фрейма стратегиями"""
        try:    
                frame = pd.concat([frame, last_bar_frame], ignore_index=True)
                for indicator in indicators:
                    frame = indicator.update_values(frame)
                    frame = indicator.strategy(frame)
                    
                return frame
        except(AttributeError):
            logger.critical(str(symbol) + ": 1 оr more objects become 'None/Null'")


    def isCondition(self, frame, index, order_id):
        # Выглядит как какое-то порно... Надо подумамть.
        val = "NaN"
        if index == len(frame['target']) - 1: 
            val = order_id
        return val

    def position_id_in_frame(self, order: Order, frame: pd.DataFrame, is_order_open):
        """Метод обновления фрейма id открытыми позициями"""
        if type(order) == Order or is_order_open:
            value = order.id
        else:
            value = "NaN"

        if 'order_id' in frame.columns:
            frame.loc[frame.index[-1], 'order_id'] = value
            logger.info("order_id обновлен.")
        else:
            logger.info("Столбец 'order_id' не существует и будет создан.")
            close_ser = frame['target'].to_list()
            is_opened_list = []
            for index, item in enumerate(close_ser):
                is_opened_list.append(self.isCondition(frame, index, value))
            frame['order_id'] = is_opened_list
        return frame
    
    def get_last_column_value(self, frame, column: str):
        try:
            signal = np.array(frame[column])[-1]
            return signal
        except(KeyError):
            logger.warning("Отсутствую сигналы на закрытие или открытие. Рекомендуется ожидание сигналов.")
            return None

    @abstractmethod
    def buy_signal_checker():
        """Проверка сигнала к открытию Buy"""

    @abstractmethod
    def sell_signal_checker():
        """Проверка сигнала к открытию Sell"""
    
    @abstractmethod
    def close_byu_signal_checker():
        """Проверка закрытия сделки buy"""

    @abstractmethod
    def close_sell_signal_checker():
        """Проверка сигнала к закрытию сделки sell"""

    @abstractmethod
    def sl_tp_for_buy_checker():   
        """Проверка SLTP buy"""
    
    @abstractmethod
    def sl_tp_for_sell_checker():
        """Проверка SLTP sell"""
    
    @abstractmethod
    def buy_trailing_stop_checker():
        """Функция Trailing stop buy"""

    @abstractmethod
    def sell_trailing_stop_checker():
        """Функция Trailing stop sell"""

    @abstractmethod
    def signals_handler():
        """Функция Обработки сигналов"""