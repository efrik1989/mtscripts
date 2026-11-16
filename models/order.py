import time
import random
import MetaTrader5 as mt5
import core.mt5.mt5_trade as trade
from core.mt5.mt5_actions import MT5_actions as mt5_a
import core.global_vars as gv
import core.app_logger as app_logger

logger = app_logger.get_logger(__name__)


class Order:
    def __init__(
        self,
        open_price: float,
        symbol: str,
        strategy,
        atr_value: float,
        isBuy: bool,
        lots: float = 1.0,
        magic: int = 7777
    ):
        self.open_price = float(open_price)
        self.symbol = symbol
        self.strategy = strategy
        self.atr = float(atr_value)
        self.isBuy = bool(isBuy)
        self.lots = float(lots)
        self.magic = int(magic)
        self.direction = "buy" if self.isBuy else "sell"

        # Множители сопровождения из стратегии
        trail_mult = getattr(self.strategy, 'atr_trailing_mult', None) or 2.5
        be_mult = getattr(self.strategy, 'breakeven_atr_mult', None) or 1.8

        self.stop_atr = self.atr * trail_mult
        self.be_atr = self.atr * be_mult
        self.START_TRAILING = self.stop_atr

        # Расчёт дистанций SL и TP от уровней стратегии
        sl_dist, tp_dist = self._calculate_sl_tp_distances()
        self.take_atr = tp_dist

        self.trade_obj = trade.Trade(symbol, self.lots, sl_dist, tp_dist)
        if hasattr(self.trade_obj, 'magic'):
            self.trade_obj.magic = self.magic

        self.stop_loss = None
        self.take_profit = None
        self.id = random.randint(0, 100000)
        self.is_opened = False

        self.sim_log_path = f"{gv.global_args.logs_directory}\\{gv.global_args.monney_mode}\\simulation.txt"

    def _calculate_sl_tp_distances(self) -> tuple[float, float]:
        """Вычисляет дистанции SL и TP в единицах цены на основе расчётов стратегии."""
        strat_sl = getattr(self.strategy, 'buy_sl', None) if self.isBuy else getattr(self.strategy, 'sell_sl', None)
        strat_tp = getattr(self.strategy, 'buy_tp', None) if self.isBuy else getattr(self.strategy, 'sell_tp', None)

        sl_dist = abs(self.open_price - float(strat_sl)) if strat_sl else (self.atr * 1.5)
        tp_dist = abs(float(strat_tp) - self.open_price) if strat_tp else (self.atr * 4.5)
        return sl_dist, tp_dist

    def open_position(self) -> bool:
        """Пересчитывает дистанции SL/TP по самой свежей цене и открывает позицию в MT5."""
        sl_dist, tp_dist = self._calculate_sl_tp_distances()
        self.trade_obj.stop_loss = sl_dist
        self.trade_obj.take_profit = tp_dist
        self.trade_obj.lot = self.lots

        try:
            self.trade_obj.position_open(self.isBuy, not self.isBuy)
        except Exception as e:
            logger.error(f"{self.symbol}: Ошибка при вызове position_open: {e}")
            return False

        positions = mt5.positions_get(symbol=self.symbol)
        if positions and len(positions) > 0:
            self.id = positions[0].ticket
            self.open_price = float(positions[0].price_open)
            self.is_opened = True
            logger.info(f"{self.symbol}: Позиция успешно открыта. Ticket=#{self.id}, Lots={self.lots}, Price={self.open_price}")
            return True

        logger.warning(f"{self.symbol}: Заявка отправлена, но позиция в MT5 не найдена.")
        self.is_opened = False
        return False


    def position_check(self) -> bool:
        """Возвращает True, если позиция по инструменту уже открыта в MT5."""
        res = self.trade_obj.position_check()
        if res is not None:
            return bool(res)
        positions = mt5.positions_get(symbol=self.symbol)
        return positions is not None and len(positions) > 0


    def close_position(self):
        try:
            self.trade_obj.position_close()
            self.is_opened = False
        except Exception as e:
            logger.error(f"{self.symbol}: Ошибка при закрытии позиции: {e}")

    def traling_stop(self, current_price: float, indent):
        """Переводит дистанции ATR из рублей в пункты инструмента и обновляет трейлинг-стоп + безубыток."""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None or symbol_info.point <= 0:
            return

        point = symbol_info.point

        if indent == "atr":
            trailing_pts = self.stop_atr / point
            min_profit_pts = self.stop_atr / point
        else:
            trailing_pts = float(indent)
            min_profit_pts = float(indent)

        breakeven_pts = self.be_atr / point

        self.trade_obj.check_and_update_trailing(
            symbol=self.symbol,
            trailing_points=trailing_pts,
            min_profit_points=min_profit_pts,
            breakeven_trigger_pts=breakeven_pts
        )

    def set_new_take_profit(self, new_tp):
        if new_tp is not None and new_tp != "":
            self.trade_obj.change_take_profit(self.symbol, float(new_tp))

    # --- Методы для симуляции ---
    def open_fake_position(self):
        logger.info(f"Order.id = {self.id}")
        if self.isBuy:
            self.fake_buy()
        else:
            self.fake_sell()
        with open(self.sim_log_path, "a") as output_file:
            output_file.write(
                f"{self.symbol}, Order.id = {self.id}, {self.direction}: {self.open_price}, "
                f"SL: {self.stop_loss}, TP: {self.take_profit}, {time.asctime()}\n"
            )

    def fake_buy(self):
        self.stop_loss = self.open_price - self.stop_atr
        self.take_profit = self.open_price + self.take_atr

    def fake_sell(self):
        self.stop_loss = self.open_price + self.stop_atr
        self.take_profit = self.open_price - self.take_atr

    def fake_buy_sell_close(self, current_price):
        logger.info(f"Order.id = {self.id}")
        profit = (current_price - self.open_price) if self.isBuy else (self.open_price - current_price)
        with open(self.sim_log_path, "a") as output_file:
            output_file.write(f"{self.symbol}, Order.id = {self.id}, close_position: {current_price}, {time.asctime()}\n")
            output_file.write(f"{self.symbol}, Order.id = {self.id}, profit: {profit}, {time.asctime()}\n")
        return profit

    def fake_traling_stop(self, current_price, indent):
        if indent == "atr":
            indent = self.stop_atr
        point = mt5.symbol_info(self.symbol).point
        if self.isBuy:
            new_value = current_price - self.stop_atr
            is_need = (self.stop_loss + (indent * point)) <= new_value
        else:
            new_value = current_price + self.stop_atr
            is_need = (self.stop_loss - (indent * point)) >= new_value

        if is_need:
            self.stop_loss = new_value
            with open(self.sim_log_path, "a") as output_file:
                output_file.write(f"{self.symbol}, SL changed: {self.stop_loss}, {time.asctime()}\n")

    def fake_set_new_take_profit(self, new_tp):
        if new_tp is not None and new_tp != "":
            self.take_profit = new_tp

    def to_string(self):
        return f"{self.open_price} {self.symbol} {self.isBuy} lots={self.lots}"
