from abc import ABCMeta, abstractmethod, abstractproperty

import pandas as pd
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)


# Аьстракный класс родитель описывающий стратегии, точнее их обновление
class Strategy():
    __metaclass__=ABCMeta
    def __init__(self, period):
        self.period = period
        self.indicators = []

    def update_values(self, symbol, frame, last_bar_frame):
        try:    
                frame = pd.concat([frame, last_bar_frame], ignore_index=True)
                for indicator in self.indicators:
                    frame = indicator.update_values(frame)
                    
                return frame
        except(AttributeError):
            logger.critical(str(symbol) + ": 1 оr more objects become 'None/Null'")
        return frame

    def update_strategy(self, frame):
        self.open_strategy(frame)
        self.close_strategy(frame)
        return frame
    
    @abstractmethod
    def open_strategy(self, frame):
        pass
    
    @abstractmethod
    def close_strategy(self, frame):
        pass