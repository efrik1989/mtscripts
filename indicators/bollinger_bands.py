import pandas as pd
import pandas_ta as ta
import numpy as np
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

from models.indicator import Indicator
from indicators.ma import MA

class Bollinger(Indicator):
    def __init__(self, name, period):
        super().__init__(name, period)
        self.period = period

    def update_values(self, frame):
        logger.info("BB updating frame values...")
        frame.ta.bbands(length=self.period, std=1.4, append=True)
        return frame
    