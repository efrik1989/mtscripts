import json
import os
from dataclasses import dataclass
from typing import List, Tuple
from models.strategy_enum import Strategy
import core.app_logger as app_logger

logger = app_logger.get_logger(__name__)


@dataclass
class RiskConfig:
    """Параметры портфельного риск-менеджмента."""
    max_open_positions: int = 4
    risk_per_trade_pct: float = 1.5
    max_deposit_share: float = 0.25


@dataclass
class InstrumentConfig:
    """Индивидуальная конфигурация запуска для одного инструмента."""
    symbol: str
    strategy_name: str
    timeframe: str
    buy_sell: bool = False
    trailing_stop: str | int | float = 0
    dynamic_take_profit: bool = False
    bars_range: int = 300


class ConfigLoader:
    @staticmethod
    def load_from_json(config_path: str, default_args) -> Tuple[List[InstrumentConfig], RiskConfig]:
        """Читает JSON-файл и возвращает список инструментов и настройки рисков."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Опциональный блок risk_settings (приоритет над флагами консоли)
        risk_data = data.get("risk_settings", {})
        risk_config = RiskConfig(
        max_open_positions=int(risk_data.get("max_open_positions") or default_args.max_positions or RiskConfig.max_open_positions),
        risk_per_trade_pct=float(risk_data.get("risk_per_trade_pct") or default_args.trade_risk_pct or RiskConfig.risk_per_trade_pct),
        max_deposit_share=float(risk_data.get("max_deposit_share") or default_args.deposit_share or RiskConfig.max_deposit_share)
     )

        # 2. Список инструментов
        items = data.get("portfolio", [])
        configs: List[InstrumentConfig] = []
        used_symbols = set()

        for idx, item in enumerate(items):
            if not item.get("enabled", True):
                continue

            symbol = str(item.get("symbol", "")).strip().upper()
            strat_name = str(item.get("strategy", "")).strip()

            if not symbol or not strat_name:
                logger.warning(f"Конфиг [запись {idx}]: пропущена строка с пустым symbol или strategy.")
                continue

            if symbol in used_symbols:
                logger.warning(f"Конфиг [{symbol}]: дубликат тикера пропущен (защита от конфликта позиций в MT5).")
                continue

            if strat_name not in Strategy.__members__:
                logger.error(
                    f"Конфиг [{symbol}]: неизвестная стратегия '{strat_name}'. "
                    f"Доступные: {list(Strategy.__members__.keys())}"
                )
                continue

            used_symbols.add(symbol)
            configs.append(
                InstrumentConfig(
                    symbol=symbol,
                    strategy_name=strat_name,
                    timeframe=str(item.get("timeframe", default_args.timeframe)).strip(),
                    buy_sell=bool(item.get("buy_sell", default_args.buy_sell)),
                    trailing_stop=item.get("trailing_stop", default_args.trailing_stop),
                    dynamic_take_profit=bool(item.get("dynamic_take_profit", default_args.dynamic_take_profit)),
                    bars_range=int(item.get("range", default_args.range))
                )
            )

        return configs, risk_config

    @staticmethod
    def build_from_args(args) -> Tuple[List[InstrumentConfig], RiskConfig]:
        """Формирует конфигурации инструментов и рисков из JSON или аргументов консоли."""
        if args.config:
            return ConfigLoader.load_from_json(args.config, args)

        risk_config = RiskConfig(
        max_open_positions=int(args.max_positions or RiskConfig.max_open_positions),
        risk_per_trade_pct=float(args.trade_risk_pct or RiskConfig.risk_per_trade_pct),
        max_deposit_share=float(args.deposit_share or RiskConfig.max_deposit_share)
        )

        configs: List[InstrumentConfig] = []
        unique_symbols = list(dict.fromkeys(args.symbols or []))
        for symbol in unique_symbols:
            configs.append(
                InstrumentConfig(
                    symbol=symbol,
                    strategy_name=args.strategy,
                    timeframe=args.timeframe,
                    buy_sell=bool(args.buy_sell),
                    trailing_stop=args.trailing_stop,
                    dynamic_take_profit=bool(args.dynamic_take_profit),
                    bars_range=int(args.range)
                )
            )
        return configs, risk_config
