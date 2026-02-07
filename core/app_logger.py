import logging
import logging.handlers
import core.global_vars as gv

from enum import Enum

class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRIT = logging.CRITICAL

_log_format = f"[%(asctime)s] - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"

def get_file_handler(filename):
    file_handler = logging.FileHandler(filename)
    file_handler.setLevel(LogLevel[gv.global_args.loglevel].value)
    file_handler.setFormatter(logging.Formatter(_log_format))
    return file_handler

def get_stream_handler():
    stream_handler = logging.StreamHandler()
    stream_handler.flush()
    stream_handler.setStream(stream=None)
    stream_handler.setLevel(logging.ERROR)
    stream_handler.setFormatter(logging.Formatter(_log_format))
    return stream_handler

def get_rotate_handler(filename):
    rotate_handler = logging.handlers.TimedRotatingFileHandler(filename, when='midnight', interval=1, 
                         backupCount=7, encoding=None, 
                         delay=False, utc=False, atTime=None)
    rotate_handler.setLevel(logging.INFO)
    rotate_handler.setFormatter(logging.Formatter(_log_format))
    return rotate_handler

def get_logger(name):
    if gv.global_args != None:
        log_filename = gv.global_args.logfile
    else:
        log_filename = "test.txt"
    logger = logging.getLogger(name)
    logger.setLevel(LogLevel[gv.global_args.loglevel].value)
    logger.addHandler(get_file_handler(log_filename))
    # TODO: Priority: 3 Блядство... В винде ротация логов с нескольькими потоками не работает
    # https://qna.habr.com/q/1341954
    # Можно попробовать в отдельно логировать каждый инструмент в свой файл. 
    # Либо переезжать на linux 
    # logger.addHandler(get_rotate_handler(log_filename))
    #  
    # Стоит ли ошибки выводить в консоль ошибки? Вопрос...
    # logger.addHandler(get_stream_handler())
    logger.propagate = False
    return logger


