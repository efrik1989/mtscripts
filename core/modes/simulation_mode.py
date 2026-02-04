from pandas.plotting import register_matplotlib_converters
from core import risk_manager
from models.order import Order

register_matplotlib_converters()

import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)
from models.mode import Mode

import core.global_vars as gv

# Класс обеспечивающий режим симуляции торговли в реальном времени.
# Создан для проверки работы робота в реальном времени и проверки работы его фич.
# Для полноценной проверки стратегии в этом режиме, может занять много времени.
class Simulation_mode(Mode):
    # Передаваемые параметры снаружи symbol, indicators, 
    def __init__(self, symbol, strategy):
        super().__init__(symbol, strategy)
    
    # Проверка сигнала к открытию Buy
    def open_position_signal_checker(self, symbol, current_price, signal, atr_value):
        super().open_position_signal_checker()
        if type(self.order) != Order:
            if (signal == "Open_buy" or (gv.global_args.buy_sell == True and signal == "Open_sell")):
                logger.info(str(symbol) + ": Signal to open position find: " + signal)
                if risk_manager.is_tradable():
                    logger.info(str(symbol) + ": Signal to open position find: " + signal)
                    self.order = Order(current_price, symbol, atr_value, isbuy= True if signal == "Open_buy" else False)
                    self.order.open_fake_position()
                    self.locker.is_bar_locked = True
                    self.frame = self.position_id_in_frame(self.order, self.frame, self.is_order_open)

    # Проверка закрытия сделки buy
    def close_position_signal_checker(self, symbol, current_price, close_signal):
        super().close_position_signal_checker()
        if type(self.order) == Order and (close_signal == "Close_buy" or (gv.global_args.buy_sell == True and close_signal == "Close_sell")):
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal)
            self.order.fake_buy_sell_close(current_price)
            self.order = None

    
    # Проверка SLTP
    def sl_tp_checker(self, symbol, current_price):
        super().sl_tp_checker()
        if type(self.order) == Order:
            if self.order.isBuy:
                if (current_price >= self.order.take_profit or current_price <= self.order.stop_loss ):
                        self.close_position_by_sltp(symbol, current_price)
            else:
                if (current_price <= self.order.take_profit or current_price >= self.order.stop_loss ):
                    self.close_position_by_sltp(symbol, current_price)

    # Функция Trailing stop
    def trailing_stop_checker(self, current_price):
        super().trailing_stop_checker()
        if type(self.order) == Order and gv.global_args.trailing_stop != 0:
            self.order.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, current_price, signal, atr_value, close_signal):
        super().signals_handler()
        try:      
            if not self.locker.is_bar_locked:
                self.open_position_signal_checker(symbol, current_price, signal, atr_value)

                self.close_position_signal_checker(symbol, current_price, close_signal)

                self.sl_tp_checker(symbol, current_price)

                self.trailing_stop_checker(current_price)

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")
