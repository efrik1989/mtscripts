import sys
from unittest.mock import MagicMock, patch

# 1. Заглушка для глобальных переменных ДО импорта основных модулей.
# Это предотвращает ошибку AttributeError: 'NoneType' object has no attribute 'loglevel'
mock_global_args = MagicMock()
mock_global_args.loglevel = "INFO"
mock_global_args.logfile = "test.txt"
mock_global_args.range = 100
mock_global_args.timeframe = 'M1'
mock_global_args.monney_manager = MagicMock()
mock_global_args.lost_risk = 0.02
mock_global_args.logs_directory = '/tmp'
mock_global_args.strategy = 'test_strategy'

class MockGlobalVars:
    global_args = mock_global_args

# Внедряем заглушку в sys.modules, чтобы все импортируемые модули видели её
sys.modules['core.global_vars'] = MockGlobalVars


# 2. Теперь безопасно импортируем фреймворки и тестируемый код
import pytest
import pandas as pd
import numpy as np

from models.mode import Mode
from models.order import Order
from models.strategy import Strategy
from core.trade_locker import Locker


# 3. Конкретный класс-наследник для тестирования абстрактного класса Mode
class DummyMode(Mode):
    def close_position_signal_checker(self): pass
    def sl_tp_checker(self): pass
    def trailing_stop_checker(self): pass
    def dynamic_tp_checker(self): pass
    def signals_handler(self, *args, **kwargs): pass
    def open_position_signal_checker(self): pass


@pytest.fixture
def mock_dependencies():
    """Фикстура для изоляции внешних вызовов MetaTrader5 и логгера во время тестов."""
    with patch('models.mode.mt5_a') as mock_mt5, \
         patch('models.mode.tick') as mock_tick, \
         patch('models.mode.risk_m') as mock_risk, \
         patch('models.mode.logger') as mock_logger:
        
        # Исправленный вариант инициализации DataFrame (исправлена синтаксическая ошибка)
        init_frame = pd.DataFrame({
            'time': [1700000000, 1700000001], 
            'signal': ['none', 'none'], 
            'ATR': [1.5, 1.5]
        })
        mock_mt5.get_rates_frame.return_value = init_frame
        mock_mt5.check_order.return_value = False
        
        yield {
            'mt5': mock_mt5,
            'risk': mock_risk,
            'logger': mock_logger
        }


@pytest.fixture
def mock_strategy():
    """Фикстура для заглушки объекта стратегии."""
    return MagicMock(spec=Strategy)


# --- Сами Юнит-Тесты ---

def test_mode_initialization(mock_dependencies, mock_strategy):
    """Проверяем корректность инициализации полей класса Mode."""
    with patch.object(DummyMode, 'lets_trade') as mock_lets_trade:
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        assert mode_instance.symbol == "EURUSD"
        assert isinstance(mode_instance.locker, Locker)
        assert mode_instance.profit == 0
        assert mode_instance.is_order_open is False
        mock_lets_trade.assert_called_once_with("EURUSD")


@pytest.mark.parametrize("input_len, expected_len", [
    (5000, 5000),
    (10001, 10000),
    (15000, 10000)
])
def test_check_frame_len(mock_dependencies, mock_strategy, input_len, expected_len):
    """Проверяем лимитер размера DataFrame (check_frame_len)."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        df = pd.DataFrame({'data': range(input_len)})
        result_df = mode_instance.check_frame_len(df)
        
        assert len(result_df) == expected_len


def test_is_need_update_lst_bar_true(mock_dependencies, mock_strategy):
    """Фрейм должен обновиться, если время последнего бара в MT5 больше, чем во фрейме."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        frame = pd.DataFrame({'time': [100]})
        last_bar_frame = pd.DataFrame({'time': [200]}) 
        
        assert mode_instance.is_need_update_lst_bar("EURUSD", frame, last_bar_frame) is True


def test_is_need_update_lst_bar_false(mock_dependencies, mock_strategy):
    """Фрейм НЕ должен обновиться, если время нового бара не опережает текущее."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        frame = pd.DataFrame({'time': [200]})
        last_bar_frame = pd.DataFrame({'time': [200]}) 
        
        assert mode_instance.is_need_update_lst_bar("EURUSD", frame, last_bar_frame) is False


def test_get_last_column_value_success(mock_dependencies, mock_strategy):
    """Успешное получение последнего значения из колонки."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        frame = pd.DataFrame({'signal': ['buy', 'sell']})
        assert mode_instance.get_last_column_value(frame, 'signal') == 'sell'


def test_get_last_column_value_key_error(mock_dependencies, mock_strategy):
    """Возврат None и запись предупреждения в лог, если колонки не существует."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        frame = pd.DataFrame({'other_column': [1, 2]})
        assert mode_instance.get_last_column_value(frame, 'signal') is None
        mock_dependencies['logger'].warning.assert_called_once()


def test_position_id_in_frame(mock_dependencies, mock_strategy):
    """Проверка записи ID ордера в конкретный индекс датафрейма."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        frame = pd.DataFrame({'order_id': [None, None, None]})
        mock_order = MagicMock(spec=Order)
        mock_order.id = 777
        
        updated_frame = mode_instance.position_id_in_frame(mock_order, frame, index=1)
        assert updated_frame.loc[1, 'order_id'] == 777


def test_close_position_by_sltp(mock_dependencies, mock_strategy):
    """Проверка закрытия позиции по SLTP и обновления профита."""
    with patch.object(DummyMode, 'lets_trade'):
        mode_instance = DummyMode(symbol="EURUSD", strategy=mock_strategy)
        
        mock_order = MagicMock(spec=Order)
        mock_order.fake_buy_sell_close.return_value = 150.0  
        mode_instance.order = mock_order
        mode_instance.profit = 50.0
        
        mode_instance.close_position_by_sltp("EURUSD", current_price=1.1200)
        
        assert mode_instance.profit == 200.0
        assert mode_instance.order is None
        mock_order.fake_buy_sell_close.assert_called_once_with(1.1200)


@patch('models.mode.time.sleep', return_value=None)  
def test_lets_trade_continues_on_risk_block(mock_sleep, mock_dependencies, mock_strategy):
    """Проверка того, что цикл lets_trade уходит на со следующую итерацию, если торговля заблокирована."""
    with patch.object(DummyMode, '__init__', return_value=None):
        mode_instance = DummyMode()
        mode_instance.symbol = "EURUSD"
        
        mock_rm = MagicMock()
        mock_rm.trading_allowed.is_set.return_value = False
        mode_instance.risk_manager = mock_rm
        
        # Искусственно ломаем бесконечный цикл на 3-й итерации
        mock_rm.trading_allowed.is_set.side_effect = [False, False, RuntimeError("Break loop")]
        
        with pytest.raises(RuntimeError, match="Break loop"):
            mode_instance.lets_trade("EURUSD")
            
        # Логгер должен зафиксировать критическую ошибку ровно 2 раза перед выходом из цикла
        assert mock_dependencies['logger'].critical.call_count == 2
