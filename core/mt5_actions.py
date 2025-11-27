from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
from pandas.plotting import register_matplotlib_converters
import numpy as np

register_matplotlib_converters()
import MetaTrader5 as mt5
from metatrader5EasyT import tick
from indicators.ma import MA
from indicators.rsi import RSI
from indicators.atr import ATR
from models.order import Order
from models.timframe_enum import Timeframe
from core.risk_manager import RiskManager
import core.app_logger as app_logger

logger = app_logger.get_logger(__name__)

class MT5_actions():
    def __init__(self):
        pass

    def init_MT5():
        # connect to MetaTrader 5
        if not mt5.initialize("C:\\Program Files\\FINAM MetaTrader 5\\terminal64.exe"):
            logger.critical("initialize(): failed")
        
        # request connection status and parameters,0000
        # print(mt5.terminal_info())
        # get data on MetaTrader 5 version
        # print(mt5.version())

    def authorization(account, password):
        authorized = mt5.login(login=account, server="FINAM-AO",password=password)  
        if authorized:
            logger.info("authorization(): connected to account #{}".format(account))
        else:
            logger.error("authorization(): failed to connect at account #{}, error code: {}".format(account, mt5.last_error()))

    # Выбираем символ(инструмент)
    def selectSymbol(symbol):
        selected=mt5.symbol_select(symbol,True)
        if not selected:
            logger.error("selectSymbol(): Failed to select " + str(symbol) + ", error code =",mt5.last_error())
        else:
            # symbol_info=mt5.symbol_info(symbol)
            logger.info("selectSymbol(): " + str(symbol))

    def get_price(tick_obj):        
        tick_obj.get_new_tick()
        return tick_obj.bid

    # Получение торговых данных инструмента за определенный промежуток
    def get_rates_frame(symbol:str, start_bar: int, bars_count: int, timeframe: str):
        rates = mt5.copy_rates_from_pos(symbol, Timeframe[timeframe].value, start_bar, bars_count)
        if len(rates) == 0:
            logger.error(symbol + ": get_rates_frame(): Failed to get history data. " + str(mt5.last_error()))
        rates_frame = pd.DataFrame(rates)
        # rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
        rates_frame['close'] = pd.to_numeric(rates_frame['close'], downcast='float')
        return rates_frame

    # Получение последнего бара
    def get_last_bar(symbol, timeframe, index ):
        last_rates = mt5.copy_rates_from_pos(symbol, Timeframe[timeframe].value, 1, 1)
        if not last_rates:
            logger.critical(str(symbol) + ": get_last_bar(): Failed to get last rate: " + mt5.last_error())
            
        last_rates_df = pd.DataFrame(last_rates, index=[index])
        return last_rates_df

    def check_order(symbol):
            positions = pd.DataFrame(mt5.positions_get(symbol)) 
            result = len(positions) > 0
            return result

    # Получение всех тиков за период
    def getPeriodTicks(symbol, start_period, end_period ):
        # request AUDUSD ticks within 11.01.2020 - 11.01.2020
        ticks = mt5.copy_ticks_range(symbol, start_period, end_period, mt5.COPY_TICKS_ALL)  
        return ticks
