import threading
import time
import MetaTrader5 as mt5
import logging

logger = logging.getLogger(__name__)

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
    def __init__(self, trade_risk=0.0, lost_risk=0.0, cache_ttl=0.2):
        if not hasattr(self, "_initialized"):
            self.trade_risk = float(trade_risk)
            self.lost_risk = float(lost_risk)
            
            self.account_info_dict = {}
            self.equity = 0.0
            
            self._last_update_time = 0
            self._cache_ttl = cache_ttl
            
            self._lock = threading.RLock()
            
            # Глобальный флаг остановки: True - торговля разрешена, False - запрещена
            self.trading_allowed = threading.Event()
            self.trading_allowed.set() # По умолчанию разрешаем
            
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
                    self._last_update_time = now
                    
                    # АВТО-ПРОВЕРКА: Если данные обновились, сразу проверяем критический риск
                    if not self._check_emergency_stop():
                        self.trading_allowed.clear() # Блокируем всё
                    else:
                        self.trading_allowed.set() # Разблокируем (если баланс восстановился)
                        
                    return True
                return False
            return True

    def _check_emergency_stop(self):
        """Внутренняя проверка критического порога equity."""
        limit = self.equity - ((self.equity / 100) * self.lost_risk)
        if self.equity < limit:
            logger.critical(f"EMERGENCY STOP! Equity {self.equity} < Limit {limit}")
            return False
        return True

    def is_tradable(self, force_update=False):
        # 1. Мгновенная проверка флага остановки (без блокировок)
        if not self.trading_allowed.is_set():
            return False

        with self._lock:
            if not self.update_account_data(force=force_update):
                return False
            
            # 2. Повторная проверка после обновления данных
            if not self.trading_allowed.is_set():
                return False

            free_margin = float(self.account_info_dict.get("margin_free", 0.0))
            risk_equity_value = self.equity - ((self.equity / 100) * self.trade_risk)
            result = free_margin >= risk_equity_value
            logger.info(f"Возможно ли открытие сделки: {result}")
            return result

    def is_equity_satisfactory(self, force_update=False):
        with self._lock:
            self.update_account_data(force=force_update)
            return self.trading_allowed.is_set()