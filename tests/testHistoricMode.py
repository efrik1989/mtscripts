import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys
from types import ModuleType

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

if 'models.mode' not in sys.modules:
    mode_module = ModuleType('models.mode')
    class FakeMode:
        def __init__(self, symbol, strategy):
            self.symbol = symbol
            self.strategy = strategy
    mode_module.Mode = FakeMode
    sys.modules['models.mode'] = mode_module

from core.modes.historic_mode import Historic_mode


class TestHistoricModeBacktrader:

    @pytest.fixture
    def setup_gv(self):
        gv.global_args.buy_sell = False
        gv.global_args.dynamic_take_profit = False
        gv.global_args.trailing_stop = 0
        return gv.global_args

    @pytest.fixture
    def hm(self):
        fake_strategy = MagicMock()
        fake_strategy.stop_loss = 1.0950
        fake_strategy.take_profit = 1.1050
        
        hm_instance = Historic_mode(symbol="EURUSD", strategy=fake_strategy)
        hm_instance.start_cash = 10000.0
        hm_instance.cerebro.broker.setcash(hm_instance.start_cash)
        hm_instance.cerebro.broker.setcommission(commission=0.0)
        return hm_instance

    def create_mock_frame(self, rows_data):
        default_columns = {
            'open': 1.1000, 'high': 1.1000, 'low': 1.1000, 'close': 1.1000, 'volume': 100,
            'signal': 'NaN', 'close_signal': 'NaN', 
            'BBM_16_2.0_2.0': 1.0950, 'BBU_16_2.0_2.0': 1.1050
        }
        records = []
        for row in rows_data:
            base = default_columns.copy()
            base.update(row)
            records.append(base)
            
        df = pd.DataFrame(records)
        df.index = pd.date_range(start="2026-11-10 10:00:00", periods=len(df), freq="min")
        return df

    @patch('core.modes.historic_mode.logger')
    def test_open_position_signal_checker_via_backtrader(self, mock_logger, hm):
        hm.frame = self.create_mock_frame([
            {'close': 1.1000, 'signal': 'Open_buy'},
            {'close': 1.1010}
        ])
        hm.lets_trade("EURUSD")
        assert hm.orders_count == 1
        assert hm.profit > 0

    @patch('core.modes.historic_mode.logger')
    def test_close_position_by_take_profit(self, mock_logger, hm):
        hm.frame = self.create_mock_frame([
            {'open': 1.1000, 'high': 1.1000, 'low': 1.1000, 'close': 1.1000, 'signal': 'Open_buy'},
            {'open': 1.1000, 'high': 1.1060, 'low': 1.1000, 'close': 1.1000}
        ])
        hm.strategy.stop_loss = 1.0950
        hm.strategy.take_profit = 1.1050

        hm.lets_trade("EURUSD")
        assert hm.orders_count == 1
        assert hm.profit_orders_count == 1
        assert hm.get_efficiency() == 100.0

    @patch('core.modes.historic_mode.logger')
    def test_trailing_stop_activation(self, mock_logger, hm, setup_gv):
        setup_gv.trailing_stop = 20  
        hm.frame = self.create_mock_frame([
            {'open': 1.1000, 'high': 1.1000, 'low': 1.1000, 'close': 1.1000, 'signal': 'Open_buy'},
            {'open': 1.1030, 'high': 1.1030, 'low': 1.1030, 'close': 1.1030},
            {'open': 1.1030, 'high': 1.1030, 'low': 1.1010, 'close': 1.1010}
        ])
        hm.strategy.stop_loss = 1.0950
        hm.strategy.take_profit = 1.1150

        hm.lets_trade("EURUSD")
        assert hm.orders_count == 1
        assert hm.profit > 0 
        assert hm.profit_orders_count == 1

    def test_get_efficiency_zero_division(self, hm):
        hm.orders_count = 0
        hm.profit_orders_count = 0
        result = hm.get_efficiency()
        assert result is None

    def test_get_efficiency_success(self, hm):
        hm.orders_count = 5
        hm.profit_orders_count = 4  
        assert hm.get_efficiency() == 80.0
