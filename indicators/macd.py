import pandas_ta as ta
import pandas as pd
from models.indicator import Indicator


# Оригинальный идикатор имеет значения 12, 26, 9. Пробуем 8, 17, 9 для внутредневной торговли.
class MACD(Indicator):
    def __init__(self, name, period, fast, slow, signal):
        super().__init__(name, period)
        self.fast = fast
        self.slow = slow
        self.signal = signal

    # fast=12, slow=26, signal=9
    def update_values(self, frame: pd.DataFrame):
        macd = ta.macd(frame['close'], fast=self.fast, slow=self.slow, signal=self.signal)
        frame['macd_line'] = macd[f'MACD_{self.fast}_{self.slow}_{self.signal}']
        frame['macd_signal'] = macd[f'MACDs_{self.fast}_{self.slow}_{self.signal}']
        frame['macd_hist'] = macd[f'MACDh_{self.fast}_{self.slow}_{self.signal}']
        frame['macd_hist_sh1'] = frame['macd_hist'].shift(1)
        return frame