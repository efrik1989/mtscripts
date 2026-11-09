import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Заглушка для глобальных переменных gv
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

# Имитируем базовый класс Mode, чтобы супер-вызовы super().... не падали
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
        def sl_tp_checker(self, *args, **kwargs): pass
        def signals_handler(self, *args, **kwargs): pass
    mode_module.Mode = FakeMode
    sys.modules['models.mode'] = mode_module

# Импортируем тестируемый класс и Order
# Замените 'core.modes.historic_mode' на ваш реальный путь импорта
from core.modes.historic_mode import Historic_mode
from models.order import Order


class TestHistoricMode:

    @pytest.fixture
    def setup_gv(self):
        """Фикстура для сброса глобальных флагов."""
        gv.global_args.buy_sell = False
        gv.global_args.dynamic_take_profit = False
        gv.global_args.trailing_stop = 0
        return gv.global_args

    @pytest.fixture
    def hm(self):
        """Фикстура для инициализации Historic_mode с базовыми заглушками."""
        fake_strategy = MagicMock()
        fake_strategy.take_profit = 1.1500
        
        hm_instance = Historic_mode(symbol="EURUSD", strategy=fake_strategy)
        hm_instance.order = None
        hm_instance.orders_count = 0
        hm_instance.profit_orders_count = 0
        hm_instance.profit = 0.0
        hm_instance.frame = MagicMock()
        hm_instance.is_order_open = False
        
        # Мокаем вспомогательные методы, унаследованные или внешние
        hm_instance.position_id_in_frame = MagicMock(return_value="mock_frame")
        hm_instance.close_position_by_sltp = MagicMock()
        
        return hm_instance

    @patch('core.modes.historic_mode.logger')
    @patch('core.modes.historic_mode.Order')
    def test_open_position_signal_checker_success(self, mock_Order_cls, mock_logger, hm):
        """Тест: Сигнал на открытие BUY создает фейковую историческую позицию."""
        # Arrange
        mock_order_instance = MagicMock(spec=Order)
        mock_Order_cls.return_value = mock_order_instance

        # Act
        hm.open_position_signal_checker("EURUSD", 1.1000, "Open_buy", 0.0040)

        # Assert
        mock_Order_cls.assert_called_once_with(1.1000, "EURUSD", hm.strategy, 0.0040, isBuy=True)
        mock_order_instance.open_fake_position.assert_called_once()
        assert hm.orders_count == 1
        assert hm.order == mock_order_instance
        hm.position_id_in_frame.assert_called_once()

    @patch('core.modes.historic_mode.logger')
    def test_close_position_signal_checker_success(self, mock_logger, hm):
        """Тест: Сигнал закрытия BUY успешно рассчитывает фейковый профит."""
        # Arrange
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
        
        mock_order.fake_buy_sell_close = MagicMock(return_value=15.0) # Профит +15 долларов
        hm.order = mock_order

        # Act
        hm.close_position_signal_checker("EURUSD", 1.1050, "NaN", "Close_buy")

        # Assert
        mock_order.fake_buy_sell_close.assert_called_once_with(1.1050)
        assert hm.profit == 15.0
        assert hm.profit_orders_count == 1
        assert hm.order is None  # Позиция обнулена

    @patch('core.modes.historic_mode.logger')
    def test_sl_tp_checker_closes_by_tp(self, mock_logger, hm):
        """Тест: Свеча пересекает уровень TP -> симуляция тиков закрывает позицию по ТP."""
        # Arrange
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
        mock_order.id = 123
        mock_order.take_profit = 1.1050
        mock_order.stop_loss = 1.0950
        mock_order.isBuy = True
        hm.order = mock_order

        # Имитируем High/Low свечи фрейма, заходящие за TP
        fake_bar = pd.Series({'low': 1.0980, 'high': 1.1060})
        
        # Симулируем тики внутри этой свечи. Второй тик касается нашего TP (1.1050)
        ticks_data = {'bid': [1.1000, 1.1055, 1.1040]}
        hm.get_price_from_ticks = MagicMock(return_value=ticks_data)

        # Act
        hm.sl_tp_checker("EURUSD", fake_bar, index=5)

        # Assert
        # Проверяем, что метод симуляции тиков закрыл позицию по цене, достигшей TP
        hm.close_position_by_sltp.assert_called_once_with("EURUSD", 1.1055)

    @patch('core.modes.historic_mode.logger')
    def test_trailing_stop_checker_updates_sl(self, mock_logger, hm, setup_gv):
        """Тест: Трейлинг-стоп на тиках обновляет фейковый SL ордера."""
        # Arrange
        setup_gv.trailing_stop = 30  # Включаем трал
        
        with patch.object(Order, '__init__', lambda self: None):
            mock_order = Order()
        mock_order.id = 999
        mock_order.stop_loss = 1.0900
        mock_order.fake_traling_stop = MagicMock()
        hm.order = mock_order

        # Симулируем тиковый поток для свечи
        ticks_data = {'bid': [1.1010, 1.1020]}
        hm.get_price_from_ticks = MagicMock(return_value=ticks_data)

        # Act
        hm.trailing_stop_checker(frame=None, index=5)

        # Assert
        # Метод fake_traling_stop должен вызваться для каждого тика
        assert mock_order.fake_traling_stop.call_count == 2
        mock_order.fake_traling_stop.assert_any_call(1.1010, 30)
        mock_order.fake_traling_stop.assert_any_call(1.1020, 30)

    def test_get_efficiency_zero_division(self, hm):
        """Тест: Защита от деления на ноль в расчете эффективности, если сделок не было."""
        hm.orders_count = 0
        hm.profit_orders_count = 0
        
        # Метод не должен падать, а ZeroDivisionError должен быть корректно перехвачен
        result = hm.get_efficiency()
        assert result is None

    def test_get_efficiency_success(self, hm):
        """Тест: Корректный расчет процента прибыльных сделок."""
        hm.orders_count = 4
        hm.profit_orders_count = 3  # 3 из 4 успешные = 75%
        
        assert hm.get_efficiency() == 75.0
