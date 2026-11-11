import backtrader as bt
import pandas as pd
import numpy as np
from models.mode import Mode
import core.app_logger as app_logger
import core.global_vars as gv
from models.lots_enum import Lot
import core.queue_handler as queue
from mt5.mt5_actions import MT5_actions as mt5_a  

logger = app_logger.get_logger(__name__)


class GenericMT5Data(bt.feeds.PandasData):
    lines = ('signal_code', 'close_signal_code',)
    params = (
        ('signal_code', -1),
        ('close_signal_code', -1),
    )


class Historic_mode(Mode):
    def __init__(self, symbol, strategy):
        self.symbol = symbol
        self.strategy = strategy

        self.cerebro = bt.Cerebro(preload=False)
        self.start_cash = 10000.0
        self.cerebro.broker.setcash(self.start_cash)
        self.cerebro.broker.setcommission(commission=0.0)

        self.orders_count = 0
        self.profit_orders_count = 0
        self.profit = 0.0
        self.max_drawdown = 0.0

        self.orders_count = 0
        self.profit_orders_count = 0
        self.buy_orders_count = 0
        self.buy_profit_count = 0
        self.sell_orders_count = 0
        self.sell_profit_count = 0

        super().__init__(symbol, strategy)

    def get_symbol_point(self, symbol):
        """Получает минимальный шаг цены (point) инструмента из MT5."""
        return mt5_a.get_symbol_point(symbol)

    def get_efficiency(self):
        if self.orders_count == 0:
            return None
        return float(self.profit_orders_count) / float(self.orders_count) * 100

    def get_profit_sum(self):
        """Возвращает чистый профит, заработанный в бэктесте."""
        return self.profit

    def prepare_data(self):
        df = self.frame.copy()

        # Универсальный вызов расчёта индикаторов и сигналов любой переданной стратегии
        df = self.strategy.update_values(self.symbol, df, df)
        df = self.strategy.update_strategy(df)
        self.frame = df.copy()

        if 'time' in df.columns:
            if pd.api.types.is_numeric_dtype(df['time']):
                df['datetime'] = pd.to_datetime(df['time'], unit='s')
            else:
                df['datetime'] = pd.to_datetime(df['time'])
            df.set_index('datetime', inplace=True)

        signal_map = {"Open_buy": 1, "Open_sell": -1, "NaN": 0}
        close_map = {"Close_buy": 1, "Close_sell": -1, "NaN": 0}

        df['signal_code'] = df['signal'].map(signal_map).fillna(0).astype(int)
        df['close_signal_code'] = df['close_signal'].map(close_map).fillna(0).astype(int)

        data_signals = GenericMT5Data(dataname=df)
        self.cerebro.adddata(data_signals)

    def lets_trade(self, symbol):
        self.prepare_data()

        point_size = self.get_symbol_point(symbol)

        self.cerebro.addstrategy(
            BacktraderExecutionBridge,
            buy_sell_allowed=bool(gv.global_args.buy_sell),
            trailing_stop_pts=float(gv.global_args.trailing_stop or 0),
            dynamic_tp_enabled=bool(gv.global_args.dynamic_take_profit),
            user_strategy=self.strategy,
            raw_dataframe=self.frame,
            historic_mode_instance=self,
            point_size=point_size
        )
        self.cerebro.run()

        self.profit = self.cerebro.broker.getvalue() - self.start_cash
        last_bar = self.frame.iloc[-1]
        self.set_finish_resume(symbol, last_bar)

    def set_finish_resume(self, symbol, frame: pd.Series):
        logger.info(f"{symbol}: Сборка финального резюме бэктеста...")

        if hasattr(self, 'write_in_excell'):
            self.write_in_excell(symbol, self.frame)

        pft = self.get_profit_sum()

        try:
            lot = Lot[symbol].value
        except (KeyError, NameError):
            logger.warning(f"Символ {symbol} не найден в Lot Enum. Используем лот по умолчанию = 1")
            lot = 1

        last_close_price = float(frame['close'])
        lot_cost = last_close_price * lot  # Стоимость 1 полного лота в рублях

        finish_profit = pft * lot
        finish_drawdown = self.max_drawdown * lot

        # Комиссия от полного оборота лота (вход + выход = 0.0657% от стоимости лота на сделку)
        total_commission = (lot_cost * 0.0657 / 100) * self.orders_count
        net_profit = finish_profit - total_commission
        buy_eff = (float(self.buy_profit_count) / self.buy_orders_count * 100) if self.buy_orders_count > 0 else None
        sell_eff = (float(self.sell_profit_count) / self.sell_orders_count * 100) if self.sell_orders_count > 0 else None

        data = {
            'symbol': symbol,
            'mode_buy_sell': gv.global_args.buy_sell,
            'deals_count': self.orders_count,
            'buy_deals': self.buy_orders_count,
            'buy_efficiency': buy_eff,
            'sell_deals': self.sell_orders_count,
            'sell_efficiency': sell_eff,
            'profit': pft,
            'profit_deals': self.profit_orders_count,
            'efficiency': self.get_efficiency(),
            'lot': lot,
            'last_price': last_close_price,
            'lot_cost': round(lot_cost, 2),
            'finish_profit': round(finish_profit, 2),
            'profit-commision': round(net_profit, 2),
            'profit_pct': round((net_profit / lot_cost) * 100, 2) if lot_cost > 0 else None,
            'max_drawdown': round(finish_drawdown, 2),
            'recovery_factor': round(net_profit / finish_drawdown, 2) if finish_drawdown > 0 else None
        }

        try:
            queue.set_data_to_queue(data)
        except NameError:
            logger.error("Модуль queue не инициализирован или метод set_data_to_queue недоступен.")

        print(f"{symbol}: Processing finished.")
        return



