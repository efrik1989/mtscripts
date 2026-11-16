import math
import threading
import time
import MetaTrader5 as mt5
import core.app_logger as app_logger

logger = app_logger.get_logger(__name__)


class SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class RiskManager(metaclass=SingletonMeta):
    def __init__(
        self,
        trade_risk=0.0,
        lost_risk=0.0,
        cache_ttl=0.2,
        max_open_positions=3,
        risk_per_trade_pct=1.5,
        max_deposit_share=0.30,
        magic_number=7777
    ):
        if not hasattr(self, "_initialized"):
            self.trade_risk = float(trade_risk)
            self.lost_risk = float(lost_risk)
            self.max_open_positions = int(max_open_positions)
            self.risk_per_trade_pct = float(risk_per_trade_pct)
            self.max_deposit_share = float(max_deposit_share)
            self.magic_number = int(magic_number)

            self.account_info_dict = {}
            self.equity = 0.0
            self.balance = 0.0
            self.initial_balance = 0.0

            self._last_update_time = 0
            self._cache_ttl = cache_ttl

            self._lock = threading.RLock()
            # Внешний замок для атомарной проверки лимитов + отправки ордера из разных потоков
            self.order_lock = threading.Lock()

            self.trading_allowed = threading.Event()
            self.trading_allowed.set()

            self._initialized = True

    def _ensure_mt5_connected(self):
        if mt5.terminal_info() is None:
            logger.warning("MT5 connection lost. Re-initializing...")
            if not mt5.initialize():
                logger.error(f"Initialize failed: {mt5.last_error()}")
                return False
        return True

    def update_account_data(self, force=False):
        with self._lock:
            now = time.time()
            if force or (now - self._last_update_time) > self._cache_ttl:
                if not self._ensure_mt5_connected():
                    return False

                account_info = mt5.account_info()
                if account_info is not None:
                    self.account_info_dict = account_info._asdict()
                    self.equity = float(self.account_info_dict.get("equity", 0.0))
                    self.balance = float(self.account_info_dict.get("balance", self.equity))

                    if self.initial_balance == 0.0:
                        self.initial_balance = self.balance

                    self._last_update_time = now

                    if not self._check_emergency_stop():
                        self.trading_allowed.clear()
                    else:
                        self.trading_allowed.set()

                    return True
                return False
            return True

    def _check_emergency_stop(self):
        """Внутренняя проверка критического порога equity от начального баланса."""
        if self.initial_balance == 0.0:
            return True

        limit = self.initial_balance - ((self.initial_balance / 100.0) * self.lost_risk)

        if self.equity < limit:
            logger.critical(f"EMERGENCY STOP! Equity {self.equity} < Limit {limit} (Initial Balance: {self.initial_balance})")
            return False
        return True

    def is_tradable(self, force_update=False):
        if not self.trading_allowed.is_set():
            return False

        with self._lock:
            if not self.update_account_data(force=force_update):
                return False

            if not self.trading_allowed.is_set():
                return False

            free_margin = float(self.account_info_dict.get("margin_free", 0.0))
            risk_equity_value = self.equity - ((self.equity / 100.0) * self.trade_risk)
            result = free_margin >= risk_equity_value
            logger.debug(f"Проверка маржи для сделки: {result} (free_margin={free_margin})")
            return result

    def is_equity_satisfactory(self, force_update=False):
        with self._lock:
            self.update_account_data(force=force_update)
            return self.trading_allowed.is_set()

    def can_open_position(self, symbol: str) -> bool:
        """
        Комплексная проверка перед открытием сделки:
        1. Аварийный стоп по просадке и свободная маржа.
        2. Разрешение автоторговли в терминале MT5.
        3. Отсутствие открытой позиции по текущему тикеру (защита от склейки в Netting).
        4. Соблюдение общего лимита одновременно открытых позиций бота.
        """
        if not self.is_tradable(force_update=True):
            return False

        with self._lock:
            terminal_info = mt5.terminal_info()
            if terminal_info is None or not terminal_info.trade_allowed:
                logger.warning(f"{symbol}: Автоторговля в MT5 отключена или терминал недоступен.")
                return False

            # 1. Проверяем, нет ли уже открытой позиции по этому инструменту
            symbol_positions = mt5.positions_get(symbol=symbol)
            if symbol_positions is not None and len(symbol_positions) > 0:
                logger.info(f"{symbol}: Вход отменён — позиция по инструменту уже открыта.")
                return False

            # 2. Проверяем общий лимит открытых позиций по всему счёту (по magic_number бота)
            all_positions = mt5.positions_get()
            if all_positions is None:
                logger.warning(f"{symbol}: Не удалось запросить список позиций MT5: {mt5.last_error()}")
                return False

            bot_positions = [p for p in all_positions if p.magic == self.magic_number]
            if len(bot_positions) >= self.max_open_positions:
                logger.info(
                    f"{symbol}: Достигнут портфельный лимит позиций ({len(bot_positions)}/{self.max_open_positions})."
                )
                return False

            return True

    def calculate_lots(self, symbol: str, entry_price: float, stop_loss: float) -> float:
        """
        Рассчитывает прогрессивный объём (лоты) с учётом баланса, риска на стоп и спецификации контракта MT5.
        """
        with self._lock:
            if not self.update_account_data(force=True):
                return 0.0

            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"{symbol}: Не удалось получить спецификацию символа для расчёта лота.")
                return 0.0

            # Рабочий капитал (меньшее из баланса и эквити для защиты на просадках)
            available_capital = min(self.balance, self.equity)
            free_margin = float(self.account_info_dict.get("margin_free", 0.0))

            contract_size = float(symbol_info.trade_contract_size) if symbol_info.trade_contract_size > 0 else 1.0
            lot_cost = entry_price * contract_size

            if lot_cost <= 0 or available_capital < lot_cost:
                logger.warning(f"{symbol}: Недостаточно средств ({available_capital:.2f}) для 1 лота ({lot_cost:.2f}).")
                return 0.0

            # 1. Потолок лотов по выделенной доле депозита на один слот (например, 30% баланса)
            max_slot_capital = min(available_capital * self.max_deposit_share, free_margin * 0.90)
            max_affordable_lots = math.floor(max_slot_capital / lot_cost)

            # 2. Расчёт лотов от допустимого риска на сделку (например, 1.5% капитала)
            risk_lots = max_affordable_lots
            if stop_loss is not None and stop_loss > 0:
                risk_per_share = abs(entry_price - stop_loss)
                if risk_per_share > 0:
                    risk_rub = available_capital * (self.risk_per_trade_pct / 100.0)
                    risk_lots = math.floor(risk_rub / (risk_per_share * contract_size))

            raw_lots = min(max_affordable_lots, risk_lots)

            # 3. Выравнивание объёма по требованиям брокера (volume_min, volume_max, volume_step)
            vol_min = float(symbol_info.volume_min)
            vol_max = float(symbol_info.volume_max)
            vol_step = float(symbol_info.volume_step) if symbol_info.volume_step > 0 else 1.0

            if raw_lots < vol_min:
                if max_affordable_lots >= vol_min:
                    raw_lots = vol_min
                else:
                    logger.info(f"{symbol}: Объём ({raw_lots}) меньше минимального лота ({vol_min}).")
                    return 0.0

            normalized_lots = math.floor(raw_lots / vol_step) * vol_step
            normalized_lots = min(normalized_lots, vol_max)

            step_decimals = len(str(vol_step).split('.')) if '.' in str(vol_step) else 0
            final_lots = round(normalized_lots, step_decimals)

            logger.info(
                f"{symbol}: Лот рассчитан -> Капитал={available_capital:.0f}, "
                f"По доле={max_affordable_lots}, По риску={risk_lots} -> Итог={final_lots}"
            )
            return final_lots
