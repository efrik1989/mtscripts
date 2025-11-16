from rich.progress import track
import time
import numpy as np
import pandas as pd
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

class Historic_mode(Mode):
    def __init__(self, symbol, indicators):
        super().__init__(symbol, indicators)

     # Проверка сигнала к открытию Buy
     # TODO: [Priority: 1] Получается по условию что у нас 2 сделки может быть открыто одновремено buy и sell
     # Стоит order_buy и order_sell сделать просто order.
    def buy_signal_checker(self, symbol, current_price, signal, atr_value):
        super().buy_signal_checker()
        if type(self.order_buy) != Order and signal == "Open_buy":
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            # if risk_manager.is_tradable():
            self.order_buy = Order(current_price, symbol, atr_value)
            self.order_buy.fake_buy()
            self.orders_count += 1
            self.frame = self.position_id_in_frame(self.order_buy, self.frame, self.is_order_open)

    # Проверка сигнала к открытию Sell
    def sell_signal_checker(self, symbol, current_price, signal, atr_value):
        super().sell_signal_checker()
        if gv.global_args.buy_sell == True and (type(self.order_sell ) != Order and signal == "Open_sell"):
            logger.info(str(symbol) + ": Signal to open position find: " + signal)
            # if risk_manager.is_tradable():
            self.order_sell = Order(current_price, symbol, atr_value)
            self.order_sell.fake_sell()
            self.orders_count += 1
            self.frame = self.position_id_in_frame(self.order_sell, self.frame, self.is_order_open)

    # Проверка закрытия сделки buy
    def close_byu_signal_checker(self, symbol, current_price, close_signal):
        super().close_byu_signal_checker()
        if type(self.order_buy) == Order and close_signal == "Close_buy":
            last_position_profit = self.order_buy.fake_buy_sell_close(current_price)
            self.check_order_profit(last_position_profit)
            self.profit += last_position_profit
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal + " profit: " + str(last_position_profit))
            self.order_buy = None

    # Проверка сигнала к закрытию сделки sell
    def close_sell_signal_checker(self, symbol, current_price, close_signal):
        super().close_sell_signal_checker()
        if (type(self.order_sell) == Order and close_signal == "Close_sell"):
            last_position_profit = self.order_sell.fake_buy_sell_close(current_price)
            self.check_order_profit(last_position_profit)
            self.profit += last_position_profit
            print(last_position_profit)
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal + " profit: " + str(last_position_profit))
            self.order_sell = None
    
    # Проверка SLTP buy
    def sl_tp_for_buy_checker(self, symbol, index):
        super().sl_tp_for_buy_checker()   
        if (type(self.order_buy) == Order):
            for row, index in enumerate(self.get_price_from_ticks(index)):
                current_price = float(row['bid'])
                if (current_price >= self.order_buy.take_profit or current_price <= self.order_buy.stop_loss ):
                    logger.info(str(symbol) + ": Signal to close position find: SLTP")
                    self.profit += self.order_buy.fake_buy_sell_close(current_price)
                    self.order_buy = None
                    return

    # Проверка SLTP sell
    def sl_tp_for_sell_checker(self, symbol, index):
        super().sl_tp_for_sell_checker()
        if (type(self.order_buy) == Order):
            for row, index in enumerate(self.get_price_from_ticks(index)):
                current_price = float(row['bid'])
                if (current_price <= self.order_sell.take_profit or current_price >= self.order_sell.stop_loss ):
                    logger.info(str(symbol) + ": Signal to close position find: SLTP")
                    self.profit += self.order_buy.fake_buy_sell_close(current_price)
                    self.order_buy = None
                    return

    # TODO: Пока не уверен стоит ли делать обработку trailing stop в режими истории
    # Во всяком случае пока т.к. это подразумевает, что нужно будет подгружать тики кажджого бара.
    # Этот процесс может очень сильно затянуть процесс проверки стратегии. 
    # Функция Trailing stop buy
    def buy_trailing_stop_checker(self, current_price):
        super().buy_trailing_stop_checker()
        if type(self.order_buy) == Order and gv.global_args.trailing_stop != 0:
            self.order_buy.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    # Функция Trailing stop sell
    def sell_trailing_stop_checker(self, current_price):
        super().sell_trailing_stop_checker()   
        if type(self.order_sell) == Order and gv.global_args.trailing_stop != 0:
            self.order_sell.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, signal, atr_value, close_signal, frame, index):
        super().signals_handler()
        
        try:      
            self.buy_signal_checker(symbol, frame['close'], signal, atr_value)
            self.sell_signal_checker(symbol, frame['close'], signal, atr_value)

            self.close_byu_signal_checker(symbol, frame['close'], close_signal)
            self.close_sell_signal_checker(symbol, frame['close'], close_signal)

            self.sl_tp_for_buy_checker(symbol, index)
            self.sl_tp_for_sell_checker(symbol, index)

            # self.buy_trailing_stop_checker()
            # self.sell_trailing_stop_checker()

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")

    def getRowByindex(self, frame, index: int):
        return frame.iloc[index]

    def lets_trade(self, symbol):
        """Метод с основной логикой купли продажи по сигналам."""
        # TODO: Priority: 1 Этот метод надо переопределить.
        # Основная идея в том, что вмемсто обновления на следующий бар нужно проверить все имеющиеся бары.
        # Т.е. нужен перебор по строкам и скачивание тиков для текущего или следующего бара. Проработать надо.
        
        self.frame = self.update_all_frame(symbol, self.frame, self.indicators, self.is_order_open, self.locker, self.order_buy, self.order_sell, index=np.array(self.frame.index)[-1] + 1)
        for index in track(range(len(np.array(self.frame['low'])) - 1), description="Processing..."):
        # for index, row in enumerate(np.array(self.frame['low'])):
            # if not risk_manager.is_equity_satisfactory():
            #     raise Exception("Balance is too low!!!")
            
            # self.frame = self.update_all_frame(symbol, self.frame, self.indicators, self.is_order_open, self.locker, self.order_buy, self.order_sell, index=np.array(self.frame.index)[-1] + 1)

            frame = self.getRowByindex(self.frame, index)
            
            # TODO: Возможно стоит ATR записывать в 2 отдельныйх столбца SL и TP. 
            # А затем пост обработкой все значения кроме тех где сигнал на покупку\продажу выставлять NaN. Для более простого анализа.
            signal = frame['signal']
            close_signal = frame['close_signal']
            atr_value = float(frame['ATR'] * 2)  
            
            # TODO: Цена будет получаться не посредственно в методаХ обработки сигналов или стопов  
            # current_price = mt5_a.get_price(self.tick_obj)
           
            self.signals_handler(symbol, signal, atr_value, close_signal, frame, index)

        self.close_open_positions(frame['close'], symbol)

        output_file = open(gv.global_args.logs_directory + "\\" + gv.global_args.monney_mode + "\\analis_result.txt", "a")
        output_file.write(symbol + "\n" \
                            "Количество сделок: " + str(self.orders_count) + "\n" \
                            "Доход со сделок: " + str(self.get_profit_sum()) + "\n" \
                            "Количество прибыльных сделок: " + str(self.profit_orders_count) + "\n" \
                            "Эффективность стратегии: " + str(self.get_efficiency()) + "\n") 
        
        

        output_file.close()


    # TODO: Не совсем прпедставляю себе поведение работы с этим
    # Т.е. у нас щелкнул сигнал. У нас и так понятна цена открытия...
    # Тоже самое с закрытием... 
    # А вот SLTP вероятно да т.к. при работе с frame на исторических данных текущая цена не доступна (!!!)
    # Трэйлинг стоп тоже да (!!!)  
    def get_price_from_ticks(self, current_bar_index):
        current_bar = self.getRowByindex(self.frame, current_bar_index)
        next_bar = self.getRowByindex(self.frame, current_bar_index + 1)
        ticks = mt5_a.getPeriodTicks(self.symbol, current_bar['time'], next_bar['time'])
        return pd.DataFrame(ticks)
    
    def check_order_profit(self, profit):
        if (profit > 0):
            self.profit_orders_count += 1
    
    def get_profit_sum(self):
        return self.profit
    
    def get_efficiency(self):
        try:
            return float(self.profit_orders_count) / float(self.orders_count) * 100
        except(ZeroDivisionError):
            print("profit_orders_count = " + str(self.profit_orders_count))
            print("orders_count = " + str(self.orders_count))
            logger.critical("Один из показателей равен нулю: profit_orders_count = " + str(self.profit_orders_count) + ", orders_count = " + str(self.orders_count))

    def close_open_positions(self, current_price, symbol):
        if type(self.order_sell) == Order:
            last_position_profit = self.order_sell.fake_buy_sell_close(current_price)
        if type(self.order_buy) == Order:
            last_position_profit = self.order_buy.fake_buy_sell_close(current_price)
        self.check_order_profit(last_position_profit)
        self.profit += last_position_profit
        logger.info(str(symbol) + ": Signal to close positions. profit: " + str(last_position_profit))