class BacktraderExecutionBridge(bt.Strategy):
    params = (
        ('buy_sell_allowed', True),
        ('trailing_stop_pts', 0),
        ('dynamic_tp_enabled', False),
        ('user_strategy', None),
        ('raw_dataframe', None),
        ('historic_mode_instance', None),
        ('point_size', 0.00001),
    )

    def __init__(self):
        self.data_signals = self.data0
        self.data_execution = self.data0

        self.is_position_open = False
        self.is_buy = True
        self.stop_loss = None
        self.take_profit = None
        self.open_price_exec = 0.0
        self.current_step = 0

        # Отложенный сигнал с закрытия предыдущего бара для входа на открытии текущего
        self.pending_signal = 0
        self.pending_sl = None
        self.pending_tp = None
        self.trailing_stop_pts = float(self.p.trailing_stop_pts or 0)
        self.point_size = float(self.p.point_size or 0.01)

        # Расчёт максимальной просадки с учётом плавающего PnL
        self.peak_balance = self.broker.get_cash()
        self.max_drawdown = 0.0

    def stop(self):
        if self.is_position_open:
            close_price = float(self.data_execution.close[0])
            trade_profit = (close_price - self.open_price_exec) if self.is_buy else (self.open_price_exec - close_price)
            self.record_manual_trade(trade_profit)

        if self.p.historic_mode_instance:
            self.p.historic_mode_instance.max_drawdown = self.max_drawdown

    def _get_strategy_levels(self, is_buy: bool):
        """Забирает у стратегии уровни SL и TP для конкретного направления."""
        strat = self.p.user_strategy
        if not strat:
            return None, None

        if is_buy:
            sl = getattr(strat, 'buy_sl', getattr(strat, 'stop_loss', None))
            tp = getattr(strat, 'buy_tp', getattr(strat, 'take_profit', None))
        else:
            sl = getattr(strat, 'sell_sl', getattr(strat, 'stop_loss', None))
            tp = getattr(strat, 'sell_tp', getattr(strat, 'take_profit', None))

        return sl, tp

    def record_manual_trade(self, trade_profit):
        hm = self.p.historic_mode_instance
        if hm:
            hm.orders_count += 1
            if trade_profit > 0:
                hm.profit_orders_count += 1

            if self.is_buy:
                hm.buy_orders_count += 1
                if trade_profit > 0:
                    hm.buy_profit_count += 1
            else:
                hm.sell_orders_count += 1
                if trade_profit > 0:
                    hm.sell_profit_count += 1

            self.broker.set_cash(self.broker.get_cash() + trade_profit)
        self.is_position_open = False
        self.stop_loss = None
        self.take_profit = None

    def _validate_levels(self, is_buy, entry_price, sl, tp):
        """Проверяет корректность расположения начальных SL и TP относительно цены входа."""
        valid_sl = sl
        valid_tp = tp

        if is_buy:
            if valid_sl is not None and valid_sl >= entry_price:
                logger.debug(f"BUY: Некорректный SL ({valid_sl}) >= цены входа ({entry_price}). SL сброшен.")
                valid_sl = None
            if valid_tp is not None and valid_tp <= entry_price:
                logger.debug(f"BUY: Некорректный TP ({valid_tp}) <= цены входа ({entry_price}). TP сброшен.")
                valid_tp = None
        else:
            if valid_sl is not None and valid_sl <= entry_price:
                logger.debug(f"SELL: Некорректный SL ({valid_sl}) <= цены входа ({entry_price}). SL сброшен.")
                valid_sl = None
            if valid_tp is not None and valid_tp >= entry_price:
                logger.debug(f"SELL: Некорректный TP ({valid_tp}) >= цены входа ({entry_price}). TP сброшен.")
                valid_tp = None

        return valid_sl, valid_tp

    def next(self):
        if self.trailing_stop_pts != 0 and self.stop_loss is not None:
            dist = self.trailing_stop_pts * self.point_size

        if self.current_step >= len(self.p.raw_dataframe):
            return

        open_price = float(self.data_execution.open[0])
        low_price = float(self.data_execution.low[0])
        high_price = float(self.data_execution.high[0])
        close_price = float(self.data_execution.close[0])
        signal_code = int(self.data_signals.signal_code[0])
        close_signal_code = int(self.data_signals.close_signal_code[0])

        # 1. Исполнение отложенного сигнала прошлого бара на открытии текущей свечи
        if not self.is_position_open and self.pending_signal != 0:
            if self.pending_signal == 1:
                self.is_position_open = True
                self.is_buy = True
                self.open_price_exec = open_price
                self.stop_loss, self.take_profit = self._validate_levels(
                    True, open_price, self.pending_sl, self.pending_tp
                )
            elif self.pending_signal == -1 and self.p.buy_sell_allowed:
                self.is_position_open = True
                self.is_buy = False
                self.open_price_exec = open_price
                self.stop_loss, self.take_profit = self._validate_levels(
                    False, open_price, self.pending_sl, self.pending_tp
                )
            self.pending_signal = 0
            self.pending_sl = None
            self.pending_tp = None

        # 2. Сопровождение открытой позиции
        if self.is_position_open:
            # Трейлинг-стоп
            if self.p.trailing_stop_pts != 0 and self.stop_loss is not None:
                dist = self.p.trailing_stop_pts * self.p.point_size
                if self.is_buy:
                    self.stop_loss = max(self.stop_loss, close_price - dist)
                else:
                    self.stop_loss = min(self.stop_loss, close_price + dist)

            # Динамический тейк-профит
            if self.p.dynamic_tp_enabled and self.p.user_strategy:
                current_row_df = self.p.raw_dataframe.iloc[self.current_step: self.current_step + 1]
                self.p.user_strategy.sltp_startegy(current_row_df)
                new_tp = getattr(self.p.user_strategy, 'take_profit', None)
                if new_tp is not None:
                    self.take_profit = new_tp

            # Проверка выходов по SL, TP или сигналу закрытия стратегии
            if self.is_buy:
                if self.stop_loss is not None and low_price <= self.stop_loss:
                    self.record_manual_trade(self.stop_loss - self.open_price_exec)
                elif self.take_profit is not None and high_price >= self.take_profit:
                    self.record_manual_trade(self.take_profit - self.open_price_exec)
                elif close_signal_code == 1:
                    self.record_manual_trade(close_price - self.open_price_exec)
            else:
                if self.stop_loss is not None and high_price >= self.stop_loss:
                    self.record_manual_trade(self.open_price_exec - self.stop_loss)
                elif self.take_profit is not None and low_price <= self.take_profit:
                    self.record_manual_trade(self.open_price_exec - self.take_profit)
                elif close_signal_code == -1:
                    self.record_manual_trade(self.open_price_exec - close_price)

        # 3. Оценка сигналов по закрытию текущей свечи для входа на следующей
        if not self.is_position_open and signal_code != 0:
            can_open_buy = (signal_code == 1)
            can_open_sell = (signal_code == -1 and self.p.buy_sell_allowed)

            if can_open_buy or can_open_sell:
                self.pending_signal = signal_code
                if self.p.user_strategy:
                    current_row_df = self.p.raw_dataframe.iloc[self.current_step: self.current_step + 1]
                    self.p.user_strategy.sltp_startegy(current_row_df)
                    self.pending_sl = getattr(self.p.user_strategy, 'stop_loss', None)
                    self.pending_tp = getattr(self.p.user_strategy, 'take_profit', None)

        # 4. Обновление максимальной просадки с учётом плавающего результата
        floating_pnl = 0.0
        if self.is_position_open:
            worst_price = low_price if self.is_buy else high_price
            floating_pnl = (worst_price - self.open_price_exec) if self.is_buy else (self.open_price_exec - worst_price)

        current_equity = self.broker.get_cash() + floating_pnl
        if current_equity > self.peak_balance:
            self.peak_balance = current_equity

        current_dd = self.peak_balance - current_equity
        if current_dd > self.max_drawdown:
            self.max_drawdown = current_dd

        if self.p.historic_mode_instance:
            self.p.historic_mode_instance.max_drawdown = self.max_drawdown

        self.current_step += 1
