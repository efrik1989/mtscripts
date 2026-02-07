from rich.progress import track
import numpy as np
import pandas as pd
import queue
from pandas.plotting import register_matplotlib_converters
from models.order import Order
import core.queue_handler as queue

register_matplotlib_converters()

from core.mt5_actions import MT5_actions as mt5_a
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)
from models.mode import Mode

import core.global_vars as gv

class Historic_mode(Mode):
    def __init__(self, symbol, strategy):
        super().__init__(symbol, strategy)

     # Проверка сигнала к открытию
    def open_position_signal_checker(self, symbol, current_price, signal, atr_value):
        super().open_position_signal_checker()
        if type(self.order) != Order:
            if (signal == "Open_buy" or (gv.global_args.buy_sell == True and signal == "Open_sell")):
                logger.info(str(symbol) + ": Signal to open position find: " + signal)
                # if risk_manager.is_tradable():
                self.order = Order(current_price, symbol, atr_value, isBuy= True if signal == "Open_buy" else False)
                self.order.open_fake_position()
                self.orders_count += 1
                self.frame = self.position_id_in_frame(self.order, self.frame, self.is_order_open)

    # Проверка сигнала закрытия сделки
    def close_position_signal_checker(self, symbol, current_price, signal, close_signal):
        super().close_position_signal_checker()
        if type(self.order) == Order and signal=="NaN" and (close_signal == "Close_buy" or (gv.global_args.buy_sell == True and close_signal == "Close_sell")):
            last_position_profit = self.order.fake_buy_sell_close(current_price)
            self.check_order_profit(last_position_profit)
            self.profit += last_position_profit
            logger.info(str(symbol) + ": Signal to close position find: " + close_signal + " profit: " + str(last_position_profit))
            self.order = None
    
    # Проверка SLTP buy
    def sl_tp_checker(self, symbol, frame,  index):
        super().sl_tp_checker()
        if (type(self.order) == Order):
            logger.debug("Order to close by SLTP: " + str(self.order.id) + "SLTP: " + str(self.order.take_profit) + " " + str(self.order.stop_loss))
            isSL = frame['low'] <= self.order.stop_loss and frame['high'] >= self.order.stop_loss
            isTP = frame['low'] <= self.order.take_profit and frame['high'] >= self.order.take_profit
            logger.debug("Order to close by SLTP: " + str(self.order.id) + " В диапазлне: " + str(isTP) + " " + str(isSL))
            if (isTP or isSL):
                ticks_frame = pd.DataFrame(self.get_price_from_ticks(index))
                logger.debug("Order to close by SLTP: " + str(self.order.id) + "Количество тиков: " + str(len(ticks_frame)))
                for index, row in enumerate(range(len(np.array(ticks_frame)))):
                    current_price = float(ticks_frame['bid'].iloc[index])
                    if self.order.isBuy:
                        if (current_price >= self.order.take_profit or current_price <= self.order.stop_loss ):
                            self.close_position_by_sltp(symbol, current_price)
                            return
                    else:
                        if (current_price <= self.order.take_profit or current_price >= self.order.stop_loss ):
                            self.close_position_by_sltp(symbol, current_price)
                            return
                
    # Функция Trailing stop buy
    def trailing_stop_checker(self, frame, index):
        super().trailing_stop_checker()
        if type(self.order) == Order and gv.global_args.trailing_stop != 0:
            # TODO: Как-будто кусок кода можно вынести в отдельую функцию...
            ticks_frame = pd.DataFrame(self.get_price_from_ticks(index))
            logger.debug("Order to change SL: " + str(self.order.id) + "Количество тиков: " + str(self.order.stop_loss))
            for index, row in enumerate(range(len(np.array(ticks_frame)))):
                current_price = float(ticks_frame['bid'].iloc[index])
                # Кусок кода ниже можно передавать как аргумемнт...
                self.order.fake_traling_stop(current_price, gv.global_args.trailing_stop)

    def signals_handler(self, symbol, signal, atr_value, close_signal, frame, index):
        super().signals_handler()
        
        try:      
            self.open_position_signal_checker(symbol, frame['close'], signal, atr_value)

            self.trailing_stop_checker(frame, index)

            self.sl_tp_checker(symbol, frame, index)
            
            self.close_position_signal_checker(symbol, frame['close'], signal, close_signal)

        except(UnboundLocalError):
            logger.exception(str(symbol) + ": lets_trade(): Переменная или объект не в том месте.!!!")

    def getRowByindex(self, frame, index: int):
        return frame.iloc[index]

    def lets_trade(self, symbol):
        """Метод с основной логикой купли продажи по сигналам."""
        
        self.frame = self.update_all_frame(symbol, self.frame, self.strategy, self.is_order_open, self.locker, self.order, index=np.array(self.frame.index)[-1] + 1)
        for index in track(range(len(np.array(self.frame['low'])) - 1), description=symbol + ": Processing..."):
            
            frame = self.getRowByindex(self.frame, index)
            
            # TODO: Возможно стоит ATR записывать в 2 отдельныйх столбца SL и TP. 
            # А затем пост обработкой все значения кроме тех где сигнал на покупку\продажу выставлять NaN. Для более простого анализа.
            signal = frame['signal']
            close_signal = frame['close_signal']
            atr_value = float(frame['ATR'] * 4)
           
            self.signals_handler(symbol, signal, atr_value, close_signal, frame, index)

        self.set_finish_resume(symbol, frame)
    
    def get_price_from_ticks(self, current_bar_index):
        current_bar = self.getRowByindex(self.frame, current_bar_index)
        next_bar = self.getRowByindex(self.frame, current_bar_index + 1)
        ticks = mt5_a.getPeriodTicks(self.symbol, int(current_bar['time']), int(next_bar['time']))
        return pd.DataFrame(ticks)
    
    def check_order_profit(self, profit):
        if profit != None:
            if (profit > 0):
                self.profit_orders_count += 1
            self.profit += profit
    
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
        last_position_profit = None
        if type(self.order) == Order:
            last_position_profit = self.order.fake_buy_sell_close(current_price)
        self.check_order_profit(last_position_profit)
        logger.info(str(symbol) + ": Signal to close positions. profit: " + str(last_position_profit))

    # TODO: Анализ результатов надо загружать в файл excell
    # Т.е. в объект pd.Dataframe нужно собрать данные со всех потоков и запихать в excell.
    # Пу-пу-пу...  
    def set_finish_resume(self, symbol, frame):
        # file_name = "analis_result.txt"

        self.close_open_positions(frame['close'], symbol)
        """
        output_file = open(gv.global_args.logs_directory + "\\" + gv.global_args.monney_mode + "\\" + file_name, "a")
        output_file.write(symbol + "\n" \
                            "Количество сделок: " + str(self.orders_count) + "\n" \
                            "Доход со сделок: " + str(self.get_profit_sum()) + "\n" \
                            "Количество прибыльных сделок: " + str(self.profit_orders_count) + "\n" \
                            "Эффективность стратегии: " + str(self.get_efficiency()) + "\n") 
        output_file.close()
        """
        data = {'symbol' : symbol, \
                'deals_count' : self.orders_count, \
                'profit' : self.get_profit_sum(), \
                'profit_deals' : self.profit_orders_count, \
                'efficiency' : self.get_efficiency()}
        
        queue.set_data_to_queue(data)
        print("Processing finished.")
        exit(0)