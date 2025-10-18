from pandas.plotting import register_matplotlib_converters
from core import risk_manager
from models.order import Order

register_matplotlib_converters()

from metatrader5EasyT import tick
from core.mt5_actions import MT5_actions as mt5_a
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)
from core.trade_locker import Locker
from models.mode import Mode

import core.global_vars as gv

# Класс обеспечивающий режим симуляции торговли в реальном времени.
# Создан для проверки работы робота в реальном времени и проверки работы его фич.
# Для полноценной проверки стратегии в этом режиме, может занять много времени.
class Simulation_mode(Mode):
    # Передаваемые параметры снаружи symbol, indicators, 
    def __init__(self, symbol, indicators):
        super().__init__(symbol, indicators)
    
    # Проверка сигнала к открытию Buy
    def buy_signal_checker(self, symbol, current_price, signal, atr_value):
        if type(self.order_buy) != Order and signal == "Open_buy":
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            if risk_manager.is_tradable():
                self.order_buy = Order(current_price, symbol, atr_value)
                self.order_buy.fake_buy()
                self.locker.is_bar_locked = True
                frame = self.position_id_in_frame(self.order_buy, frame, self.is_order_open)

    # Проверка сигнала к открытию Sell
    def sell_signal_checker(self, symbol, current_price, signal, atr_value):
        if gv.global_args.buy_sell == True and (type(self.order_sell ) != Order and signal == "Open_sell"):
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            if risk_manager.is_tradable():
                self.order_sell = Order(current_price, symbol, atr_value)
                self.order_sell.fake_sell()
                self.locker.is_bar_locked = True
                frame = self.position_id_in_frame(self.order_sell, frame, self.is_order_open)

    # Проверка закрытия сделки buy
    def close_byu_signal_checker(self, symbol, current_price, close_signal):
        if type(self.order_buy) == Order and close_signal == "Close_buy":
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            self.order_buy.fake_buy_sell_close(current_price)
            self.order_buy = None

    # Проверка сигнала к закрытию сделки sell
    def close_sell_signal_checker(self, symbol, current_price, close_signal):
        if (type(self.order_sell) == Order and close_signal == "Close_sell"):
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            self.order_sell.fake_buy_sell_close(current_price)
            self.order_sell = None
    
    # Проверка SLTP buy
    def sl_tp_for_buy_checker(self, symbol, current_price):   
        if (type(self.order_buy) == Order and (current_price >= self.order_buy.take_profit or current_price <= self.order_buy.stop_loss )):
            logger.info(str(symbol) + ": Signal to close position find: SLTP")
            self.order_buy.fake_buy_sell_close(current_price)
            self.order_buy = None

    # Проверка SLTP sell
    def sl_tp_for_sell_checker(self, symbol, current_price):
        if (type(self.order_sell) == Order and (current_price <= self.order_sell.take_profit or current_price >= self.order_sell.stop_loss )):
            logger.info(str(symbol) + ": Signal to close position find: SLTP")
            self.order_sell.fake_buy_sell_close(current_price)
            self.order_sell = None

    # Функция Trailing stop buy
    def buy_trailing_stop_checker(self, current_price):
        if type(self.order_buy) == Order and gv.global_args.trailing_stop != 0:
            self.order_buy.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    # Функция Trailing stop sell
    def sell_trailing_stop_checker(self, current_price):   
        if type(self.order_sell) == Order and gv.global_args.trailing_stop != 0:
            self.order_sell.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, current_price, signal, atr_value, close_signal):
        try:      
            if not self.locker.is_bar_locked:
                self.buy_signal_checker(symbol, current_price, signal, atr_value)
                self.sell_signal_checker(symbol, current_price, signal, atr_value)

                self.close_byu_signal_checker(symbol, current_price, close_signal)
                self.close_sell_signal_checker(symbol, current_price, close_signal)

                self.sl_tp_for_buy_checker(symbol, current_price)
                self.sl_tp_for_sell_checker(symbol, current_price)

                self.buy_trailing_stop_checker(current_price)
                self.sell_trailing_stop_checker(current_price)

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")
