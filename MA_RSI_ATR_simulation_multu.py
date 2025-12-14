import sys
import threading
import core.args_parser as args_parser
parser = args_parser.Args_parser()
args = parser.args_parse()

#TODO: Задачка усложнилась из риск мэнеджера надо сделать потоко безопасный синглтон
from core.risk_manager import RiskManager
risk_manager = RiskManager(args.monney_manager, args.lost_risk)

from core.mt5_actions import MT5_actions as mt5_a
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)


import MetaTrader5 as mt5
from metatrader5EasyT import tick

from indicators.ma import MA
from indicators.rsi import RSI
from indicators.atr import ATR

from models.order import Order

import core.queue_handler as queue
import core.global_vars as gv
import core.simulation_mode as sm
import core.trade_mode as tm
import core.historic_mode as hm
"""
Основная задача скрипта опрпделеять точки входа в сделку и выхода.
На вход получаем минутный фрейм, будем подоватьт по строчно т.е. будут известны история этих данных и 
чтобы принять решение об открытии позиции нужно подождать закрытия следующего бара.
"""
# TODO: Priority: 1 [general] Необходимл отладить стратегию(ии). На данный момент можно запустить симуляцию, но это не проверка стратегии на исторических данных.
# Нужен отдельный режим history (как simulation\trade), что покажет, где бы по текущей стртегии был бы вход в сделку, выход из нее и профит + расчет итогового профита.
# TODO: Priority: 2 [general] Обложить все юнит тестами
# TODO: Priority: 3[general/sim/history] Должна быть возможность выставить SLTP не только в значении ATR.
# TODO: Пока выносить параметры, что стоит указывать в аргументах при запуске, а не хардкодить.
# TODO: Сделать возможность выставлять только SL или TP
# Период для индикаторов
window = 50


# Функция определения режима
def monney_mode_select(symbol):
    mm = gv.global_args.monney_mode
    indicators = [MA('MA50', window), RSI("RSI14", 14, True), ATR("ATR", 14)]
    if mm == "simulation": return sm.Simulation_mode(symbol, indicators)
    if mm == "trade": return tm.Trade_mode(symbol, indicators)
    if mm == "historic": return hm.Historic_mode(symbol, indicators)
    return mm

def historic_analis_writer(producers):
    for t in producers:
            t.join()

    frame = queue.set_data_to_frame()
    frame.to_excel(gv.global_args.logs_directory + "\\historic\\Analis_Result_" \
                       + gv.global_args.timeframe + "_Buy_Sell=" + str(gv.global_args.buy_sell) + \
                        "_TrailingStop=" + str(gv.global_args.trailing_stop) + ".xlsx")
    
def symbols_workers_start(producers):
    if len(args.symbols) != 0:
        logger.debug("Symbols lenght: " + str(len(args.symbols)))
        for symbol in args.symbols:
            logger.info(str(symbol) + ": start()")
            thread=threading.Thread(target=monney_mode_select, args=(symbol,), daemon=True)
            thread.start()
            producers.append(thread)
    return producers

def commands_handler():
    print("Posible commands:")
    print("exit - exit from programm")
    print("Please enter command:")
    try: 
        while True:
            command = input()
            if command == "exit":
                logger.info("Exit from programm.")
                break
            else:
                print("Please enter correct command.")
    except Exception as e:
        logger.warning("Ошибка при работе с вводом! Экстренное завершение программы.")    

def startRobot():
    mt5_a.init_MT5()
    mt5_a.authorization(args.account, args.password)
    
    producers = []
    symbols_workers_start(producers)

    # TODO: Priority: 2 [general] Добавить "Уровень риска". Процент от общего счета который может использовать робот. 
    # TODO: Priority: 1 [general] И предохранитель, если баланс опустил на n-% от максимального кидаем ошибку и останавливаемся.
    # Или например нет больше денег на болансе и сделку совершить невозможно.
    if gv.global_args.monney_mode == "historic":
        historic_analis_writer(producers)
        return

    commands_handler()

startRobot()
# shut down connection to MetaTrader 5
mt5.shutdown()
sys.exit