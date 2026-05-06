import numpy as np
import pandas as pd
from models.strategy import Strategy

from indicators.rsi import RSI
from indicators.atr import ATR
from indicators.bollinger_bands import Bollinger
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.ma import MA

import core.app_logger as app_logger
logger=app_logger.get_logger(__name__)

class Strategy_MACD(Strategy):
    def __init__(self, period):
                super().__init__(period)
                self.indicators = [MACD('MACD', 12, 12, 26, 9),  
                                   RSI("RSI", 14, True), 
                                    MA("EMA", 200, "ema")]
                """self.rsi_open = rsi_open
                self.adx_open = adx_open
                self.open_triger = open_triger
                self.close_triger = close_triger    """

    def open_strategy(self, frame):
            conditions = [
                (frame['close'] > frame['EMA200']) & 
                (frame['macd_line'] > frame['macd_signal']) & 
                (frame['RSI'] > 30) & (frame['RSI'] < 50)
                ,
                # Доработать стратегию для SELL
                (frame['close'] < frame['EMA200']) & 
                (frame['macd_line'] > frame['macd_signal']) & 
                (frame['RSI'] < 70 ) & (frame['RSI'] > 50)
            ]
            chois = ["Open_buy", "Open_sell"]
            frame['signal'] = np.select(conditions, chois, default="NaN")   
            return frame
    
    def close_strategy(self, frame):
            conditions = [
                (frame['macd_line'] < frame['macd_signal']) | 
                (frame['RSI'] > 70)
                ,
                (frame['macd_line'] > frame['macd_signal']) | 
                (frame['RSI'] < 30)
                ]
            chois = ["Close_buy", "Close_sell"]
            frame['close_signal'] = np.select(conditions, chois, default="NaN")

            logger.info("strategy: Analis complete.")
            return frame
    