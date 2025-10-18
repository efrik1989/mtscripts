import pandas as pd
import numpy as np
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

class Indicator():
    def __init__(self):
        pass

    def update_values(self, frame):
        logger.info("Нечего обновлять.")
        return frame
    
    def strategy(self, frame):
        logger.info("Нет стратегии для обновления frame")
        return frame