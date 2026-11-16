# Оригинальный идикатор имеет значения 12, 26, 9. Пробуем 8, 17, 9 для внутредневной торговли.
import pandas as pd
import pandas_ta as ta
from models.indicator import Indicator
import core.app_logger as app_logger
logger=app_logger.get_logger(__name__)

class MACD(Indicator):
    def __init__(self, name: str = "MACD", fast: int = 12, slow: int = 26, signal: int = 9):
        # Передаем slow в базовый класс как минимальный период прогрева индикатора
        super().__init__(name, slow)
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def update_values(self, frame: pd.DataFrame) -> pd.DataFrame:
        macd = ta.macd(frame['close'], fast=self.fast, slow=self.slow, signal=self.signal)
        if macd is None or macd.empty:
            return frame

        suffix = f"{self.fast}_{self.slow}_{self.signal}"
        frame['macd_line'] = macd[f'MACD_{suffix}']
        frame['macd_signal'] = macd[f'MACDs_{suffix}']
        frame['macd_hist'] = macd[f'MACDh_{suffix}']
        frame['macd_hist_sh1'] = frame['macd_hist'].shift(1)

        return frame
