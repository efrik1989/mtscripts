import math
import MetaTrader5 as Mt5
import mt5.mt5_actions
from abstractEasyT import trade
import core.app_logger as app_logger
from position_math import PositionMath

logger = app_logger.get_logger(__name__)


class Trade(trade.Trade):
    """
    This class is responsible to handle all the trade requests.
    """

    def __init__(self,
                 symbol: str,
                 lot: float,
                 stop_loss: float,
                 take_profit: float
                 ):

        """
        It is allowed to have only one position at time per symbol, right now it is not possible to open a position and
        increase the size of it or to open opposite position. Open an open position will close the other direction one.

        Args:
            symbol:
                It is the symbol you want to open or close or check if already have an operation opened.

            lot:
                It is how many shares you want to trade, many symbols allow fractions and others requires a
                certain amount. It can be 0.01, 100.0, 1000.0, 10000.0.

            stop_loss:
                It is how much you accept to lose. Example: If you buy a share for US$10.00, and you accept to lose US$1.00
                you set this variable at 1.00, you will be out of the operation at US$9.00 (sometimes more, somtime less,
                the US$9.00 is the trigger). Keep in mind that some symbols has different points metrics, US$1.00 sometimes
                can be 1000 points.

            take_profit:
                It is how much you accept to win. Example: If you buy a share for US$10.00, and you accept to win US$1.00
                you set this variable at 1.00, you will be out of the operation at US$11.00 (sometimes more, somtime less,
                the US$11.00 is the trigger). Keep in mind that some symbols has different points metrics, US$1.00 sometimes
                can be 1000 points.

        """

        self.symbol = symbol.upper()
        self.lot = lot
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.ticket = None
        self.points = Mt5.symbol_info(self.symbol).trade_tick_size

        self._trade_allowed = True

        self.trade_direction = None  # 'buy', 'sell', or None for no position
        self.position_check()

    def normalize(self, price: float) -> float:
        """
        This function normalize the price to ensure a precision that is required by the platform

        Args:
            price:
                It is the price that you want to be normalized, usually is the last price to open a market position.

        Returns:
            It returns the float price normalized under a precision that is accepted by the platform.

        Examples:

            >>> # All the code you need to execute the function:
            >>> from metatrader5EasyT.initialization import Initialize
            >>> from metatrader5EasyT.trade import Trade
            >>> initialize = Initialize()
            >>> initialize.initialize_platform()
            >>> initialize.initialize_symbol('EURUSD')
            >>> eurusd_trade = Trade(symbol='EURUSD', lot=1.0, stop_loss=1.0, take_profit=1.0)
            >>> # The normalize function is used inside other functions, but the idea is to normalize the value to
            >>> # be accepted in the trade request. If you want to see this function in action you can look at
            >>> # open_buy() and open_sell()
            >>> eurusd_trade.normalize(12.3456789)
            12.34

        """
        logger.info(f'{self.symbol}: Normalizing the price')
        return math.floor(float(self.points * round(price / self.points)) * 100) / 100

    def open_buy(self) -> bool:
        tick = Mt5.symbol_info_tick(self.symbol)
        if tick is None or tick.ask <= 0:
            logger.warning(f"{self.symbol}: Не удалось получить цену Ask для покупки (возможно клиринг или сбой связи).")
            return False

        price = float(tick.ask)
        sl_price = self.normalize(price - self.stop_loss) if self.stop_loss else 0.0
        tp_price = self.normalize(price + self.take_profit) if self.take_profit else 0.0

        logger.info(
            f"BUY Order sent: {self.symbol}, {self.lot} lot(s), at {price}, "
            f"stoploss: {sl_price}, takeprofit: {tp_price}."
        )

        request = {
            "action": Mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(self.lot),
            "type": Mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 10,
            "magic": getattr(self, 'magic', 7777),
            "comment": "python_bot",
            "type_time": Mt5.ORDER_TIME_GTC,
            "type_filling": Mt5.ORDER_FILLING_RETURN,
        }

        result = Mt5.order_send(request)

        if result is None or result.retcode != Mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else Mt5.last_error()
            logger.error(f"{self.symbol}: Ошибка открытия BUY (retcode={retcode}): {comment}")
            return False

        logger.info(f"{self.symbol}: Позиция BUY успешно открыта (ticket={result.order}).")
        self.trade_direction = 'buy'
        return True


    def open_sell(self):
        """
        This functions when called send a sell request to Metatrader5 with the parameters in the attributes.

        Returns:
            It returns None, but if an error occurs when open a position it will break.

        Examples:

            Try this on your demo account with fake money, a position will be opened.

            >>> # All the code you need to execute the function:
            >>> from metatrader5EasyT.initialization import Initialize
            >>> from metatrader5EasyT.trade import Trade
            >>> initialize = Initialize()
            >>> initialize.initialize_platform()
            True
            2022-03-11 04:47:29,903 WARNING - initialize_platform - "Algotrading" not allowed! You cannot open position,
            but you can retrieve data. If you want to open positions, please, go to Metatrader5 and press the button
            "Algotrading."
            >>> initialize.initialize_symbol('EURUSD')
            >>> eurusd_trade = Trade(symbol='EURUSD', lot=1.0, stop_loss=1.0, take_profit=1.0)
            >>> # When I try to open a position and the Algotrading is not allowed on Metatrader5 I got a warning.
            >>> eurusd_trade.open_sell()
            2022-03-11 04:57:08,628 ERROR - open_sell - Something went wrong: Position Not Found for symbol EURUSD!
            Last Error: (1, 'Success')
            >>> # But when I allow algotrading, I return None, you can see at Metatrader5 that a buy
            position was opened.
            >>> eurusd_trade.open_sell()
            None
            >>> # Just for curiosity, if you want to try to open a buy position with this sell opened you will close
            >>> # the sell position
            >>> eurusd_trade.open_buy()
            None

        """
        price = Mt5.symbol_info_tick(self.symbol).bid

        self.ticket = (Mt5.positions_get(symbol=self.symbol)[0].ticket if len(
            Mt5.positions_get(symbol=self.symbol)) == 1 else 0)

        logger.info(f'{self.symbol}: SELL Order sent: {self.symbol},'
                              f' {self.lot} lot(s),'
                              f' at {price},'
                              f' stoploss:{self.normalize(price - self.stop_loss)},'
                              f' takeprofit: {self.normalize(price + self.take_profit)}.')

        request = {
            "action": Mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.lot,
            "type": Mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": self.normalize(price + self.stop_loss),
            "tp": self.normalize(price - self.take_profit),
            "deviation": 5,
            "magic": 7777,
            "comment": "easyT",
            "type_time": Mt5.ORDER_TIME_GTC,
            "type_filling": Mt5.ORDER_FILLING_RETURN,
            "position": (Mt5.positions_get(symbol=self.symbol)[0].ticket if len(
                Mt5.positions_get(symbol=self.symbol)) == 1 else 0)
        }

        result = Mt5.order_send(request)
        if result is None or result.retcode != Mt5.TRADE_RETCODE_DONE:
            logger.error(f'{self.symbol}: Something went wrong: Position Not Found for symbol {self.symbol}!'
                                   f' Last Error: {Mt5.last_error()}')

        else:
            logger.info(f'{self.symbol}: Change trade direction to SELL.')
            self.trade_direction = 'sell'

    def open_sell(self) -> bool:
        tick = Mt5.symbol_info_tick(self.symbol)
        if tick is None or tick.bid <= 0:
            logger.warning(f"{self.symbol}: Не удалось получить цену Bid для продажи (возможно клиринг или сбой связи).")
            return False

        price = float(tick.bid)
        # Для продажи SL ставится ВЫШЕ цены входа, а TP — НИЖЕ цены входа
        sl_price = self.normalize(price + self.stop_loss) if self.stop_loss else 0.0
        tp_price = self.normalize(price - self.take_profit) if self.take_profit else 0.0

        logger.info(
            f"SELL Order sent: {self.symbol}, {self.lot} lot(s), at {price}, "
            f"stoploss: {sl_price}, takeprofit: {tp_price}."
        )

        request = {
            "action": Mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(self.lot),
            "type": Mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 10,
            "magic": getattr(self, 'magic', 7777),
            "comment": "python_bot",
            "type_time": Mt5.ORDER_TIME_GTC,
            "type_filling": Mt5.ORDER_FILLING_RETURN,
        }

        result = Mt5.order_send(request)

        if result is None or result.retcode != Mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else Mt5.last_error()
            logger.error(f"{self.symbol}: Ошибка открытия SELL (retcode={retcode}): {comment}")
            return False

        logger.info(f"{self.symbol}: Позиция SELL успешно открыта (ticket={result.order}).")
        self.trade_direction = 'sell'
        return True


    def position_close(self) -> None:
        """
        This functions checks the trade direction, and it opens an opposite position to the current one to close it.
        If there is no position nothing happens.

        Returns:
            Close the current position by opening an opposite one.

        Examples:

            Try this on your demo account with fake money, a position will be opened.

            >>> # All the code you need to execute the function:
            >>> from metatrader5EasyT.initialization import Initialize
            >>> from metatrader5EasyT.trade import Trade
            >>> initialize = Initialize()
            >>> initialize.initialize_platform()
            True
            >>> initialize.initialize_symbol('EURUSD')
            >>> eurusd_trade = Trade(symbol='EURUSD', lot=1.0, stop_loss=1.0, take_profit=1.0)
            >>> eurusd_trade._trade_allowed = True
            >>> # Opening a position with Algotrading allowed and, eurusd_trade._trade_allowed True
            >>> # To know more about eurusd_trade._trade_allowed look the Examples in position_open() documentation.
            >>> eurusd_trade.position_open(False, True)
            'sell'
            >>> # When there is a position opened, eurusd_trade.position_close() will open a position in a different
            >>> # direction to close it.
            >>> eurusd_trade.position_close()
            None
            # It checks the trading direction, return none when there is no trade opened.
            >>> eurusd_trade.trade_direction
            None
            # I will open a buy position, check the trade direction and close it!
            >>> eurusd_trade.position_open(True, False)
            'buy'
            >>>  eurusd_trade.trade_direction
            'buy'
            >>> eurusd_trade.position_close()
            >>> # We can see that it worked!
            >>> # What happens when I call eurusd_trade.position_close() with no position opened?
            >>> eurusd_trade.position_close()
            None
            >>> # Nothing happens, there are no position to be closed.


        """
        logger.info(f'{self.symbol}: Close position called.')
        self.position_check()
        if self.trade_direction == 'buy':
            logger.info(f'{self.symbol}: Close BUY position.')
            self.open_sell()
            self.position_check()

        elif self.trade_direction == 'sell':
            logger.info(f'{self.symbol}: Close SELL position')
            self.open_buy()
            self.position_check()

    def position_check(self) -> None:
        """
        This function checks if there are a position opened and update the variable self.trade_direction.
        If there is no position, the self.trade_direction will be updated to None, else, it updates with the trade
        direction, which can be 'sell' or 'buy'.

        Returns:
            This function update the variable self.trade_direction and do not return a result.

        Examples:

            Try this on your demo account with fake money, a position will be opened.

            >>> # All the code you need to execute the function:
            >>> from metatrader5EasyT.initialization import Initialize
            >>> from metatrader5EasyT.trade import Trade
            >>> initialize = Initialize()
            >>> initialize.initialize_platform()
            True
            >>> initialize.initialize_symbol('EURUSD')
            >>> eurusd_trade = Trade(symbol='EURUSD', lot=1.0, stop_loss=1.0, take_profit=1.0)
            >>> eurusd_trade._trade_allowed = True
            >>> # Position check it is just to ensure that the eurusd_trade.trade_direction are in the right direction.
            >>> # The eurusd_trade.trade_direction is automatically handled by buy open_sell() and open_buy() and
            >>> # it returns the trade direction or None when there is no trade opened.
            >>> eurusd_trade.trade_direction
            None
            >>> eurusd_trade.position_open(True, False)
            'buy'
            >>> eurusd_trade.trade_direction
            'buy'
            >>> # After I open a buy position, it returns 'buy' to trade_direction, but, what happens if I manually
            >>> # change the direction?
            >>> eurusd_trade.trade_direction = 'coffee shop'
            None
            >>> eurusd_trade.trade_direction
            'coffee shop'
            >>> # It is possible to see that the trade_direction was changed.
            >>> # and the position_check() is called in all the functions that opens and closes position
            >>> # to ensure that direction is correct, I will call position_check() to fix my change to 'coffee shop'
            >>> eurusd_trade.position_check()
            None
            >>> eurusd_trade.trade_direction
            'buy'
            >>> # It worked.
            >>> # That is it, I will just the position that I opened before.
            >>> eurusd_trade.position_close()


        """
        logger.info(f'{self.symbol}: Calls Metatrader5 to check if there is a position opened.')
        result = Mt5.positions_get(symbol=self.symbol)
        isOpen = False
        if len(result) > 0:
            logger.info(f'{self.symbol}: There is a position opened.')
            isOpen = True
            if result[0].type == 0:  # if buy
                logger.info(f'{self.symbol}: Set the trade direction to BUY')
                self.trade_direction = 'buy'

            elif result[0].type == 1:  # if sell
                logger.info(f'{self.symbol}: Set the trade direction to SELL')
                self.trade_direction = 'sell'
        else:
            logger.info(f'{self.symbol}: There are no position opened.')
            logger.info(f'{self.symbol}: Set the trade direction to None')
            self.trade_direction = None
            isOpen = False
        return isOpen

    def check_and_update_trailing(
        self,
        symbol: str,
        trailing_points: float,
        breakeven_trigger_pts: float = None,
        commission_pct: float = 0.0657
    ):
        """
        Обновляет Stop Loss с учетом ступени безубытка (1.8 * ATR) и скользящего трейлинга.
        """
        symbol_info = Mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.warning(f"{symbol}: Не удалось получить symbol_info из MT5.")
            return

        point = symbol_info.point
        digits = symbol_info.digits
        # Минимально разрешенный брокером отступ от текущей цены для установки SL/TP
        min_stop_dist = symbol_info.trade_stops_level * point

        positions = Mt5.positions_get(symbol=symbol)
        if not positions:
            return

        tick = Mt5.symbol_info_tick(symbol)
        if tick is None or tick.bid <= 0 or tick.ask <= 0:
            logger.warning(f"{symbol}: Некорректный тик (bid/ask = 0), пропускаем обновление трала.")
            return

        for pos in positions:
            is_buy = (pos.type == Mt5.POSITION_TYPE_BUY)
            current_price = tick.bid if is_buy else tick.ask

            new_sl = PositionMath.calculate_trailing_sl(
                is_buy=is_buy,
                open_price=pos.price_open,
                current_price=current_price,
                current_sl=pos.sl,
                be_trigger_dist=(breakeven_trigger_pts * point) if breakeven_trigger_pts else 0.0,
                trail_dist=trailing_points * point,
                commission_pct=commission_pct
            )

            if new_sl is not None:
                new_sl_rounded = round(new_sl, digits)
                # Проверяем, что новый SL реально изменился минимум на 1 шаг цены и не нарушает stops_level брокера
                price_diff_ok = (pos.sl == 0) or (abs(new_sl_rounded - pos.sl) >= point)
                broker_dist_ok = (current_price - new_sl_rounded >= max(min_stop_dist, point)) if is_buy else (
                    new_sl_rounded - current_price >= max(min_stop_dist, point)
                )

                if price_diff_ok and broker_dist_ok:
                    self.modify_position_sl(pos.ticket, new_sl_rounded, pos.tp)

    def modify_position_sl(self, position_ticket: int, new_sl: float, tp: float):
        """Безопасно обновляет Stop Loss, сохраняя текущий Take Profit."""
        request = {
            "action": Mt5.TRADE_ACTION_SLTP,
            "position": position_ticket,
            "sl": float(new_sl),
            "tp": float(tp) if tp else 0.0,
        }
        result = Mt5.order_send(request)
        if result is None:
            logger.error(f"#{position_ticket}: Mt5.order_send вернул None (ошибка соединения с терминалом).")
            return

        if result.retcode != Mt5.TRADE_RETCODE_DONE:
            logger.warning(f"#{position_ticket}: Ошибка модификации SL={new_sl} (retcode={result.retcode}): {result.comment}")
        else:
            logger.info(f"#{position_ticket}: SL успешно обновлён до {new_sl} (TP={tp} сохранён).")

    def change_take_profit(self, symbol: str, proposed_tp: float, commission_pct: float = 0.0657):
        """Безопасно обновляет Take Profit через единую математику PositionMath."""
        symbol_info = Mt5.symbol_info(symbol)
        positions = Mt5.positions_get(symbol=symbol)
        tick = Mt5.symbol_info_tick(symbol)

        if not positions or symbol_info is None or tick is None:
            return

        position = positions[0]
        is_buy = (position.type == Mt5.POSITION_TYPE_BUY)
        current_price = tick.bid if is_buy else tick.ask
        min_stop_dist = symbol_info.trade_stops_level * symbol_info.point

        new_tp = PositionMath.calculate_dynamic_tp(
            is_buy=is_buy,
            open_price=position.price_open,
            current_tp=position.tp,
            proposed_tp=proposed_tp,
            min_step=self.atr * 0.5,
            commission_pct=commission_pct
        )

        if new_tp is None:
            return

        new_tp_rounded = round(new_tp, symbol_info.digits)

        # Проверяем минимальный отступ от текущей рыночной цены, требуемый брокером
        dist_ok = (new_tp_rounded - current_price >= min_stop_dist) if is_buy else (
            current_price - new_tp_rounded >= min_stop_dist
        )
        if not dist_ok:
            return

        request = {
            "action": Mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": symbol,
            "sl": float(position.sl),
            "tp": float(new_tp_rounded),
            "magic": getattr(self, 'magic', 7777),
            "comment": "dynamic TP, python",
        }
        result = Mt5.order_send(request)
        if result is None or result.retcode != Mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else Mt5.last_error()
            logger.error(f"{symbol} #{position.ticket}: Ошибка обновления TP={new_tp_rounded}: {err}")
        else:
            self.take_profit = new_tp_rounded
            logger.info(f"{symbol} #{position.ticket}: TP обновлён до {new_tp_rounded} (SL={position.sl} сохранён).")



