import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys

# Настройка глобальных переменных gv перед импортом
try:
    import core.global_vars as gv
    if gv.global_args is None:
        mock_args = MagicMock()
        mock_args.loglevel = "INFO"
        mock_args.logfile = "test.txt"
        mock_args.logs_directory = "C:\\logs"
        mock_args.monney_mode = "sim"
        mock_args.strategy = "AtrStrategy"
        gv.global_args = mock_args
except ImportError:
    pass

# Импортируем тестируемый класс
# Замените 'models.order' на ваш реальный путь, если он отличается
from models.order import Order


class TestOrder:

    @pytest.fixture
    def setup_gv(self):
        """Фикстура для сброса конфигураций gv."""
        gv.global_args.logs_directory = "C:\\logs"
        gv.global_args.monney_mode = "sim"
        gv.global_args.strategy = "AtrStrategy"
        return gv.global_args

    @pytest.fixture
    @patch('models.order.trade.Trade')  # Мокаем Trade, чтобы не вызывать его конструктор
    def order_buy(self, mock_trade_cls, setup_gv):
        """Фикстура для создания BUY ордера."""
        with patch('builtins.open', mock_open()):
            ord_instance = Order(open_price=1.1000, symbol="EURUSD", strategy=MagicMock(), atr_value=0.0020, isBuy=True)
        return ord_instance

    @pytest.fixture
    @patch('models.order.trade.Trade')
    def order_sell(self, mock_trade_cls, setup_gv):
        """Фикстура для создания SELL ордера."""
        with patch('builtins.open', mock_open()):
            ord_instance = Order(open_price=1.1000, symbol="EURUSD", strategy=MagicMock(), atr_value=0.0020, isBuy=False)
        return ord_instance

    def test_order_initialization(self, order_buy):
        """Тест корректности инициализации параметров ордера."""
        assert order_buy.open_price == 1.1000
        assert order_buy.symbol == "EURUSD"
        assert order_buy.atr == 0.0020
        assert order_buy.stop_atr == pytest.approx(0.0050)
        assert order_buy.take_atr == pytest.approx(0.0100)
        assert order_buy.isBuy is True
        assert order_buy.direction == "buy"

    def test_fake_buy_levels(self, order_buy):
        """Тест расчета уровней SL/TP для симуляции BUY ордера."""
        order_buy.fake_buy()
        assert order_buy.stop_loss == pytest.approx(1.0950)
        assert order_buy.take_profit == pytest.approx(1.1100)

    def test_fake_sell_levels(self, order_sell):
        """Тест расчета уровней SL/TP для симуляции SELL ордера."""
        order_sell.fake_sell()
        assert order_sell.stop_loss == pytest.approx(1.1050)
        assert order_sell.take_profit == pytest.approx(1.0900)

    @patch('models.order.logger')
    def test_open_fake_position_file_write(self, mock_logger, order_buy):
        """Тест симуляции открытия позиции: проверка дозаписи в файл."""
        m_open = mock_open()
        with patch('builtins.open', m_open):
            order_buy.open_fake_position()

        m_open.assert_called_once_with(order_buy.sim_log_path, "a")
        handle = m_open()
        handle.write.assert_called_once()

    @patch('models.order.logger')
    def test_fake_buy_close_profit(self, mock_logger, order_buy):
        """Тест симуляции закрытия BUY ордера и расчета профита."""
        m_open = mock_open()
        with patch('builtins.open', m_open):
            profit = order_buy.fake_buy_sell_close(1.1020)

        assert profit == pytest.approx(0.0020)
        handle = m_open()
        assert handle.write.call_count == 2

    @patch('models.order.logger')
    def test_fake_sell_close_profit(self, mock_logger, order_sell):
        """Тест симуляции закрытия SELL ордера и расчета профита."""
        m_open = mock_open()
        with patch('builtins.open', m_open):
            profit = order_sell.fake_buy_sell_close(1.0950)

        assert profit == pytest.approx(0.0050)

    @patch('models.order.mt5')
    def test_fake_trailing_stop_buy_triggered(self, mock_mt5, order_buy):
        """Тест симуляции Трейлинг-Стопа для BUY (SL подтягивается)."""
        mock_symbol_info = MagicMock()
        mock_symbol_info.point = 0.00001
        mock_mt5.symbol_info.return_value = mock_symbol_info

        order_buy.stop_loss = 1.0950
        
        m_open = mock_open()
        with patch('builtins.open', m_open):
            order_buy.fake_traling_stop(current_price=1.1200, indent="atr")

        assert order_buy.stop_loss == pytest.approx(1.1150)

    def test_fake_set_new_take_profit_valid(self, order_buy):
        """Тест: Передача корректного значения в fake_set_new_take_profit изменяет TP."""
        order_buy.take_profit = 1.1100
        order_buy.fake_set_new_take_profit(1.1150)
        assert order_buy.take_profit == 1.1150

    @pytest.mark.parametrize("invalid_tp", [None, ""])
    def test_fake_set_new_take_profit_invalid(self, order_buy, invalid_tp):
        """Тест: Передача None или пустой строки НЕ изменяет TP (проверка исправленного AND)."""
        order_buy.take_profit = 1.1100
        order_buy.fake_set_new_take_profit(invalid_tp)
        assert order_buy.take_profit == 1.1100  # Значение осталось прежним

    @patch('models.order.trade')
    def test_set_new_take_profit_valid(self, mock_trade_mod, order_buy):
        """Тест: Передача корректного значения вызывает изменение реального TP через trade."""
        order_buy.set_new_take_profit(1.1150)
        mock_trade_mod.change_take_profit.assert_called_once_with("EURUSD", 1.1150)

    @pytest.mark.parametrize("invalid_tp", [None, ""])
    @patch('models.order.trade')
    def test_set_new_take_profit_invalid(self, mock_trade_mod, order_buy, invalid_tp):
        """Тест: Передача невалидного TP не вызывает метод модуля trade."""
        order_buy.set_new_take_profit(invalid_tp)
        mock_trade_mod.change_take_profit.assert_not_called()

    @patch('models.order.mt5_a')
    def test_open_position_success(self, mock_mt5_a, order_buy):
        """Тест открытия реальной позиции в терминале MT5."""
        # Настраиваем фейковый вызов trade_obj
        order_buy.trade_obj = MagicMock()
        
        # Настраиваем ответ mt5_a.get_position_info (возвращает тикет позиции)
        mock_pos_info = MagicMock()
        mock_pos_info.ticket = 987654
        mock_mt5_a.get_position_info.return_value = mock_pos_info

        # Act
        order_buy.open_position()

        # Assert
        order_buy.trade_obj.position_open.assert_called_once_with(True, False)
        assert order_buy.id == 987654

    def test_close_position_success(self, order_buy):
        """Тест отправки команды на закрытие реальной позиции."""
        order_buy.trade_obj = MagicMock()
        
        order_buy.close_position()
        
        order_buy.trade_obj.position_close.assert_called_once()
