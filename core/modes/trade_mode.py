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
    def __init__(self, symbol, strategy):
        super().__init__(symbol, strategy)
    
    # Открытие позиции
    def open_position_signal_checker(self, symbol, current_price, signal, atr_value):
        super().open_position_signal_checker()
        if type(self.order) != Order:
            if (signal == "Open_buy" or (gv.global_args.buy_sell == True and signal == "Open_sell")):
                logger.info(str(symbol) + ": Signal to open position find: " + signal)
                if risk_manager.is_tradable():
                    logger.info("Risk manager checker: Ok.")
                    self.order = Order(current_price, symbol, atr_value, isbuy= True if signal == "Open_buy" else False)
                    self.order.open_position()
                    self.locker.is_bar_locked = True
                    self.frame = self.position_id_in_frame(self.order, self.frame, self.is_order_open)

    # Проверка закрытия сделки buy
    def close_position_signal_checker(self, symbol, close_signal):
        super().close_position_signal_checker()
        if type(self.order) == Order and (close_signal == "Close_buy" or (gv.global_args.buy_sell == True and close_signal == "Close_sell")):
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            self.order.close_position()
            self.order = None

    # Функция Trailing stop
    def trailing_stop_checker(self, current_price):
        super().trailing_stop_checker()
        if type(self.order) == Order and gv.global_args.trailing_stop != 0:
            self.order.traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, current_price, signal, atr_value, close_signal):
        super().signals_handler()
        try:      
            if not self.locker.is_bar_locked:
                self.open_position_signal_checker(symbol, current_price, signal, atr_value)

                self.close_position_signal_checker(symbol, close_signal)

                self.trailing_stop_checker(current_price)

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")
                    
    def sl_tp_checker():
        pass

