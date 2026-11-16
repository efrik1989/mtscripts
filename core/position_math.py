class PositionMath:
    @staticmethod
    def calculate_trailing_sl(
        is_buy: bool,
        open_price: float,
        current_price: float,
        current_sl: float | None,
        be_trigger_dist: float,
        trail_dist: float,
        commission_pct: float = 0.0657
    ) -> float | None:
        """
        Единый расчёт нового Stop Loss (ступень безубытка + скользящий трал).
        Возвращает новое значение SL или None, если сдвиг не требуется.
        """
        if trail_dist <= 0:
            return None

        be_buffer = open_price * (commission_pct / 100.0) * 1.5
        target_sl = current_sl

        if is_buy:
            if be_trigger_dist > 0 and current_price >= open_price + be_trigger_dist:
                be_sl = open_price + be_buffer
                if target_sl is None or target_sl == 0 or be_sl > target_sl:
                    target_sl = be_sl

            if current_price > open_price:
                trail_sl = current_price - trail_dist
                if target_sl is None or target_sl == 0 or trail_sl > target_sl:
                    target_sl = trail_sl

            if target_sl and (current_sl is None or current_sl == 0 or target_sl > current_sl):
                return float(target_sl)

        else:
            if be_trigger_dist > 0 and current_price <= open_price - be_trigger_dist:
                be_sl = open_price - be_buffer
                if target_sl is None or target_sl == 0 or be_sl < target_sl:
                    target_sl = be_sl

            if current_price < open_price:
                trail_sl = current_price + trail_dist
                if target_sl is None or target_sl == 0 or trail_sl < target_sl:
                    target_sl = trail_sl

            if target_sl and (current_sl is None or current_sl == 0 or target_sl < current_sl):
                return float(target_sl)

        return None

    @staticmethod
    def calculate_dynamic_tp(
        is_buy: bool,
        open_price: float,
        current_tp: float | None,
        proposed_tp: float | None,
        min_step: float = 0.0,
        commission_pct: float = 0.0657
    ) -> float | None:
        """
        Единый расчёт динамического Take Profit.
        Проверяет, что новый TP не уходит в убыточную зону (с учётом комиссии)
        и отличается от текущего минимум на min_step (защита от спама заявками в MT5).
        """
        if proposed_tp is None or proposed_tp <= 0:
            return None

        comm_buffer = open_price * (commission_pct / 100.0) * 1.5

        # 1. Защита от переноса TP в зону убытка или ниже комиссии
        if is_buy:
            if proposed_tp <= open_price + comm_buffer:
                return None
        else:
            if proposed_tp >= open_price - comm_buffer:
                return None

        # 2. Если TP ещё не был установлен — ставим предложенный уровень
        if current_tp is None or current_tp == 0:
            return float(proposed_tp)

        # 3. Проверяем минимальный шаг изменения (например, 0.5 * ATR),
        # чтобы в реальной торговле не отправлять запросы при сдвиге на 1 копейку
        if abs(proposed_tp - current_tp) < min_step:
            return None

        return float(proposed_tp)
