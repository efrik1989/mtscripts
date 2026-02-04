from indicators.ma import MA
from models.indicator import Indicator


# Оригинальный идикатор имеет значения 12, 26, 9. Пробуем 8, 17, 9 для внутредневной торговли.
class MACD(Indicator):
    def __init__(self, name, period, fast, slow, signal):
        super().__init__(name, period)

        # TODO: Выглядит так что можно в список затолкать... Пока не критично.
        self.fast_ema = MA("fast_MA", fast, "ema")
        self.slow_ema = MA("slow_MA", slow, "ema")
        self.signal_ema = MA("signal_MA", signal, "ema")

    def update_values(self, frame):
        frame = self.fast_ema.update_values(frame)
        frame = self.slow_ema.update_values(frame)
        frame = self.signal_ema.update_values(frame)
        frame['divergence'] = frame['slow_MA'] - frame['fast_MA']
        return frame