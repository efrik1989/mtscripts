from abc import ABCMeta, abstractmethod, abstractproperty
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

# Абстрактный класс родитель описывающий основные методы индикатора
class Indicator():
    __metaclass__=ABCMeta
    def __init__(self, name:str, period:int):
        self.name = name
        self.period = period

    @abstractmethod
    def update_values(self, frame):
        logger.info("Нечего обновлять.")
        return frame
    
    @abstractmethod
    def strategy(self, frame):
        logger.info("Нет стратегии для обновления frame")
        return frame