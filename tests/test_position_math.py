import pytest
from core.position_math import PositionMath


class TestPositionMathTrailingSL:
    """Тесты единой логики расчёта Stop Loss (безубыток + скользящий трал)."""

    def test_trailing_disabled_when_dist_zero(self):
        """Если дистанция трала <= 0, метод должен возвращать None."""
        res = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=105.0,
            current_sl=98.0,
            be_trigger_dist=2.0,
            trail_dist=0.0
        )
        assert res is None

    def test_buy_no_move_before_breakeven_and_trail(self):
        """Для BUY: цена выросла недостаточно для безубытка, а трал ещё ниже текущего SL -> None."""
        # Вход 100.0, SL 98.0, порог БУ 2.0 (цена >= 102.0), трал 3.0
        # Текущая цена 101.5: до БУ не дошли, трал = 101.5 - 3.0 = 98.5 > 98.0 -> сдвиг на 98.5
        res_move = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=101.5,
            current_sl=98.0,
            be_trigger_dist=2.0,
            trail_dist=3.0
        )
        assert res_move == pytest.approx(98.5)

        # Текущая цена 100.5: трал = 97.5 < 98.0 (старого SL) -> возвращаем None
        res_no_move = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=100.5,
            current_sl=98.0,
            be_trigger_dist=2.0,
            trail_dist=3.0
        )
        assert res_no_move is None

    def test_buy_breakeven_activation(self):
        """Для BUY: цена достигла порога безубытка -> SL переносится на open_price + буфер комиссии."""
        # Комиссия 0.1% -> буфер = 100.0 * 0.001 * 1.5 = 0.15 -> БУ = 100.15
        # Трал при цене 102.0 и дистанции 3.0 равен 99.0 (ниже БУ), поэтому срабатывает именно БУ
        res = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=102.0,
            current_sl=98.0,
            be_trigger_dist=2.0,
            trail_dist=3.0,
            commission_pct=0.1
        )
        assert res == pytest.approx(100.15)

    def test_buy_trailing_overtakes_breakeven(self):
        """Для BUY: при сильном росте скользящий трал выше уровня БУ -> выбирается более высокий трал."""
        # Цена 105.0, трал 3.0 -> 102.0 (выше БУ 100.15)
        res = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=105.0,
            current_sl=100.15,
            be_trigger_dist=2.0,
            trail_dist=3.0,
            commission_pct=0.1
        )
        assert res == pytest.approx(102.0)

    def test_sell_breakeven_and_trailing(self):
        """Для SELL: зеркальная проверка безубытка и трала вниз."""
        # Вход 100.0, SL 102.0, порог БУ 2.0 (цена <= 98.0), комиссия 0.1% -> БУ = 99.85
        res_be = PositionMath.calculate_trailing_sl(
            is_buy=False,
            open_price=100.0,
            current_price=98.0,
            current_sl=102.0,
            be_trigger_dist=2.0,
            trail_dist=3.0,
            commission_pct=0.1
        )
        assert res_be == pytest.approx(99.85)

        # Цена упала до 95.0, трал 3.0 -> новый SL = 98.0 (ниже БУ 99.85)
        res_trail = PositionMath.calculate_trailing_sl(
            is_buy=False,
            open_price=100.0,
            current_price=95.0,
            current_sl=99.85,
            be_trigger_dist=2.0,
            trail_dist=3.0,
            commission_pct=0.1
        )
        assert res_trail == pytest.approx(98.0)

    def test_never_moves_sl_backwards(self):
        """SL никогда не сдвигается в сторону увеличения риска при откате цены."""
        # Для BUY: текущий SL уже 102.0, цена откатила до 103.0 (трал 100.0 < 102.0) -> None
        res_buy = PositionMath.calculate_trailing_sl(
            is_buy=True,
            open_price=100.0,
            current_price=103.0,
            current_sl=102.0,
            be_trigger_dist=2.0,
            trail_dist=3.0
        )
        assert res_buy is None

        # Для SELL: текущий SL уже 98.0, цена отскочила до 97.0 (трал 100.0 > 98.0) -> None
        res_sell = PositionMath.calculate_trailing_sl(
            is_buy=False,
            open_price=100.0,
            current_price=97.0,
            current_sl=98.0,
            be_trigger_dist=2.0,
            trail_dist=3.0
        )
        assert res_sell is None


class TestPositionMathDynamicTP:
    """Тесты единой логики расчёта динамического Take Profit."""

    def test_buy_tp_blocked_if_below_commission_buffer(self):
        """Для BUY: запрет переноса TP в зону убытка или ниже комиссии."""
        # Вход 100.0, комиссия 0.1% -> минимально допустимый TP > 100.15
        res = PositionMath.calculate_dynamic_tp(
            is_buy=True,
            open_price=100.0,
            current_tp=105.0,
            proposed_tp=100.10,
            min_step=0.5,
            commission_pct=0.1
        )
        assert res is None

    def test_sell_tp_blocked_if_above_commission_buffer(self):
        """Для SELL: запрет переноса TP выше цены входа минус комиссия."""
        # Вход 100.0, комиссия 0.1% -> максимально допустимый TP < 99.85
        res = PositionMath.calculate_dynamic_tp(
            is_buy=False,
            open_price=100.0,
            current_tp=95.0,
            proposed_tp=99.90,
            min_step=0.5,
            commission_pct=0.1
        )
        assert res is None

    def test_tp_ignores_micro_changes_below_min_step(self):
        """Если изменение TP меньше min_step, возвращается None (защита от спама заявками)."""
        res = PositionMath.calculate_dynamic_tp(
            is_buy=True,
            open_price=100.0,
            current_tp=105.0,
            proposed_tp=105.2,
            min_step=0.5,
            commission_pct=0.1
        )
        assert res is None

    def test_tp_updates_when_step_sufficient(self):
        """Если изменение TP >= min_step и находится в прибыльной зоне, возвращается новый TP."""
        res_buy = PositionMath.calculate_dynamic_tp(
            is_buy=True,
            open_price=100.0,
            current_tp=105.0,
            proposed_tp=105.6,
            min_step=0.5,
            commission_pct=0.1
        )
        assert res_buy == pytest.approx(105.6)

        res_sell = PositionMath.calculate_dynamic_tp(
            is_buy=False,
            open_price=100.0,
            current_tp=95.0,
            proposed_tp=94.4,
            min_step=0.5,
            commission_pct=0.1
        )
        assert res_sell == pytest.approx(94.4)

    def test_initial_tp_set_when_current_is_zero(self):
        """Если текущий TP равен 0 или None, устанавливается предложенный уровень (при соблюдении комиссии)."""
        res = PositionMath.calculate_dynamic_tp(
            is_buy=True,
            open_price=100.0,
            current_tp=0.0,
            proposed_tp=103.0,
            min_step=1.0,
            commission_pct=0.1
        )
        assert res == pytest.approx(103.0)
