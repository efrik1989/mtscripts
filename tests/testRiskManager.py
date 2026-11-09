import pytest
from unittest.mock import MagicMock, patch
import time

# Заглушка для логгера
try:
    import core.global_vars as gv
    if gv.global_args is None:
        mock_args = MagicMock()
        mock_args.loglevel = "INFO"
        mock_args.logfile = "test.txt"
        gv.global_args = mock_args
except ImportError:
    pass

# Импортируем ваш RiskManager
# Замените 'core.risk' на реальный путь к модулю, где лежит RiskManager
from core.risk_manager import RiskManager 


class TestRiskManager:

    @pytest.fixture(autouse=True)
    def clean_singleton(self):
        """Фикстура очищает Singleton перед каждым тестом, обеспечивая их изоляцию."""
        RiskManager._instances = {}
        yield

    @pytest.fixture
    def manager(self):
        """Фикстура для создания свежего экземпляра RiskManager."""
        return RiskManager(trade_risk=10.0, lost_risk=5.0, cache_ttl=0.2)

    @patch('core.risk_manager.mt5')
    def test_singleton_pattern(self, mock_mt5):
        """Проверяем, что паттерн Singleton возвращает один и тот же объект."""
        rm1 = RiskManager(trade_risk=10.0)
        rm2 = RiskManager(trade_risk=20.0)
        
        assert rm1 is rm2
        # Параметры не должны перезаписываться при повторном вызове
        assert rm2.trade_risk == 10.0 

    @patch('core.risk_manager.logger')
    @patch('core.risk_manager.mt5')
    def test_ensure_mt5_connected_lost_and_failed(self, mock_mt5, mock_logger, manager):
        """Тест: Соединение с МТ5 разорвано и повторная инициализация провалилась."""
        mock_mt5.terminal_info.return_value = None
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = "No connection"
        
        result = manager._ensure_mt5_connected()
        
        assert result is False
        mock_logger.warning.assert_called_once_with("MT5 connection lost. Re-initializing...")
        mock_logger.error.assert_called_once_with("Initialize failed: No connection")

    @patch('core.risk_manager.mt5')
    @patch('core.risk_manager.time.time')
    def test_update_account_data_caching(self, mock_time, mock_mt5, manager):
        """Тест: Проверка работы кэширования по времени TTL."""
        # Настраиваем успешный ответ аккаунта
        mock_account = MagicMock()
        mock_account._asdict.return_value = {"equity": 1000.0}
        mock_mt5.account_info.return_value = mock_account
        mock_mt5.terminal_info.return_value = MagicMock()

        # 1-й вызов: время 100.0 (данные должны обновиться)
        mock_time.return_value = 100.0
        assert manager.update_account_data() is True
        assert mock_mt5.account_info.call_count == 1

        # 2-й вызов: время 100.1 (разница 0.1 < TTL 0.2 -> берем из кэша, копания в MT5 нет)
        mock_time.return_value = 100.1
        assert manager.update_account_data() is True
        assert mock_mt5.account_info.call_count == 1  # Счетчик вызовов не изменился

        # 3-й вызов: время 100.4 (разница 0.4 > TTL 0.2 -> кэш устарел, запрашиваем MT5)
        mock_time.return_value = 100.4
        assert manager.update_account_data() is True
        assert mock_mt5.account_info.call_count == 2  # Вызвался второй раз

    @patch('core.risk_manager.logger')
    @patch('core.risk_manager.mt5')
    def test_is_tradable_success(self, mock_mt5, mock_logger, manager):
        """Тест: Торговля разрешена, маржи хватает."""
        mock_mt5.terminal_info.return_value = MagicMock()
        
        # Задаем параметры аккаунта
        mock_account = MagicMock()
        # equity = 1000. Риск 10%. Значит, лимит свободной маржи: 1000 - (1000/100 * 10) = 900
        # Задаем margin_free = 950 (хватает с запасом)
        mock_account._asdict.return_value = {"equity": 1000.0, "margin_free": 950.0}
        mock_mt5.account_info.return_value = mock_account

        assert manager.is_tradable(force_update=True) is True
        mock_logger.info.assert_any_call("Возможно ли открытие сделки: True")

    @patch('core.risk_manager.logger')
    @patch('core.risk_manager.mt5')
    def test_is_tradable_insufficient_margin(self, mock_mt5, mock_logger, manager):
        """Тест: Свободной маржи меньше, чем требует риск-менеджмент."""
        mock_mt5.terminal_info.return_value = MagicMock()
        
        mock_account = MagicMock()
        # Лимит маржи: 900. А у нас на счету только 850
        mock_account._asdict.return_value = {"equity": 1000.0, "margin_free": 850.0}
        mock_mt5.account_info.return_value = mock_account

        assert manager.is_tradable(force_update=True) is False
        mock_logger.info.assert_any_call("Возможно ли открытие сделки: False")

    @patch('core.risk_manager.mt5')
    def test_is_tradable_blocked_by_emergency_event(self, mock_mt5, manager):
        """Тест: Если флаг trading_allowed сброшен, метод мгновенно возвращает False."""
        # Принудительно сбрасываем флаг разрешения торговли
        manager.trading_allowed.clear()
        
        # Метод должен мгновенно вернуть False, не опрашивая MT5
        assert manager.is_tradable() is False
        mock_mt5.account_info.assert_not_called()

    @patch('core.risk_manager.mt5')
    def test_is_equity_satisfactory(self, mock_mt5, manager):
        """Тест проверки состояния эквити."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_account = MagicMock()
        mock_account._asdict.return_value = {"equity": 1000.0}
        mock_mt5.account_info.return_value = mock_account

        assert manager.is_equity_satisfactory(force_update=True) is True

    @patch('core.risk_manager.logger')
    @patch('core.risk_manager.mt5')
    def test_emergency_stop_triggered(self, mock_mt5, mock_logger, manager):
        """Тест: Эквити падает ниже допустимого лимита просадки -> Торговля блокируется."""
        mock_mt5.terminal_info.return_value = MagicMock()
        
        # Шаг 1: Симулируем первый запуск. Баланс = 1000. Эквити = 1000.
        # Допустимый риск потерь (lost_risk) у нас 5%, значит лимит остановки = 950.
        mock_account_normal = MagicMock()
        mock_account_normal._asdict.return_value = {"balance": 1000.0, "equity": 1000.0}
        mock_mt5.account_info.return_value = mock_account_normal
        
        manager.update_account_data(force=True)
        assert manager.trading_allowed.is_set() is True  # Всё в порядке, торговля разрешена

        # Шаг 2: Симулируем просадку. Эквити падает до 940 (что ниже лимита 950)
        mock_account_crash = MagicMock()
        mock_account_crash._asdict.return_value = {"balance": 1000.0, "equity": 940.0}
        mock_mt5.account_info.return_value = mock_account_crash
        
        # Вызываем обновление данных
        manager.update_account_data(force=True)
        
        # ПРОВЕРКИ:
        # 1. Флаг разрешений должен автоматически сброситься в False
        assert manager.trading_allowed.is_set() is False  
        # 2. Должен вызваться критический лог аварийной остановки
        mock_logger.critical.assert_called_with("EMERGENCY STOP! Equity 940.0 < Limit 950.0 (Initial Balance: 1000.0)")
        # 3. Метод is_tradable теперь должен сразу возвращать False
        assert manager.is_tradable() is False

    @patch('core.risk_manager.mt5')
    def test_emergency_stop_recovery(self, mock_mt5, manager):
        """Тест: Баланс восстановился выше лимита -> Блокировка автоматически снимается."""
        mock_mt5.terminal_info.return_value = MagicMock()
        manager.initial_balance = 1000.0
        manager.lost_risk = 5.0  # Лимит 950
        
        # Сначала загоняем робота в блокировку (equity = 900)
        mock_account_bad = MagicMock()
        mock_account_bad._asdict.return_value = {"balance": 1000.0, "equity": 900.0}
        mock_mt5.account_info.return_value = mock_account_bad
        manager.update_account_data(force=True)
        assert manager.trading_allowed.is_set() is False

        # Теперь симулируем, что баланс восстановился (например, закрылись сетки или долили депо: equity = 960)
        mock_account_good = MagicMock()
        mock_account_good._asdict.return_value = {"balance": 1000.0, "equity": 960.0}
        mock_mt5.account_info.return_value = mock_account_good
        
        manager.update_account_data(force=True)
        
        # Проверяем, что блокировка успешно снялась
        assert manager.trading_allowed.is_set() is True
