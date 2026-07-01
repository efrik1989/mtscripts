import pandas_ta as ta
from models.indicator import Indicator
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

class ADX(Indicator):
    def __init__(self, name, period):
        super().__init__(name, period)

    def update_values(self, frame):
        logger.debug("ADX Начато обновление данных.")
        adx = ta.adx(frame['high'], frame['low'], frame['close'], length=self.period)
        frame['ADX'] = adx[f'ADX_{self.period}']
        logger.debug("Закончено обновление данных ADX.")
        return frame