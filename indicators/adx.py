import pandas_ta as ta
from models.indicator import Indicator

class ADX(Indicator):
    def __init__(self, name, period):
        super().__init__(name, period)

    def update_values(self, frame):
        adx = ta.adx(frame['high'], frame['low'], frame['close'], length=14)
        frame['ADX'] = adx['ADX_14']
        return frame