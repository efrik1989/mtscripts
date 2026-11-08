from unittest.mock import MagicMock, patch
import pytest

# Заглушка для логгера приложений gv (уже проверенная)
try:
    import core.global_vars as gv
    if gv.global_args is None:
        mock_args = MagicMock()
        mock_args.loglevel = "INFO"
        mock_args.logfile = "test.txt"
        gv.global_args = mock_args
except ImportError:
    pass

from core.mt5.mt5_trade import Trade


class TestTrailingStop:

    @pytest.fixture
    def bot(self):
        """Фикстура, имитирующая объект self (Trade)."""
        bot_instance = MagicMock()
        # Замокаем внутренний метод modify_position_sl, чтобы проверять его вызовы
        bot_instance.modify_position_sl = MagicMock()
        return bot_instance

    @pytest.fixture
    def mock_symbol_info(self):
        """Фикстура для свойств символа (EURUSD)."""
        info = MagicMock()
        info.point = 0.00001
        info.digits = 5
        return info

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_symbol_info_none(self, mock_Mt5, mock_logger, bot):
        """Тест: Свойства символа не найдены -> ранний выход."""
        mock_Mt5.symbol_info.return_value = None
        
        Trade.check_and_update_trailing(bot, "EURUSD", 300, 100)
        
        mock_Mt5.positions_get.assert_not_called()
        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_no_positions(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Нет открытых позиций."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        # Имитируем пустой список, чтобы избежать len(None) ошибки
        mock_Mt5.positions_get.return_value = []
        
        Trade.check_and_update_trailing(bot, "EURUSD", 300, 100)
        
        mock_logger.info.assert_any_call("There are no open positions on EURUSD, positions: 0")
        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_buy_success(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Успешный подтяг SL для BUY позиции."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_BUY = 0  # Имитируем константу MT5
        
        # Создаем фейковую BUY позицию
        pos = MagicMock()
        pos.ticket = 1111
        pos.type = 0  # POSITION_TYPE_BUY
        pos.price_open = 1.10000
        pos.sl = 0.0  # Стоп-лосс не установлен
        pos.tp = 1.12000
        mock_Mt5.positions_get.return_value = [pos]
        
        # Имитируем текущие цены (прибыль: 1.10150 - 1.10000 = 150 пунктов)
        tick = MagicMock()
        tick.bid = 1.10150
        tick.ask = 1.10140
        mock_Mt5.symbol_info_tick.return_value = tick
        
        # Запуск метода: дистанция 30 пунктов, минимальный профит 100 пунктов
        # Прибыль 150 >= 100 -> Трал должен активироваться
        # Новый SL: 1.10150 - (30 * 0.00001) = 1.10120
        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)
        
        # Проверяем, что вызвалась модификация с правильным новым SL
        bot.modify_position_sl.assert_called_once_with(1111, 1.10120, 1.12000)

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_buy_profit_too_low(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Прибыль BUY позиции слишком мала для активации трейлинга."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_BUY = 0
        
        pos = MagicMock()
        pos.type = 0
        pos.price_open = 1.10000
        pos.sl = 0.0
        mock_Mt5.positions_get.return_value = [pos]
        
        # Прибыль всего 50 пунктов (1.10050 - 1.10000)
        tick = MagicMock()
        tick.bid = 1.10050
        mock_Mt5.symbol_info_tick.return_value = tick
        
        # Требуется минимум 100 пунктов прибыли
        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)
        
        # Модификация не должна быть вызвана
        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_sell_success(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Успешный подтяг SL для SELL позиции."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_SELL = 1
        
        # Создаем фейковую SELL позицию
        pos = MagicMock()
        pos.ticket = 2222
        pos.type = 1  # POSITION_TYPE_SELL
        pos.price_open = 1.10000
        pos.sl = 1.11000  # Старый SL
        pos.tp = 1.08000
        mock_Mt5.positions_get.return_value = [pos]
        
        # Прибыль для SELL: 1.10000 - 1.09850 (current_ask) = 150 пунктов
        tick = MagicMock()
        tick.ask = 1.09850
        mock_Mt5.symbol_info_tick.return_value = tick
        
        # Новый SL для SELL: 1.09850 + (30 * 0.00001) = 1.09880
        # 1.09880 < 1.11000 (старого SL) -> Трал должен сдвинуть SL вниз
        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)
        
        bot.modify_position_sl.assert_called_once_with(2222, 1.09880, 1.08000)

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_modify_position_sl_success(self, mock_Mt5, mock_logger, bot):
        """Тест вспомогательного метода modify_position_sl при успешном ответе MT5."""
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10001
        
        mock_result = MagicMock()
        mock_result.retcode = 10001
        mock_Mt5.order_send.return_value = mock_result
        
        # Вызываем реальный метод через класс, передавая базовый bot
        Trade.modify_position_sl(bot, 12345, 1.10000, 1.12000)
        
        # Проверяем структуру запроса в order_send
        mock_Mt5.order_send.assert_called_once_with({
            "action": 1,
            "position": 12345,
            "sl": 1.10000,
            "tp": 1.12000
        })
        mock_logger.info.assert_any_call("Трейлинг-стоп активирован. Позиция #12345 новый SL: 1.1")