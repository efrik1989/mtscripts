from unittest.mock import MagicMock, patch
import pytest

# Заглушка для логгера приложений gv
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


class TestChangeTakeProfit:

    @pytest.fixture
    def bot(self):
        """Фикстура, имитирующая объект self."""
        bot_instance = MagicMock()
        bot_instance.atr = 0.0010
        bot_instance.symbol = "EURUSD"
        bot_instance.take_profit = 0.0
        bot_instance.isBuy = True
        return bot_instance

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_no_open_positions(self, mock_Mt5, mock_logger, bot):
        """Тест: открытых позиций нет (None) -> ранний return."""
        mock_Mt5.positions_get.return_value = None
        
        # Act
        Trade.change_take_profit(bot, "EURUSD", 1.1500)
        
        # Assert
        # Теперь благодаря вашей правке функция безопасно логирует positions: 0 при None
        mock_logger.info.assert_any_call("There are no open positions on EURUSD, positions: 0")
        mock_Mt5.order_send.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')  
    @patch('core.mt5.mt5_trade.Mt5')  
    def test_change_tp_buy_success(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Успешное изменение TP для BUY с отправкой ордера."""
        # Arrange
        bot.isBuy = True
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_position.ticket = 123456
        mock_Mt5.positions_get.return_value = [mock_position]
        
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10001
        
        mock_result = MagicMock()
        mock_result.retcode = 10001  
        mock_result._asdict.return_value = {'tp': 1.112}  
        mock_mt5.order_send.return_value = mock_result
        
        # Act
        Trade.change_take_profit(bot, "EURUSD", 1.1120)

        # Assert
        assert bot.take_profit == 1.1120
        mock_mt5.order_send.assert_called_once()
        mock_logger.info.assert_any_call("Value of Take Profit is changed. TP = 1.112")

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_change_tp_buy_condition_not_met(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Условие изменения TP для BUY не выполнено -> ордер НЕ отправляется."""
        # Arrange
        bot.isBuy = True
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_position.ticket = 123456
        mock_Mt5.positions_get.return_value = [mock_position]
        
        # Act
        # 1.1005 < 1.1000 + 0.0010 -> условие не сработает
        Trade.change_take_profit(bot, "EURUSD", 1.1005)

        # Assert
        assert bot.take_profit == 1.1000  # Значение не изменилось
        mock_mt5.order_send.assert_not_called()  # ИСПРАВЛЕНО: запрос не должен отправляться!
        
        # Проверяем появление лога из ветки else
        mock_logger.info.assert_any_call(
            "Value of Take Profit is not changed. No need to change. TP = 1.1, new TP value = 1.1005"
        )

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_change_tp_buy_new_tp_lower_than_current(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Новый TP меньше текущего для BUY -> ордер НЕ отправляется."""
        # Arrange
        bot.isBuy = True
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_position.ticket = 123456
        mock_Mt5.positions_get.return_value = [mock_position]
        
        # Act
        # Передаем новый TP = 1.0900 (что гораздо меньше текущего 1.1000)
        Trade.change_take_profit(bot, "EURUSD", 1.0900)

        # Assert
        assert bot.take_profit == 1.1000  
        mock_mt5.order_send.assert_not_called()  # ИСПРАВЛЕНО: запрос заблокирован флагом
        mock_logger.info.assert_any_call(
            "Value of Take Profit is not changed. No need to change. TP = 1.1, new TP value = 1.09"
        )

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_change_tp_sell_success(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Успешное изменение TP для SELL с отправкой ордера."""
        # Arrange
        bot.isBuy = False  
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_position.ticket = 654321
        mock_Mt5.positions_get.return_value = [mock_position]
        
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10001
        
        mock_result = MagicMock()
        mock_result.retcode = 10001
        mock_result._asdict.return_value = {'tp': 1.09}
        mock_mt5.order_send.return_value = mock_result
        
        # Act
        # Для SELL: (1.1000 + 0.0010) = 1.1010 >= 1.0900 -> Условие выполнено!
        Trade.change_take_profit(bot, "EURUSD", 1.0900)

        # Assert
        assert bot.take_profit == 1.0900
        mock_mt5.order_send.assert_called_once()
        mock_logger.info.assert_any_call("Value of Take Profit is changed. TP = 1.09")

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_change_tp_sell_condition_not_met(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Условие изменения TP для SELL не выполнено -> ордер НЕ отправляется."""
        # Arrange
        bot.isBuy = False
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_position.ticket = 654321
        mock_Mt5.positions_get.return_value = [mock_position]
        
        # Act
        # Для SELL: 1.1010 >= 1.1500 -> даст False
        Trade.change_take_profit(bot, "EURUSD", 1.1500)

        # Assert
        assert bot.take_profit == 1.1000  
        mock_mt5.order_send.assert_not_called()  # ИСПРАВЛЕНО: запрос не отправляется
        mock_logger.info.assert_any_call(
            "Value of Take Profit is not changed. No need to change. TP = 1.1, new TP value = 1.15"
        )

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.mt5')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_order_send_failed(self, mock_Mt5, mock_mt5, mock_logger, bot):
        """Тест: Условия выполнены, но сервер MetaTrader вернул ошибку выполнения ордера."""
        # Arrange
        bot.isBuy = True
        bot.atr = 0.0010
        
        mock_position = MagicMock()
        mock_position.tp = 1.1000
        mock_Mt5.positions_get.return_value = [mock_position]
        
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10001  
        
        mock_result = MagicMock()
        mock_result.retcode = 10014  # Код ошибки
        mock_result._asdict.return_value = {'retcode': 10014, 'comment': 'Invalid stops'}
        mock_mt5.order_send.return_value = mock_result
        
        # Act
        Trade.change_take_profit(bot, "EURUSD", 1.1120)

        # Assert
        mock_mt5.order_send.assert_called_once()
        mock_logger.error.assert_any_call("4. order_send failed, retcode=10014")

