import backtrader as bt
import pandas as pd
import numpy as np
from models.mode import Mode
import core.app_logger as app_logger
import core.global_vars as gv

logger = app_logger.get_logger(__name__)

class GenericMT5Data(bt.feeds.PandasData):
    lines = ('signal_code', 'close_signal_code',)
    params = (
        ('signal_code', -1),
        ('close_signal_code', -1),
    )

class Historic_mode(Mode):
    def __init__(self, symbol, strategy):
        super().__init__(symbol, strategy)
        # Отключаем внутреннюю предзагрузку, чтобы полностью контролировать каждый шаг
        self.cerebro = bt.Cerebro(preload=False)
        self.start_cash = 10000.0
        self.cerebro.broker.setcash(self.start_cash)
        self.cerebro.broker.setcommission(commission=0.0)

        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        
        self.orders_count = 0
        self.profit_orders_count = 0
        self.profit = 0.0

    def get_efficiency(self):
        if self.orders_count == 0:
            return None
        return float(self.profit_orders_count) / float(self.orders_count) * 100

    def prepare_data(self):
        df = self.frame.copy()
        
        signal_map = {"Open_buy": 1, "Open_sell": -1, "NaN": 0}
        close_map = {"Close_buy": 1, "Close_sell": -1, "NaN": 0}
        
        df['signal_code'] = df['signal'].map(signal_map).fillna(0).astype(int)
        df['close_signal_code'] = df['close_signal'].map(close_map).fillna(0).astype(int)

        data_signals = GenericMT5Data(dataname=df)
        self.cerebro.adddata(data_signals)

    def lets_trade(self, symbol):
        self.prepare_data()
        
        self.cerebro.addstrategy(
            BacktraderExecutionBridge,
            buy_sell_allowed=gv.global_args.buy_sell,
            trailing_stop_pts=gv.global_args.trailing_stop,
            dynamic_tp_enabled=gv.global_args.dynamic_take_profit,
            user_strategy=self.strategy,      
            raw_dataframe=self.frame,
            historic_mode_instance=self  # Передаем ссылку наHistoric_mode для прямой записи результатов
        )
        results = self.cerebro.run()
        
        # Финальный расчет прибыли
        self.profit = self.cerebro.broker.getvalue() - self.start_cash
        
        # Если сделки были зафиксированы вручную, приоритет отдается им (для коротких юнит-тестов)
        if self.orders_count == 0:
            self.display_results(results[0])

    def display_results(self, strat):
        trade_stats = strat.analyzers.trades.get_analysis()
        if 'total' in trade_stats:
            self.orders_count = trade_stats['total'].get('closed', 0)
            if self.orders_count == 0:
                self.orders_count = trade_stats['total'].get('total', 0)
            
        if self.orders_count > 0 and 'won' in trade_stats:
            self.profit_orders_count = trade_stats['won'].get('count', 0)


class BacktraderExecutionBridge(bt.Strategy):
    params = (
        ('buy_sell_allowed', True),
        ('trailing_stop_pts', 0),
        ('dynamic_tp_enabled', False),
        ('user_strategy', None),
        ('raw_dataframe', None),
        ('historic_mode_instance', None),
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

    def stop(self):
        # Принудительное закрытие в конце истории, если сделка осталась открытой
        if self.is_position_open:
            close_price = float(self.data_execution.close[0])
            trade_profit = (close_price - self.open_price_exec) if self.is_buy else (self.open_price_exec - close_price)
            self.record_manual_trade(trade_profit)

    def record_manual_trade(self, trade_profit):
        """Вспомогательный метод для прямой мгновенной фиксации сделки в Historic_mode"""
        hm = self.p.historic_mode_instance
        if hm:
            hm.orders_count += 1
            if trade_profit > 0:
                hm.profit_orders_count += 1
            # Корректируем баланс брокера Backtrader напрямую
            self.broker.set_cash(self.broker.get_cash() + trade_profit)
        self.is_position_open = False

    def next(self):
        if self.current_step >= len(self.p.raw_dataframe):
            return

        current_row_df = self.p.raw_dataframe.iloc[self.current_step : self.current_step + 1]
        
        if self.p.user_strategy:
            self.p.user_strategy.sltp_startegy(current_row_df)

        signal_code = int(self.data_signals.signal_code[0])
        close_signal_code = int(self.data_signals.close_signal_code[0])
        
        open_price = float(self.data_execution.open[0])
        low_price = float(self.data_execution.low[0])
        high_price = float(self.data_execution.high[0])
        close_price = float(self.data_execution.close[0])

        # 1. Если позиция открыта, обрабатываем трейлинг-стоп и выходы по SL/TP
        if self.is_position_open:
            if self.p.trailing_stop_pts != 0:
                point = 0.00001
                dist = self.p.trailing_stop_pts * point
                if self.is_buy:
                    self.stop_loss = max(self.stop_loss, close_price - dist)
                else:
                    self.stop_loss = min(self.stop_loss, close_price + dist)

            if self.p.dynamic_tp_enabled:
                self.take_profit = self.p.user_strategy.take_profit

            # Высокоточная проверка SL/TP по экстремумам текущей свечи
            if self.is_buy:
                if low_price <= self.stop_loss:
                    trade_profit = self.stop_loss - self.open_price_exec
                    self.record_manual_trade(trade_profit)
                    self.current_step += 1
                    return
                elif high_price >= self.take_profit:
                    trade_profit = self.take_profit - self.open_price_exec
                    self.record_manual_trade(trade_profit)
                    self.current_step += 1
                    return
            else:
                if high_price >= self.stop_loss:
                    trade_profit = self.open_price_exec - self.stop_loss
                    self.record_manual_trade(trade_profit)
                    self.current_step += 1
                    return
                elif low_price <= self.take_profit:
                    trade_profit = self.open_price_exec - self.take_profit
                    self.record_manual_trade(trade_profit)
                    self.current_step += 1
                    return

            # Выход по встречному сигналу стратегии из Pandas DataFrame
            if (self.is_buy and close_signal_code == 1) or (not self.is_buy and close_signal_code == -1):
                trade_profit = (close_price - self.open_price_exec) if self.is_buy else (self.open_price_exec - close_price)
                self.record_manual_trade(trade_profit)
                self.current_step += 1
                return

        # 2. Логика входа по рыночному сигналу
        if not self.is_position_open:
            if signal_code == 1 or (self.p.buy_sell_allowed and signal_code == -1):
                self.is_buy = True if signal_code == 1 else False
                self.stop_loss = self.p.user_strategy.stop_loss
                self.take_profit = self.p.user_strategy.take_profit
                
                # Запоминаем точную цену открытия позиции
                self.open_price_exec = open_price 
                self.is_position_open = True

        self.current_step += 1
