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
        # self.ma = MA("MA", period, "ema")

    def update_values(self, frame):
        logger.info("BB updating frame values...")
        frame.ta.bbands(length=self.period, std=2, append=True)
        """frame = self.ma.update_values(frame)
        std = np.std(np.array(frame['close'])[-self.period:], ddof=1)
        try:
            frame['bb_high'] = frame['MA'] + 2 * std
            frame['bb_low'] = frame['MA'] - 2 * std
        except(KeyError):
             logger.error("Отсутствует ключ во фрэйме. Возможно, отсутвтувет расчет связанного индикатора.")
        """
        return frame
    