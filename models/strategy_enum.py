from enum import Enum
from strategies.str_bollingers_band import Strategy_BB as BB
from strategies.str_ma_50 import Strategy_MA_50 as MA_50

class Strategy(Enum):
    BB_RSI = BB(20)
    MA_50_RSI = MA_50(50)
