import pandas as pd
from models.indicator import Indicator
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

class ATR(Indicator):
    def __init__(self, name, period):
        self.name = name
        self.period = period

    def calculate_true_range(self, df):
        df['high_low'] = df['high'] - df['low']
        df['high_prev_close'] = abs(df['high'] - df['close'].shift(1))
        df['low_prev_close'] = abs(df['low'] - df['close'].shift(1))
        
        df['True_Range'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
        
        return df

    def calculate_atr(self, df, atr_type='rma'):
        df = self.calculate_true_range(df)
        
        if atr_type == 'rma':
            df['ATR'] = df['True_Range'].ewm(alpha=1/self.period, adjust=False).mean()
        elif atr_type == 'sma':
            df['ATR'] = df['True_Range'].rolling(window=self.period).mean()
        elif atr_type == 'ema':
            df['ATR'] = df['True_Range'].ewm(span=self.period, adjust=False).mean()
        elif atr_type == 'wma':
            weights = pd.Series(range(1, self.period + 1))
            df['ATR'] = df['True_Range'].rolling(window=self.period).apply(lambda x: (weights*x).sum() / weights.sum(), raw=True)
        else:
            raise ValueError(f"Unknown ATR type: {atr_type}")
        
        return df

    def update_values(self, frame):
        logger.info("MA Начато обновление данных.")
        frame = self.calculate_atr(frame, atr_type='rma')
        return frame