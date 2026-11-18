import sys
import copy
from datetime import datetime
import threading
import core.args_parser as args_parser
parser = args_parser.Args_parser()
args = parser.args_parse()
import core.global_vars as gv

from config_loader import ConfigLoader, InstrumentConfig
from core.risk_manager import RiskManager
risk_manager = RiskManager(args.monney_manager, args.lost_risk)

instrument_configs, risk_cfg = ConfigLoader.build_from_args(args)

risk_manager = RiskManager(
    trade_risk=args.monney_manager,
    lost_risk=args.lost_risk,
    risk_config=risk_cfg
)

from core.mt5.mt5_actions import MT5_actions as mt5_a
import core.app_logger as app_logger

logger=app_logger.get_logger(__name__)

import MetaTrader5 as mt5
from models.strategy_enum import Strategy

import core.queue_handler as queue

import core.modes.simulation_mode as sm
import core.modes.trade_mode as tm
import core.modes.historic_mode as hm


"""
Основная задача скрипта опрпделеять точки входа в сделку и выхода.
На вход получаем минутный фрейм, будем подоватьт по строчно т.е. будут известны история этих данных и 
чтобы принять решение об открытии позиции нужно подождать закрытия следующего бара.
"""

# Функция определения режима
def monney_mode_select(config: InstrumentConfig):
    """Запускает поток инструмента со своей стратегией и индивидуальным конфигом."""
    strategy_instance = copy.deepcopy(Strategy[config.strategy_name].value)

    mm = gv.global_args.monney_mode
    if mm == "simulation":
        return sm.Simulation_mode(config.symbol, strategy_instance, config=config)
    if mm == "trade":
        return tm.Trade_mode(config.symbol, strategy_instance, config=config)
    if mm == "historic":
        return hm.Historic_mode(config.symbol, strategy_instance, config=config)
    return mm

def historic_analis_writer(producers):
    for t in producers:
            t.join()

    now = datetime.now()
    frame = queue.set_data_to_frame()
    frame.to_excel(f"{gv.global_args.logs_directory}\\historic\\Analis_Result_{now.strftime("%d-%m-%Y_%H_%M_%S")}.xlsx")
    
def symbols_workers_start(producers):
    if len(args.instrument_configs) != 0:
        logger.debug("Instruments count: " + str(len(args.instrument_configs)))
        for cfg in args.instrument_configs:
            logger.info(f"{cfg.symbol}: start() -> Strategy={cfg.strategy_name}, "f"TF={cfg.timeframe}, Range={cfg.bars_range}")
            thread = threading.Thread(target=monney_mode_select, args=(cfg,), daemon=True)
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
                print("Exit from programm.")
                logger.info("Exit from programm.")
                break
            else:
                print("Please enter correct command.")
    except(KeyboardInterrupt):
        print("Exit form programm")
        logger.warning("Ошибка при работе с вводом! Экстренное завершение программы.")
    except Exception as e:
        logger.error("Не предвиденная ошибка при работе с вводом! Экстренное завершение программы.")
        sys.exit(1)    

def startRobot():
    logger.info("-----------------------Start new session----------------------")
    mt5_a.init_MT5()
    mt5_a.authorization(args.account, args.password)
    
    producers = []
    producers = symbols_workers_start(producers)

    if gv.global_args.monney_mode == "historic":
        historic_analis_writer(producers)
        print("The End")
        return

    commands_handler()

startRobot()
# shut down connection to MetaTrader 5
mt5.shutdown()
sys.exit