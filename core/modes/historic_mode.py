import backtrader as bt
import pandas as pd
import numpy as np
from models.mode import Mode
import core.app_logger as app_logger
import core.global_vars as gv
from models.lots_enum import Lot
import core.queue_handler as queue
from mt5.mt5_actions import MT5_actions as mt5_a
from typing import override

import os
import io
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from openpyxl.drawing.image import Image as XLImage

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
        self.trades_history = []

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

        # Расчёт индикаторов и сигналов стратегии
        df = self.strategy.update_values(self.symbol, df, df)
        df = self.strategy.update_strategy(df)

        # Универсальная очистка дубликатов, где бы ни хранилось время
        before_len = len(df)
        if 'time' in df.columns:
            df = df.drop_duplicates(subset=['time'], keep='first').sort_values('time').reset_index(drop=True)
        elif 'datetime' in df.columns:
            df = df.drop_duplicates(subset=['datetime'], keep='first').sort_values('datetime').reset_index(drop=True)
        else:
            # Если время находится в индексе датафрейма
            df = df[~df.index.duplicated(keep='first')].sort_index().reset_index(drop=True)

        if len(df) != before_len:
            logger.warning(f"{self.symbol}: Удалено {before_len - len(df)} дублей! Было {before_len}, стало {len(df)}.")

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

    @override
    def lets_trade(self, symbol=None):
        target_symbol = symbol or self.symbol
        self.prepare_data()
        point_size = self.get_symbol_point(target_symbol)

        try:
            base_lot = Lot[target_symbol].value
        except (KeyError, NameError):
            base_lot = 1

        self.cerebro.addstrategy(
            BacktraderExecutionBridge,
            buy_sell_allowed=bool(gv.global_args.buy_sell),
            trailing_stop=gv.global_args.trailing_stop,
            atr_trailing_mult=2.5,
            dynamic_tp_enabled=bool(gv.global_args.dynamic_take_profit),
            user_strategy=self.strategy,
            raw_dataframe=self.frame,
            historic_mode_instance=self,
            point_size=point_size,
            start_cash=self.start_cash,
            base_lot_size=base_lot,
            capital_usage=0.95,
            risk_per_trade=0.02
        )

        self.cerebro.run()

        last_bar = self.frame.iloc[-1]
        self.set_finish_resume(target_symbol, last_bar)

    def export_report_to_excel(self, symbol: str):
        """Потокобезопасно строит график и сохраняет Excel-отчёт с полным логированием."""
        try:
            df = self.frame.reset_index(drop=True)
            trades = getattr(self, 'trades_history', [])

            if df.empty or not trades:
                logger.warning(f"{symbol}: Пропуск создания графика (df.empty={df.empty}, сделок={len(trades)})")
                return

            # Получаем абсолютный путь к папке logs/frames от корня проекта
            base_dir = os.getcwd()
            out_dir = os.path.join(base_dir, "logs", "frames")
            os.makedirs(out_dir, exist_ok=True)
            excel_path = os.path.join(out_dir, f"chart_{symbol}.xlsx")

            # Создаём 3 оси через subplots (без индексации gs)
            fig = Figure(figsize=(16, 11))
            FigureCanvasAgg(fig)
            axes = fig.subplots(3, 1, gridspec_kw={'height_ratios': [3, 1.2, 1]})
            ax1, ax2, ax3 = axes

            # --- Панель 1: Цена и точки сделок ---
            ax1.plot(df.index, df['close'], label='Close', color='#1f77b4', linewidth=1.1, alpha=0.9)
            if 'EMA' in df.columns:
                ax1.plot(df.index, df['EMA'], label='EMA 50', color='#ff7f0e', linewidth=1.0, alpha=0.8)

            # Находим колонки Боллинджера через next() без квадратных скобок
            bbu_col = next((c for c in df.columns if c.startswith('BBU_')), None)
            bbl_col = next((c for c in df.columns if c.startswith('BBL_')), None)
            if bbu_col and bbl_col:
                ax1.plot(df.index, df[bbu_col], color='gray', linestyle='--', linewidth=0.7, alpha=0.6)
                ax1.plot(df.index, df[bbl_col], color='gray', linestyle='--', linewidth=0.7, alpha=0.6)
                ax1.fill_between(df.index, df[bbl_col], df[bbu_col], color='gray', alpha=0.07)

            for t in trades:
                e_idx = min(t['entry_step'], len(df) - 1)
                x_idx = min(t['exit_step'], len(df) - 1)
                e_p, x_p = t['entry_price'], t['exit_price']
                is_win = t['net_pnl'] > 0

                ax1.scatter(e_idx, e_p, marker='^' if t['direction'] == 'BUY' else 'v',
                            color='green' if t['direction'] == 'BUY' else 'purple', s=65, zorder=5)
                exit_color = '#00aa00' if is_win else '#dd0000'
                ax1.scatter(x_idx, x_p, marker='o' if is_win else 'x', color=exit_color, s=50, zorder=5)
                ax1.plot([e_idx, x_idx], [e_p, x_p], color=exit_color, linestyle=':', linewidth=1.1, alpha=0.8)

            net_pft = self.get_profit_sum()
            eff = self.get_efficiency() or 0
            ax1.set_title(
                f"{symbol} | Сделок: {len(trades)} | Винрейт: {eff:.1f}% | Прибыль: {net_pft:.2f} руб. ({net_pft/self.start_cash*100:.2f}%)",
                fontsize=13, fontweight='bold'
            )
            ax1.grid(True, alpha=0.25)
            ax1.legend(loc='upper left')

            # --- Панель 2: Кривая капитала ---
            trade_nums = list(range(len(trades) + 1))
            balances = [self.start_cash] + [t['balance'] for t in trades]
            line_color = '#2ca02c' if net_pft >= 0 else '#d62728'
            ax2.plot(trade_nums, balances, color=line_color, linewidth=2)
            ax2.axhline(self.start_cash, color='black', linestyle='--', linewidth=0.9, alpha=0.6)
            ax2.fill_between(trade_nums, self.start_cash, balances, alpha=0.15, color=line_color)
            ax2.set_ylabel("Депозит (руб.)")
            ax2.grid(True, alpha=0.25)

            # --- Панель 3: PnL каждой сделки ---
            pnls = [t['net_pnl'] for t in trades]
            ax3.bar(range(1, len(trades) + 1), pnls, color=['#2ca02c' if p > 0 else '#d62728' for p in pnls], alpha=0.85)
            ax3.axhline(0, color='black', linewidth=0.8)
            ax3.set_xlabel("Номер сделки")
            ax3.set_ylabel("PnL (руб.)")
            ax3.grid(True, alpha=0.25)

            fig.tight_layout()
            img_buf = io.BytesIO()
            fig.savefig(img_buf, format='png', dpi=140)
            img_buf.seek(0)

            # Записываем в Excel
            trades_df = pd.DataFrame(trades)
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                trades_df.to_excel(writer, sheet_name='Сделки', index=False)
                ws_chart = writer.book.create_sheet(title='График')
                ws_chart.add_image(XLImage(img_buf), 'A1')

            logger.info(f"{symbol}: Excel-отчёт с графиком УСПЕШНО сохранён в {excel_path}")

        except Exception as e:
            logger.error(f"{symbol}: Ошибка при создании Excel-графика: {e}", exc_info=True)

    def set_finish_resume(self, symbol, frame: pd.Series):
        logger.info(f"{symbol}: Сборка финального резюме бэктеста...")
        self.export_report_to_excel(symbol)

        if hasattr(self, 'write_in_excell'):
            self.write_in_excell(symbol, self.frame)

        # В self.profit теперь лежит ЧИСТАЯ прибыль в рублях с учетом сложного процента и всех комиссий
        net_profit = self.get_profit_sum()
        final_balance = self.start_cash + net_profit

        try:
            base_lot = Lot[symbol].value
        except (KeyError, NameError):
            base_lot = 1

        last_close_price = float(frame['close'])
        one_lot_cost = last_close_price * base_lot

        # Сколько лотов мог купить бот к концу теста
        final_lots = int((final_balance * 0.95) // one_lot_cost) if one_lot_cost > 0 else 0

        # Доходность в % от стартового депозита (start_cash)
        profit_pct = (net_profit / self.start_cash) * 100 if self.start_cash > 0 else 0.0

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
            'start_cash': round(self.start_cash, 2),
            'final_balance': round(final_balance, 2),
            'profit_deals': self.profit_orders_count,
            'efficiency': self.get_efficiency(),
            'base_lot': base_lot,
            'final_lots': final_lots,
            'last_price': last_close_price,
            'net_profit': round(net_profit, 2),
            'profit_pct': round(profit_pct, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'recovery_factor': round(net_profit / self.max_drawdown, 2) if self.max_drawdown > 0 else None
        }
        
        try:
            queue.set_data_to_queue(data)
            self.export_report_to_excel(symbol)
        except NameError:
            logger.error("Модуль queue не инициализирован или метод set_data_to_queue недоступен.")
        
        print(f"{symbol}: Processing finished.")
        return




class BacktraderExecutionBridge(bt.Strategy):
    params = (
        ('buy_sell_allowed', True),
        ('trailing_stop', None),     # Принимает "atr", число (650) или 0/None
        ('atr_trailing_mult', 1.5),  # Множитель для режима "atr"
        ('dynamic_tp_enabled', False),
        ('user_strategy', None),
        ('raw_dataframe', None),
        ('historic_mode_instance', None),
        ('point_size', 0.01),
        ('start_cash', 10000.0),
        ('base_lot_size', 1),
        ('capital_usage', 0.95),
        ('risk_per_trade', None),
        ('commission_pct', 0.0657),
    )

    def __init__(self):
        self.trades_history = []
        self.open_step_exec = 0
        self.data_signals = self.data0
        self.data_execution = self.data0

        self.is_position_open = False
        self.is_buy = True
        self.stop_loss = None
        self.take_profit = None
        self.open_price_exec = 0.0
        self.current_step = 0
        self.current_lots = 0

        self.pending_signal = 0
        self.pending_sl = None
        self.pending_tp = None
        self.point_size = float(self.p.point_size or 0.01)

        # Разбор параметра trailing_stop ("atr" или число пунктов)
        ts_raw = str(self.p.trailing_stop).strip().lower() if self.p.trailing_stop is not None else "0"
        if ts_raw == "atr":
            self.ts_mode = "atr"
            self.trailing_stop_pts = 0.0
        else:
            self.ts_mode = "pts"
            try:
                self.trailing_stop_pts = float(ts_raw)
            except ValueError:
                self.trailing_stop_pts = 0.0

        self.current_balance = float(self.p.start_cash)
        self.total_commission_paid = 0.0
        self.peak_balance = self.current_balance
        self.max_drawdown = 0.0

    def _get_trailing_distance(self) -> float:
        """Возвращает дистанцию трейлинг-стопа в зависимости от режима (-ts 'atr' или пункты)."""
        if self.ts_mode == "atr":
            if self.p.raw_dataframe is not None and 'ATR' in self.p.raw_dataframe.columns:
                if self.current_step < len(self.p.raw_dataframe):
                    atr_val = self.p.raw_dataframe['ATR'].iloc[self.current_step]
                    if pd.notna(atr_val) and float(atr_val) > 0:
                        return float(atr_val) * float(self.p.atr_trailing_mult)
            return 0.0

        if self.ts_mode == "pts" and self.trailing_stop_pts > 0:
            return self.trailing_stop_pts * self.point_size

        return 0.0


    def _calculate_lots(self, entry_price: float, stop_loss: float = None) -> int:
        """Рассчитывает количество биржевых лотов исходя из текущего баланса."""
        lot_cost = entry_price * self.p.base_lot_size
        if lot_cost <= 0 or self.current_balance < lot_cost:
            return 0

        # 1. Максимум лотов, который позволяет купить текущий баланс
        max_affordable_lots = int((self.current_balance * self.p.capital_usage) // lot_cost)

        # 2. Если задан риск-менеджмент по стопу (например, 2% риска на сделку)
        if self.p.risk_per_trade and stop_loss is not None:
            risk_per_share = abs(entry_price - stop_loss)
            if risk_per_share > 0:
                risk_rub = self.current_balance * self.p.risk_per_trade
                risk_lots = int(risk_rub // (risk_per_share * self.p.base_lot_size))
                return max(1, min(max_affordable_lots, risk_lots)) if max_affordable_lots >= 1 else 0

        return max_affordable_lots

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

    def record_manual_trade(self, price_diff: float, exit_reason: str = "Trade"):
        """Фиксирует сделку с учетом количества лотов и комиссии, обновляя баланс."""
        executed_lots = self.current_lots
        shares = executed_lots * self.p.base_lot_size
        gross_pnl = price_diff * shares

        # Комиссия от объема входа в рублях
        position_value = self.open_price_exec * shares
        commission = position_value * (self.p.commission_pct / 100.0)
        net_pnl = gross_pnl - commission

        self.current_balance += net_pnl
        self.total_commission_paid += commission

        exit_price = self.open_price_exec + price_diff if self.is_buy else self.open_price_exec - price_diff
        self.trades_history.append({
            'direction': 'BUY' if self.is_buy else 'SELL',
            'entry_step': self.open_step_exec,
            'exit_step': self.current_step,
            'entry_price': self.open_price_exec,
            'exit_price': exit_price,
            'lots': executed_lots,
            'net_pnl': net_pnl,
            'balance': self.current_balance,
            'reason': exit_reason
        })

        self.is_position_open = False
        self.current_lots = 0

        hm = self.p.historic_mode_instance
        if hm:
            hm.trades_history = self.trades_history
            hm.orders_count += 1
            hm.profit = self.current_balance - self.p.start_cash
            if net_pnl > 0:
                hm.profit_orders_count += 1

            if self.is_buy:
                hm.buy_orders_count += 1
                if net_pnl > 0:
                    hm.buy_profit_count += 1
            else:
                hm.sell_orders_count += 1
                if net_pnl > 0:
                    hm.sell_profit_count += 1


    def _validate_levels(self, is_buy, entry_price, sl, tp):
        """Проверяет корректность начальных SL и TP относительно реальной цены открытия с защитой от гэпов."""
        valid_sl = sl
        valid_tp = tp

        # Получаем текущий ATR для страховочного уровня при гэпе
        atr_val = 0.0
        if self.p.raw_dataframe is not None and 'ATR' in self.p.raw_dataframe.columns:
            if self.current_step < len(self.p.raw_dataframe):
                raw_atr = self.p.raw_dataframe['ATR'].iloc[self.current_step]
                if pd.notna(raw_atr) and float(raw_atr) > 0:
                    atr_val = float(raw_atr)

        if is_buy:
            if valid_sl is None or valid_sl >= entry_price:
                valid_sl = (entry_price - atr_val * 1.5) if atr_val > 0 else None
                logger.debug(f"BUY: Гэп на открытии. Установлен страховочный SL={valid_sl} от входа {entry_price}.")
            if valid_tp is not None and valid_tp <= entry_price:
                valid_tp = (entry_price + atr_val * 2.0) if atr_val > 0 else None
        else:
            if valid_sl is None or valid_sl <= entry_price:
                valid_sl = (entry_price + atr_val * 1.5) if atr_val > 0 else None
                logger.debug(f"SELL: Гэп на открытии. Установлен страховочный SL={valid_sl} от входа {entry_price}.")
            if valid_tp is not None and valid_tp >= entry_price:
                valid_tp = (entry_price - atr_val * 2.0) if atr_val > 0 else None

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
                sl, tp = self._validate_levels(True, open_price, self.pending_sl, self.pending_tp)
                lots = self._calculate_lots(open_price, sl)
                if lots >= 1:
                    self.is_position_open = True
                    self.is_buy = True
                    self.open_price_exec = open_price
                    self.stop_loss = sl
                    self.take_profit = tp
                    self.current_lots = lots
                    self.open_step_exec = self.current_step

            elif self.pending_signal == -1 and self.p.buy_sell_allowed:
                sl, tp = self._validate_levels(False, open_price, self.pending_sl, self.pending_tp)
                lots = self._calculate_lots(open_price, sl)
                if lots >= 1:
                    self.is_position_open = True
                    self.is_buy = False
                    self.open_price_exec = open_price
                    self.stop_loss = sl
                    self.take_profit = tp
                    self.current_lots = lots
                    self.open_step_exec = self.current_step

            self.pending_signal = 0
            self.pending_sl = None
            self.pending_tp = None

        # 2. Сопровождение открытой позиции
                # 2. Сопровождение открытой позиции
        if self.is_position_open:
            # Сначала проверяем выход по уровням, установленным на ПРОШЛОМ баре (без заглядывания в будущее)
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

            # Если позиция всё ещё открыта после проверки — обновляем Trailing Stop и Dynamic TP на СЛЕДУЮЩИЙ бар
                        # В BacktraderExecutionBridge.next(self):
            if self.is_position_open:
                dist = self._get_trailing_distance()
                if dist > 0 and self.stop_loss is not None:
                    # Если цена прошла в нашу сторону больше 1.2 * дистанции — сначала гарантируем безубыток с учетом комиссии
                    breakeven_buffer = self.open_price_exec * (self.p.commission_pct / 100.0) * 1.5
                    if self.is_buy and close_price >= self.open_price_exec + (dist * 0.8):
                        self.stop_loss = max(self.stop_loss, self.open_price_exec + breakeven_buffer, close_price - dist)
                    elif not self.is_buy and close_price <= self.open_price_exec - (dist * 0.8):
                        self.stop_loss = min(self.stop_loss, self.open_price_exec - breakeven_buffer, close_price + dist)

            if self.p.dynamic_tp_enabled and self.p.user_strategy:
                current_row_df = self.p.raw_dataframe.iloc[self.current_step: self.current_step + 1]
                self.p.user_strategy.sltp_startegy(current_row_df)
                _, new_tp = self._get_strategy_levels(self.is_buy)
                if new_tp is not None:
                    # Защита: динамический TP не имеет права опускаться ниже цены входа (для Buy) или подниматься выше (для Sell)
                    if self.is_buy and new_tp > self.open_price_exec:
                        self.take_profit = new_tp
                    elif not self.is_buy and new_tp < self.open_price_exec:
                        self.take_profit = new_tp


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

         # 4. Обновление максимальной просадки с учётом плавающего результата и объема
        floating_pnl = 0.0
        if self.is_position_open:
            shares = self.current_lots * self.p.base_lot_size
            worst_price = low_price if self.is_buy else high_price
            floating_pnl = ((worst_price - self.open_price_exec) if self.is_buy else (self.open_price_exec - worst_price)) * shares

        current_equity = self.current_balance + floating_pnl
        if current_equity > self.peak_balance:
            self.peak_balance = current_equity

        current_dd = self.peak_balance - current_equity
        if current_dd > self.max_drawdown:
            self.max_drawdown = current_dd

        if self.p.historic_mode_instance:
            self.p.historic_mode_instance.max_drawdown = self.max_drawdown

        self.current_step += 1
