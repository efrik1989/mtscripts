import pytest
from unittest.mock import MagicMock, patch

# Заглушка для логгера приложений gv
try:
    import core.global_vars as gv
    if gv.global_args is None:
        mock_args = MagicMock()
        mock_args.loglevel = "INFO"
        mock_args.logfile = "test.txt"
        mock_args.buy_sell = False
        mock_args.dynamic_take_profit = False
        mock_args.trailing_stop = 0
        gv.global_args = mock_args
except ImportError:
    pass

# Имитируем базовый класс Mode
import sys
from types import ModuleType

if 'models.mode' not in sys.modules:
    mode_module = ModuleType('models.mode')
    class FakeMode:
        def __init__(self, symbol, strategy):
            self.symbol = symbol
            self.strategy = strategy
        def open_position_signal_checker(self, *args, **kwargs): pass
        def close_position_signal_checker(self, *args, **kwargs): pass
        def dynamic_tp_checker(self, *args, **kwargs): pass
        def trailing_stop_checker(self, *args, **kwargs): pass
        def signals_handler(self, *args, **kwargs): pass
    mode_module.Mode = FakeMode
    sys.modules['models.mode'] = mode_module

from core.modes.trade_mode import Trade_mode 
from models.order import Order


class TestTradeMode:

    @pytest.fixture
    def setup_gv(self):
        """Фикстура для сброса глобальных флагов."""
        gv.global_args.buy_sell = False
        gv.global_args.dynamic_take_profit = False
        gv.global_args.trailing_stop = 0
        return gv.global_args

    @pytest.fixture
    def tm(self):
        """Фикстура для создания объекта Trade_mode."""
        fake_strategy = MagicMock()
        fake_strategy.take_profit = 1.1500
        
        trade_mode_instance = Trade_mode(symbol="EURUSD", strategy=fake_strategy)
        trade_mode_instance.order = None
        trade_mode_instance.risk_manager = MagicMock()
        trade_mode_instance.locker = MagicMock()
        trade_mode_instance.locker.is_bar_locked = False
        trade_mode_instance.get_current_price = MagicMock(return_value=1.1000)
        
        return trade_mode_instance

    @patch('core.modes.trade_mode.logger')
    @patch('core.modes.trade_mode.Order')
    def test_open_position_buy_success(self, mock_Order_cls, mock_logger, tm):
        """Тест: Получен сигнал на покупку, риск-менеджер разрешил -> позиция открывается."""
        tm.risk_manager.is_tradable.return_value = True
        
        mock_order_instance = MagicMock(spec=Order)  
        mock_order_instance.position_check.return_value = False  
        mock_Order_cls.return_value = mock_order_instance

        tm.open_position_signal_checker("EURUSD", 1.1000, "Open_buy", 0.0010)

        mock_Order_cls.assert_called_once_with(1.1000, "EURUSD", tm.strategy, 0.0010, isBuy=True)
        mock_order_instance.position_check.assert_called_once()
        mock_order_instance.open_position.assert_called_once()
        assert tm.order == mock_order_instance

    @patch('core.modes.trade_mode.logger')
    @patch('core.modes.trade_mode.Order')
    def test_open_position_risk_manager_blocks(self, mock_Order_cls, mock_logger, tm):
        """Тест: Сигнал есть, но Риск-Менеджер ЗАПРЕТИЛ торговлю -> ордер не создается."""
        tm.risk_manager.is_tradable.return_value = False

        tm.open_position_signal_checker("EURUSD", 1.1000, "Open_buy", 0.0010)

        mock_Order_cls.assert_not_called()
        assert tm.order is None

    @patch('core.modes.trade_mode.logger')
    def test_close_position_buy_success(self, mock_logger, tm):
        """Тест: Получен сигнал на закрытие BUY -> позиция закрывается, объект обнуляется."""
        # ИСПРАВЛЕНО: Отключаем родной __init__ у Order, чтобы создать чистый инстанс класса Order
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
            
        mock_order.close_position = MagicMock() 
        tm.order = mock_order  

        # Act
        tm.close_position_signal_checker("EURUSD", "Close_buy")

        # Assert
        mock_order.close_position.assert_called_once()
        assert tm.order is None  

    @patch('core.modes.trade_mode.logger')
    def test_dynamic_tp_disabled_by_config(self, mock_logger, tm, setup_gv):
        """Тест: Сигнал на смену TP есть, но в gv флаг отключен -> ничего не происходит."""
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
            
        mock_order.set_new_take_profit = MagicMock()
        tm.order = mock_order

        # Act
        tm.dynamic_tp_checker(1.1200)

        # Assert
        mock_order.set_new_take_profit.assert_not_called()

    @patch('core.modes.trade_mode.logger')
    def test_dynamic_tp_enabled_success(self, mock_logger, tm, setup_gv):
        """Тест: Динамический TP включен -> ордер получает новое значение."""
        # Arrange
        setup_gv.dynamic_take_profit = True  
        
        # ИСПРАВЛЕНО: Создаем чистый объект Order без вызова тяжелого __init__
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
            
        mock_order.id = 777
        mock_order.set_new_take_profit = MagicMock()
        tm.order = mock_order

        # Act
        tm.dynamic_tp_checker(1.1200)

        # Assert
        mock_order.set_new_take_profit.assert_called_once_with(1.1200)
        mock_logger.info.assert_any_call("Order to change TP: 777, значение:  1.12")

    @patch('core.modes.trade_mode.mt5_a')
    def test_check_opened_positions_already_closed_on_server(self, mock_mt5_a, tm):
        """Тест: На сервере позиция закрылась -> очищаем self.order."""
        mock_order = MagicMock()
        tm.order = mock_order
        mock_mt5_a.get_position_info.return_value = None

        tm.check_opened_positions("EURUSD")

        assert tm.order is None  

    @patch('core.modes.trade_mode.logger')
    def test_signals_handler_bar_is_locked(self, mock_logger, tm):
        """Тест: Если бар заблокирован, обработчик сигналов ничего не делает."""
        tm.locker.is_bar_locked = True
        tm.trailing_stop_checker = MagicMock()

        tm.signals_handler("EURUSD", 1.1000, "Open_buy", 0.0010, "None")

        tm.trailing_stop_checker.assert_not_called()  
