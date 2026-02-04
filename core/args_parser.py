import argparse
import os
import core.global_vars as gv

class Args_parser():

    def __init__(self):
        pass

    def args_parse(self):
        parser = argparse.ArgumentParser()
        # Символы по умолчанию: "LKOH", "TATN", "SBER", "MAGN", "VTBR", "NLMK", "CHMF", "X5", "MGNT", "YDEX", "OZON"
        parser.add_argument("-s", "--symbols", help="List of instrument symbols. Enter like a strings list(Example: 'LKOH' 'TATN')\n" \
        " Default: 'LKOH', 'TATN', 'SBER', 'MAGN', 'VTBR', 'NLMK', 'CHMF', 'X5', 'MGNT', 'YDEX', 'OZON'", nargs="+", action="store", default=["LKOH", "TATN", "SBER", "MAGN", "VTBR", "NLMK", "CHMF", "X5", "MGNT", "YDEX", "OZON"] )
        parser.add_argument("-l", "--logfile", help="Logfile path. Default: '.\\logs\\everything.log'", action="store", default="everything.log")
        parser.add_argument("-r", "--range", type=int, help="Range of bar at first analis.", action="store", default=100)
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
        parser.add_argument("-str", "--strategy", help="Strategy name. Available: BB_RSI, MA_50_RSI.", action="store", default="BB_RSI")
        parser.add_argument("-a", "--account", help="Account number in Finam.", action="store_true", default=23677)
        parser.add_argument("-p", "--password", help="Account password number in Finam.", action="store_true", default="3C$ap3%H")
        parser.add_argument("-mm", "--monney_manager", help="Percentage of the total balance that will be involved in trading.", action="store", default=100)
        parser.add_argument("-lr", "--lost_risk", help="Percentage of total balance that is allowed to be lost.", action="store", default=100)
        parser.add_argument("-ts", "--trailing_stop", type=int, help="Price indent from Stop Loss.", action="store", default=0)
        parser.add_argument("-bs", "--buy_sell", help="Type of deals. True - buy and sell, False - only buy. Example: -bs (it's True value).", action="store_true", default=False)
        parser.add_argument("-d", "--logs_directory", help="Logs store directory.", action="store", default="logs")
        parser.add_argument("-m", "--monney_mode", help="Mode of start. Posible values: \n" \
                            "simulation - trade simulation,\n" \
                            "trade - real trade.\n" \
                            "historic - trade simulation," , action="store", default="simulation")
        args = parser.parse_args()
        args.logfile = args.logs_directory + "\\" + args.logfile
        gv.global_args = args
        print("Выбраны иснтрументы:")
        print(args.symbols)
        print("Выбран таймфрэйм:")
        print(args.timeframe)
        print("Выбран период для предварительного анализа:")
        print(args.range)
        print("Выбран режим работы")
        print(args.monney_mode)
        print("Используется аккаунт")
        print(args.account)
        print("Файл логов")
        print(gv.global_args.logfile)
        self.create_dirs_if_not_exist(args.logs_directory + "\\" + args.monney_mode)
        self.create_dirs_if_not_exist(args.logs_directory + "\\frames")

        return args
    
    def create_dirs_if_not_exist(self, path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            print(f"Ошибка при создании директории '{path}': {e}")