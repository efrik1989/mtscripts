import time
import MetaTrader5 as mt5
import core.mt5.mt5_trade as trade
from core.mt5.mt5_actions import MT5_actions as mt5_a
import pandas as pd
import core.global_vars as gv
import core.app_logger as app_logger
import random

logger=app_logger.get_logger(__name__)


# Класс отвечающий за описание ордера
class Order():

    def __init__(self, open_price, symbol, strategy, atr_value: float, isBuy: bool):
        self.START_TRAILING = atr_value
        self.open_price = open_price    # Цена открытия сделки.
        self.symbol = symbol
        self.atr = atr_value
        self.stop_atr = atr_value * 2.5
        self.take_atr = atr_value * 5
        self.trade_obj = trade.Trade(symbol, 1.0, self.stop_atr, self.take_atr)
        self.strategy = strategy
        self.isBuy = isBuy
        self.direction = "buy" if self.isBuy else "sell"
        self.stop_loss = None
        self.take_profit = None
        self.id = random.randint(0, 100000)
        self.sim_log_path = gv.global_args.logs_directory + "\\" + gv.global_args.monney_mode + "\\simulation.txt"
        logger.debug(f"self.open_price: {self.open_price}, symbol: {self.symbol}, strategy: {gv.global_args.strategy}, atr_value: {atr_value}, stop_atr: {self.stop_atr}")


    def position_check(self):
        self.trade_obj.position_check()

    # Метод открытия сделки в симуляции
    def open_fake_position(self):
        logger.info("Order.id = " + str(self.id))
        if self.isBuy:
            self.fake_buy()
        else:
            self.fake_sell()
        output_file = open(self.sim_log_path, "a")
        output_file.write(self.symbol + ", Order.id = " + str(self.id) + ", " + self.direction+": " + str(self.open_price) + ", SL: " + str(self.stop_loss) 
                          + ", TP: " + str(self.take_profit) + ", " + str(time.asctime()) + "\n") 
        output_file.close()

    def fake_buy(self):
        self.stop_loss = self.open_price - self.stop_atr
        self.take_profit = self.open_price + self.take_atr
        
    def fake_sell(self):
        self.stop_loss = self.open_price + self.stop_atr
        self.take_profit = self.open_price - self.take_atr
    # Метод закрытия сделки в симуляции
    def fake_buy_sell_close(self, current_price):
        logger.info("Order.id = " + str(self.id))
        output_file = open(self.sim_log_path, "a")
        output_file.write(self.symbol + ", Order.id = " + str(self.id) + ", close_position: " + str(current_price) + ", " + str(time.asctime()) + "\n")
        profit = None
        if self.isBuy==True:
            profit = current_price - self.open_price    
        elif self.isBuy==False:
            profit = self.open_price - current_price
        output_file.write(self.symbol + ", Order.id = " + str(self.id) + ", profit: " + str(profit) + ", " + str(time.asctime()) + "\n")
        output_file.close()
        return profit

    def open_position(self):
        try:
            self.trade_obj.position_open(self.isBuy, not self.isBuy)
        except:
            logger.error(f"{self.symbol}: Somthing went wrong to open position!!!")
        position = mt5_a.get_position_info(self.symbol)
        self.id = position.ticket

    def close_position(self):
        try:
            self.trade_obj.position_close()
        except:
            logger.error(f"{self.symbol}: Somthing went wrong to close position!!!")
        
    
    # TODO: Priority: 1 [general\sim]Реализовать трэйлинг стоп
    #  аргумент текущая цена. Если цена увеличилась на фиксированое значение(значение или % тут надо подумать), то сдвигаем стоп лосс.
    def fake_traling_stop(self, current_price, indent):
        if indent == "atr": indent = self.stop_atr
        isNeedToMoveSL = None
        new_value = None
        point=mt5.symbol_info(self.symbol).point
        if self.isBuy:
            new_value = current_price - self.stop_atr
            isNeedToMoveSL = (self.stop_loss + (indent * point)) <= new_value
        else:
            new_value = current_price + self.stop_atr
            isNeedToMoveSL = (self.stop_loss - (indent * point)) >= new_value

        if isNeedToMoveSL: 
            self.stop_loss = new_value
            output_file = open(self.sim_log_path, "a")
            output_file.write(self.symbol + ", SL changed: " + str(self.stop_loss) + ", " + str(time.asctime()) + "\n") 
            output_file.close()
    
    def traling_stop(self, current_price, indent):
        if indent == "atr": indent = self.stop_atr
        self.trade_obj.check_and_update_trailing(self.symbol, indent, self.START_TRAILING)
        logger.info(f"{self.symbol}: positions info:{mt5_a.get_position_info(self.symbol)}")
           
    def fake_set_new_take_profit(self, new_tp):
        if new_tp != None and new_tp != "":
            self.take_profit = new_tp

    def set_new_take_profit(self, new_tp):
        if new_tp != None and new_tp != "":
            trade.change_take_profit(self.symbol, new_tp)

    def to_string(self):
        return "" + str(self.open_price) + " " + str(self.symbol) + " " + str(self.isBuy)