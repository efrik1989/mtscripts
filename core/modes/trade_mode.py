from pandas.plotting import register_matplotlib_converters
from models.order import Order
from mt5.mt5_actions import MT5_actions as mt5_a
import core.app_logger as app_logger
from models.mode import Mode
import core.global_vars as gv

register_matplotlib_converters()
logger = app_logger.get_logger(__name__)


class Trade_mode(Mode):
    def __init__(self, symbol, strategy, config=None):
        super().__init__(symbol, strategy, config=config)

    def open_position_signal_checker(self, symbol, current_price, signal, atr_value):
        super().open_position_signal_checker()
        if self.order is not None:
            return

        is_buy_signal = (signal == "Open_buy")
        is_sell_signal = (self.buy_sell is True and signal == "Open_sell")

        if not (is_buy_signal or is_sell_signal):
            return

        logger.info(f"{symbol}: Обнаружен сигнал на открытие: {signal}")

        # Потокобезопасная проверка портфельного лимита и расчёт прогрессивного лота
        with self.risk_manager.order_lock:
            if not self.risk_manager.can_open_position(symbol):
                logger.info(f"{symbol}: Вход отклонен риск-менеджером (лимит позиций или маржа).")
                return

            # Получаем расчётный уровень SL из стратегии для точного расчёта лота от риска
            sl_price = self.strategy.buy_sl if is_buy_signal else self.strategy.sell_sl
            if sl_price is None:
                sl_price = getattr(self.strategy, 'stop_loss', None)

            progressive_lots = self.risk_manager.calculate_lots(symbol, current_price, sl_price)
            if progressive_lots <= 0:
                logger.warning(f"{symbol}: Расчётный объём <= 0, сделка пропущена.")
                return

            logger.info(f"{symbol}: Risk manager OK. Объём к открытию: {progressive_lots} лот.")
            self.order = Order(
                open_price=current_price,
                symbol=symbol,
                strategy=self.strategy,
                atr_value=atr_value,
                isBuy=is_buy_signal,
                lots=progressive_lots,
                magic=self.risk_manager.magic_number
            )
            if not self.open_n_check():
                # Если ордер не открылся на бирже — сбрасываем self.order, чтобы не блокировать инструмент
                self.order = None
            # Передаем рассчитанный прогрессивный объём в объект ордера
            self.order.lots = progressive_lots
            self.order.volume = progressive_lots
            self.order.magic = self.risk_manager.magic_number

            self.open_n_check()

    def close_position_signal_checker(self, symbol, close_signal):
        super().close_position_signal_checker()
        if isinstance(self.order, Order) and (
            close_signal == "Close_buy" or (self.buy_sell is True and close_signal == "Close_sell")
        ):
            logger.info(f"{symbol}: Сигнал на закрытие позиции: {close_signal}")
            self.order.close_position()
            self.order = None

    def dynamic_tp_checker(self, new_tp):
        super().dynamic_tp_checker()
        if isinstance(self.order, Order) and self.dynamic_take_profit:
            self.order.set_new_take_profit(new_tp)
            logger.info(f"Order to change TP: {self.order.id}, значение: {new_tp}")

    def trailing_stop_checker(self, current_price):
        super().trailing_stop_checker()
        if self.order is not None and self.trailing_stop != 0:
            self.order.traling_stop(current_price, self.trailing_stop)

    def signals_handler(self, symbol, current_price, signal, atr_value, close_signal):
        super().signals_handler()
        try:
            # 1. Сопровождение уже открытой позиции работает ВСЕГДА, даже если бар заблокирован на вход
            self.trailing_stop_checker(current_price)
            self.dynamic_tp_checker(self.strategy.take_profit)
            self.close_position_signal_checker(symbol, close_signal)

            # 2. Открытие новой позиции проверяем только если нет блокировки бара
            if not self.locker.is_bar_locked:
                self.open_position_signal_checker(symbol, current_price, signal, atr_value)

            # 3. Синхронизация состояния позиции с терминалом MT5
            self.check_opened_positions(symbol)

        except UnboundLocalError:
            logger.exception(f"{symbol}: Переменная или объект не в том месте!")

    def sl_tp_checker(self):
        pass

    def open_n_check(self) -> bool:
        if not self.order.position_check():
            self.order.open_price = self.get_current_price()
            opened = self.order.open_position()
            if opened:
                self.locker.is_bar_locked = True
            return opened
        else:
            self.locker.is_bar_locked = True
            return True

    def check_opened_positions(self, symbol):
        position = mt5_a.get_position_info(symbol)
        if position is None or len(position) == 0:
            self.order = None
