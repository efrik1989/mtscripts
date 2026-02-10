from abc import ABCMeta, abstractmethod, abstractproperty
import time
import pandas as pd
from pandas.plotting import register_matplotlib_converters
import numpy as np

from metatrader5EasyT import tick
from core.trade_locker import Locker
import core.app_logger as app_logger
from models.order import Order
from models.strategy import Strategy
from mt5.mt5_actions import MT5_actions as mt5_a   

logger=app_logger.get_logger(__name__)

import core.global_vars as gv

import core.risk_manager as risk_m

# Абстрактный класс родитель для режимов запуска.
class Mode():
    __metaclass__=ABCMeta
    def __init__(self, symbol, strategy: Strategy ):
        self.symbol = symbol
           
        mt5_a.selectSymbol(self.symbol)
        self.frame = mt5_a.get_rates_frame(self.symbol, 2, gv.global_args.range, gv.global_args.timeframe)
        
        self.tick_obj = tick.Tick(self.symbol)
        self.strategy = strategy
        self.is_order_open = mt5_a.check_order(self.symbol)
        self.order = None
        self.locker = Locker()
        self.locker.is_bar_locked = False
        self.profit = 0
        self.efficiency = 0
        self.orders_count = 0
        self.profit_orders_count = 0
        #TODO: RiskManager не должен создаваться для каждого инструмента он единый должен быть...
        self.risk_manager = risk_m.RiskManager(gv.global_args.monney_manager, gv.global_args.lost_risk)

        self.lets_trade(self.symbol)

    # Ограничитель в 5000 строк для DataFrame, для сбоерегания ресурсов
    def check_frame_len(self, frame: pd.DataFrame):
        if len(frame) > 5000:
            frame = frame.tail(5000)
            logger.info("Фрэйм обрезан до 5000 строк с конца.")
        return frame

    # Основная функция с логикой торговли
    def lets_trade(self, symbol):
        """Метод с основной логикой купли продажи по сигналам."""
        
        while True:
            time.sleep(1)
            # Проверяем флаг ПЕРЕД любыми действиями (очень быстро)
            if not self.risk_manager.trading_allowed.is_set():
                logger.critical(f"Поток {symbol}: Торговля заблокирована риск-менеджером.")
                time.sleep(1)
                continue
            
            self.frame = self.update_all_frame(symbol, self.frame, self.strategy, self.is_order_open, self.locker, self.order, index=np.array(self.frame.index)[-1] + 1)
            
            # TODO: Возможно стоит ATR записывать в 2 отдельныйх столбца SL и TP. 
            # А затем пост обработкой все значения кроме тех где сигнал на покупку\продажу выставлять NaN. Для более простого анализа.
            signal = self.get_last_column_value(self.frame, 'signal')
            close_signal = self.get_last_column_value(self.frame, 'close_signal')
            atr_value = float(self.get_last_column_value(self.frame, 'ATR') * 4)    
            current_price = mt5_a.get_price(self.tick_obj)
            # Отладочный 
            # signal = "Open_buy"
            # close_signal = "Close_buy"
            logger.debug(f"Signal: {signal}, Close_signal: {close_signal}, ATR: {atr_value}, Current price: {current_price}")
           
            self.signals_handler(symbol, current_price, signal, atr_value, close_signal)

    def update_all_frame(self, symbol, frame, strategy, is_order_open, locker: Locker, order, index):
        """Метод обновления фрейма."""
        last_bar_frame = mt5_a.get_last_bar(symbol, gv.global_args.timeframe, index)
        if self.is_need_update_lst_bar(symbol, frame, last_bar_frame):
            frame = self.update_frame_startegy(symbol, frame, last_bar_frame, strategy)
            # TODO: До делать метод  а то получается он сейчас не делает ничего...
            # frame = self.position_id_in_frame(order, frame, is_order_open)
            frame.to_excel(f"{gv.global_args.logs_directory}\\frames\\out_{symbol}_{gv.global_args.strategy}_frame_signal_test.xlsx")
            logger.info(f"{str(symbol)}: Frames update complete. Frame in: {gv.global_args.logs_directory}\\frames\\out_{symbol}_{gv.global_args.strategy}_frame_signal_test.xlsx to manual analis.")
            locker.is_bar_locked = False
            return self.check_frame_len(frame)
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

    def update_frame_startegy(self, symbol, frame: pd.DataFrame, last_bar_frame, strategy: Strategy):
        """Метод обновления фрейма стратегиями"""
        try:    
                frame = pd.concat([frame, last_bar_frame], ignore_index=True)
                frame = strategy.update_values(symbol, frame, last_bar_frame)
                # Для отладки frame.to_excel(gv.global_args.logs_directory + '\\frames\\out_' + str(symbol) + '.xlsx')
                frame = strategy.update_strategy(frame)
                    
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
            # TODO: Реализация ниже подхоит только для одной стратегии. Переделать надо...
            # close_ser = frame['target'].to_list()
            # is_opened_list = []
            # for index, item in enumerate(close_ser):
            #     is_opened_list.append(self.isCondition(frame, index, value))
            # frame['order_id'] = is_opened_list
        return frame
    
    def get_last_column_value(self, frame, column: str):
        try:
            signal = np.array(frame[column])[-1]
            return signal
        except(KeyError):
            logger.warning("Отсутствую сигналы на закрытие или открытие. Рекомендуется ожидание сигналов.")
            return None
        
    def close_position_by_sltp(self, symbol, current_price):
        logger.info(str(symbol) + ": Signal to close position find: SLTP")
        self.profit += self.order.fake_buy_sell_close(current_price)
        self.order = None
    
    @abstractmethod
    def close_position_signal_checker(self):
        logger.debug("Проверка закрытия сделки ")

    @abstractmethod
    def sl_tp_checker(self):   
        logger.debug("Проверка SLTP")
    
    @abstractmethod
    def trailing_stop_checker(self):
        logger.debug("Функция Trailing stop")

    @abstractmethod
    def signals_handler(self):
        logger.debug("Функция Обработки сигналов")
    
    @abstractmethod
    def open_position_signal_checker(self):
        logger.debug("Функция Обработки сигнала на открытие сделки")