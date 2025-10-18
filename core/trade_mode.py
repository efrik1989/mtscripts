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

class Trade_mode(Mode):
    def __init__(self, symbol, indicators):
        super().__init__(symbol, indicators)

    def buy_signal_checker(self, symbol, current_price, signal, atr_value):
         if not self.is_order_open  and signal == "Open_buy":
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            if risk_manager.is_tradable():
                order_buy = Order(current_price, symbol, atr_value)
                order_buy.position_open(True, False)
                frame = self.position_id_in_frame(order_buy, frame, self.is_order_open)
                
    def sell_signal_checker(self, symbol, current_price, signal, atr_value):
         if (not self.is_order_open and signal == "Open_sell") and gv.global_args.buy_sell == True:
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            if risk_manager.is_tradable():
                order_sell = Order(current_price, symbol, atr_value)
                order_sell.position_open(False, True)
                frame = self.position_id_in_frame(order_sell, frame, self.is_order_open)
                
    def close_byu_signal_checker(self, symbol, close_signal):
         if self.is_order_open and close_signal == "Close_buy":
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            order_buy.position_close()
            order_buy = None
                
    def close_sell_signal_checker(self, symbol, close_signal):
         if (self.is_order_open and close_signal == "Close_sell") and gv.global_args.buy_sell == True:
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            order_sell.position_close() 
            order_sell = None

    def buy_trailing_stop_checker(self, current_price):
         if type(self.order_buy) == Order and gv.global_args.trailing_stop != 0:
            self.order_buy.traling_stop(current_price, gv.global_args.trailing_stop)

    def sell_trailing_stop_checker(self, current_price):
        if type(self.order_sell) == Order and gv.global_args.trailing_stop != 0:
            self.order_sell.traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, current_price, signal, atr_value, close_signal):
        try:      
            if not self.locker.is_bar_locked:
                self.buy_signal_checker(symbol, current_price, signal, atr_value)
                self.sell_signal_checker(symbol, current_price, signal, atr_value)

                self.close_byu_signal_checker(symbol, current_price, close_signal)
                self.close_sell_signal_checker(symbol, current_price, close_signal)

                self.buy_trailing_stop_checker(current_price)
                self.sell_trailing_stop_checker(current_price)

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")
                    
    def sl_tp_for_buy_checker():
        pass

    def sl_tp_for_sell_checker():
        pass            
