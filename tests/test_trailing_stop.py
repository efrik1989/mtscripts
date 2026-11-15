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


class TestTrailingStop:

    @pytest.fixture
    def bot(self):
        """Фикстура, имитирующая объект self (Trade)."""
        bot_instance = MagicMock()
        bot_instance.atr = 0.00100
        bot_instance.modify_position_sl = MagicMock()
        return bot_instance

    @pytest.fixture
    def mock_symbol_info(self):
        """Фикстура для свойств символа (EURUSD) с учётом trade_stops_level."""
        info = MagicMock()
        info.point = 0.00001
        info.digits = 5
        info.trade_stops_level = 10  # Минимальный отступ брокера 10 пунктов (0.00010)
        return info

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_symbol_info_none(self, mock_Mt5, mock_logger, bot):
        """Тест: Свойства символа не найдены -> ранний выход без падения."""
        mock_Mt5.symbol_info.return_value = None

        Trade.check_and_update_trailing(bot, "EURUSD", 300, 100)

        mock_Mt5.positions_get.assert_not_called()
        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_no_positions_or_none(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Нет открытых позиций или positions_get вернул None."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info

        # 1. Пустой список
        mock_Mt5.positions_get.return_value = []
        Trade.check_and_update_trailing(bot, "EURUSD", 300, 100)
        bot.modify_position_sl.assert_not_called()

        # 2. Возврат None при сбое связи (проверка защиты от TypeError)
        mock_Mt5.positions_get.return_value = None
        Trade.check_and_update_trailing(bot, "EURUSD", 300, 100)
        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_buy_success(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Успешный подтяг SL для BUY позиции."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_BUY = 0

        pos = MagicMock()
        pos.ticket = 1111
        pos.type = 0
        pos.price_open = 1.10000
        pos.sl = 0.0
        pos.tp = 1.12000
        mock_Mt5.positions_get.return_value = [pos]

        # Прибыль 150 пунктов (1.10150 - 1.10000) >= 100
        tick = MagicMock()
        tick.bid = 1.10150
        tick.ask = 1.10160
        mock_Mt5.symbol_info_tick.return_value = tick

        # Новый SL: 1.10150 - (30 * 0.00001) = 1.10120 (отступ 30 пп >= stops_level 10 пп)
        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)

        bot.modify_position_sl.assert_called_once_with(1111, 1.10120, 1.12000)

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_buy_breakeven_step(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Активация ступени безубытка (1.8 * ATR) до достижения основного трала."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_BUY = 0

        pos = MagicMock()
        pos.ticket = 1112
        pos.type = 0
        pos.price_open = 1.10000
        pos.sl = 1.09800
        pos.tp = 1.12000
        mock_Mt5.positions_get.return_value = [pos]

        # Прибыль 190 пунктов: больше порога безубытка (180 пп), но меньше основного трала (250 пп)
        tick = MagicMock()
        tick.bid = 1.10190
        tick.ask = 1.10200
        mock_Mt5.symbol_info_tick.return_value = tick

        # Буфер безубытка: 1.10000 * (0.0657 / 100) * 1.5 = 0.001084 -> 1.10108
        Trade.check_and_update_trailing(
            bot,
            "EURUSD",
            trailing_points=250,
            min_profit_points=250,
            breakeven_trigger_pts=180,
            commission_pct=0.0657
        )

        bot.modify_position_sl.assert_called_once_with(1112, 1.10108, 1.12000)

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

        tick = MagicMock()
        tick.bid = 1.10050
        tick.ask = 1.10060
        mock_Mt5.symbol_info_tick.return_value = tick

        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)

        bot.modify_position_sl.assert_not_called()

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_trailing_sell_success(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: Успешный подтяг SL для SELL позиции."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_SELL = 1

        pos = MagicMock()
        pos.ticket = 2222
        pos.type = 1
        pos.price_open = 1.10000
        pos.sl = 1.11000
        pos.tp = 1.08000
        mock_Mt5.positions_get.return_value = [pos]

        # Прибыль для SELL: 1.10000 - 1.09850 = 150 пунктов
        tick = MagicMock()
        tick.bid = 1.09840
        tick.ask = 1.09850
        mock_Mt5.symbol_info_tick.return_value = tick

        # Новый SL: 1.09850 + (30 * 0.00001) = 1.09880
        Trade.check_and_update_trailing(bot, "EURUSD", 30, 100)

        bot.modify_position_sl.assert_called_once_with(2222, 1.09880, 1.08000)

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_modify_position_sl_success(self, mock_Mt5, mock_logger, bot):
        """Тест вспомогательного метода modify_position_sl при успешном ответе MT5."""
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10009

        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_Mt5.order_send.return_value = mock_result

        Trade.modify_position_sl(bot, 12345, 1.10000, 1.12000)

        mock_Mt5.order_send.assert_called_once_with({
            "action": 1,
            "position": 12345,
            "sl": 1.10000,
            "tp": 1.12000
        })
        mock_logger.info.assert_any_call("#12345: SL успешно обновлён до 1.1 (TP=1.12 сохранён).")

    @patch('core.mt5.mt5_trade.logger')
    @patch('core.mt5.mt5_trade.Mt5')
    def test_change_take_profit_preserves_sl(self, mock_Mt5, mock_logger, bot, mock_symbol_info):
        """Тест: change_take_profit обновляет TP и НЕ затирает текущий SL."""
        mock_Mt5.symbol_info.return_value = mock_symbol_info
        mock_Mt5.POSITION_TYPE_BUY = 0
        mock_Mt5.TRADE_ACTION_SLTP = 1
        mock_Mt5.TRADE_RETCODE_DONE = 10009

        pos = MagicMock()
        pos.ticket = 3333
        pos.type = 0
        pos.sl = 1.09500  # Установленный стоп-лосс, который нельзя потерять
        pos.tp = 1.11000
        mock_Mt5.positions_get.return_value = [pos]

        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_Mt5.order_send.return_value = mock_result

        # Новый TP 1.11500 >= (1.11000 + 0.00100 ATR) -> должно обновиться
        Trade.change_take_profit(bot, "EURUSD", 1.11500)

        mock_Mt5.order_send.assert_called_once_with({
            "action": 1,
            "position": 3333,
            "symbol": "EURUSD",
            "sl": 1.09500,
            "tp": 1.11500,
            "magic": 7777,
            "comment": "dynamic TP, python",
        })
