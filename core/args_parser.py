import argparse
import os
import core.global_vars as gv

class Args_parser():

    def __init__(self):
        pass

    def args_parse(self):
        parser = argparse.ArgumentParser()

                # Внутри Args_parser.args_parse():
        parser.add_argument(
            "-mp", "--max_positions",
            type=int,
            help="Maximum number of simultaneously open positions across portfolio. Default: 4.",
            action="store",
            default=4
        )
        parser.add_argument(
            "-trp", "--trade_risk_pct",
            type=float,
            help="Risk percentage per single trade (to Stop Loss). Default: 1.5.",
            action="store",
            default=1.5
        )
        parser.add_argument(
            "-ds", "--deposit_share",
            type=float,
            help="Maximum deposit share allocated to a single instrument (0.0 to 1.0). Default: 0.25.",
            action="store",
            default=0.25
        )

        parser.add_argument("-c", "--config", help="Path to JSON portfolio config file (Example: configs/portfolio_config.json)", action="store", default=None)
        # Символы по умолчанию: "LKOH", "TATN", "SBER", "MAGN", "VTBR", "NLMK", "CHMF", "X5", "MGNT", "YDEX", "OZON"
        parser.add_argument("-s", "--symbols", help="List of instrument symbols. Enter like a strings list(Example: 'LKOH' 'TATN')\n" \
        " Default: 'LKOH', 'TATN', 'SBER', 'MAGN', 'VTBR', 'NLMK', 'CHMF', 'X5', 'MGNT', 'YDEX', 'OZON'", nargs="+", action="store", default=["LKOH"] )
        parser.add_argument("-d", "--logs_directory", help="Logs store directory.", action="store", default="logs")
        parser.add_argument("-l", "--logfile", help="Logfile path. Default: '.\\logs\\everything.log'", action="store", default="everything.log")
        parser.add_argument("-ll", "--loglevel", help="Example: DEBUG, INFO, WARNING, ERROR, CRIT.", action="store", default="INFO")
        parser.add_argument("-r", "--range", type=int, help="Range of bar at first analis.", action="store", default=300)
        parser.add_argument("-t", "--timeframe", help="Timeframe of instrument grafic. Default: 'M5' (5 minuts).\n" \
            " Posible values:\n" \
            " M5 - 5 minutes,\n" \
            " M10 - 10 minutes,\n" \
            " M15 - 15 minutes,\n" \
            " M30 - 30 minutes,\n" \
            " H1 - 1 hour,\n" \
            " H2 - 2 hours,\n" \
            " H3 - 3 hours,\n" \
            " H4 - 4 hours,\n" \
            " H6 - 6 hours,\n" \
            " H8 - 8 hours,\n" \
            " H12 - 12 hours,\n" \
            " D1 - 1 day,\n" \
            " W 1 weak,\n" \
            " MN = 1 month", action="store", default="H4")
        parser.add_argument("-str", "--strategy", help="Strategy name. Available: BB_RSI, MA_50_RSI.", action="store", default="BB_RSI_45_18_close_BBM")
        parser.add_argument("-a", "--account", help="Account number in Finam.", action="store", default=23677)
        parser.add_argument("-p", "--password", help="Account password number in Finam.", action="store", default="3C$ap3%H")
        parser.add_argument("-mm", "--monney_manager", help="Percentage of the total balance that will be involved in trading.", action="store", default=100)
        parser.add_argument("-lr", "--lost_risk", help="Percentage of total balance that is allowed to be lost.", action="store", default=100)
        parser.add_argument("-ts", "--trailing_stop", help="Price indent from Stop Loss.", action="store", default=0)
        parser.add_argument("-dtp", "--dynamic_take_profit", help="Price indent from Take Profit.", action="store_true", default=False)
        parser.add_argument("-bs", "--buy_sell", help="Type of deals. True - buy and sell, False - only buy. Example: -bs (it's True value).", action="store_true", default=False)
        parser.add_argument("-m", "--monney_mode", help="Mode of start. Posible values: \n" \
                            "simulation - trade simulation,\n" \
                            "trade - real trade.\n" \
                            "historic - trade simulation," , action="store", default="simulation")
        args = parser.parse_args()
        args.logfile = args.logs_directory + "\\" + args.logfile
        gv.global_args = args

        self.get_config_from_file(args)

        self.greetings_outpupt(gv.global_args)
    
        self.create_dirs_if_not_exist(args.logs_directory + "\\" + args.monney_mode)
        self.create_dirs_if_not_exist(args.logs_directory + "\\frames")

        return args
    
    def create_dirs_if_not_exist(self, path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            print(f"Ошибка при создании директории '{path}': {e}")

    def greetings_outpupt(self, args):

        # 3. Если запущено с JSON-конфигом — перезаписываем сводные поля args актуальными данными из файла
        if args.config:
            args.symbols = [cfg.symbol for cfg in args.instrument_configs]
            print(f"Файл конфигурации: {args.config}")
            print("Загруженный портфель из JSON:")
            for cfg in args.instrument_configs:
                print(
                    f"  - {cfg.symbol}: Strategy={cfg.strategy_name}, TF={cfg.timeframe}, "
                    f"Range={cfg.bars_range}, BuySell={cfg.buy_sell}, TS={cfg.trailing_stop}, DTP={cfg.dynamic_take_profit}"
                )
        else:
            print(f"Выбраны инструменты: {args.symbols}")
            print(f"Выбран таймфрэйм: {args.timeframe}")
            print(f"Выбранная стратегия: {args.strategy}")
            print(f"Выбран период для предварительного анализа: {args.range}")

        print(
            f"Настройки риска: MaxPositions={args.risk_config.max_open_positions}, "
            f"RiskPerTrade={args.risk_config.risk_per_trade_pct}%, DepositShare={args.risk_config.max_deposit_share}"
        )

    def get_config_from_file(seslf, args):   
        from core.config_loader import ConfigLoader
        instrument_configs, risk_config = ConfigLoader.build_from_args(args)
        
        args.instrument_configs = instrument_configs
        args.risk_config = risk_config
        return args