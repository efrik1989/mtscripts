import json
import os
from dataclasses import dataclass
from typing import List, Tuple, Any
from models.strategy_enum import Strategy
import core.app_logger as app_logger

logger = app_logger.get_logger(__name__)


@dataclass
class RiskConfig:
    max_open_positions: int = 4
    risk_per_trade_pct: float = 1.5
    max_deposit_share: float = 0.25


@dataclass
class InstrumentConfig:
    symbol: str
    strategy_name: str
    timeframe: str = "H4"
    buy_sell: bool = False
    trailing_stop: str | int | float = 0
    dynamic_take_profit: bool = False
    bars_range: int = 300


class ConfigLoader:
    @staticmethod
    def _resolve(param_name: str, cli_args, json_val: Any, default_val: Any) -> Any:
        """
        Строгий приоритет:
        1. Явно переданный флаг в CLI (если param_name есть в cli_args.explicit_cli)
        2. Значение из JSON-конфига (если оно там указано)
        3. Значение по умолчанию (из default_val / args_parser)
        """
        explicit_set = getattr(cli_args, "explicit_cli", set())
        if param_name in explicit_set:
            return getattr(cli_args, param_name)
        if json_val is not None:
            return json_val
        return default_val

    @staticmethod
    def load_from_json(config_path: str, cli_args) -> Tuple[List[InstrumentConfig], RiskConfig]:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Настройки риска: CLI -> JSON -> Default из args_parser
        risk_data = data.get("risk_settings", {})
        risk_config = RiskConfig(
            max_open_positions=int(ConfigLoader._resolve("max_positions", cli_args, risk_data.get("max_open_positions"), cli_args.max_positions)),
            risk_per_trade_pct=float(ConfigLoader._resolve("trade_risk_pct", cli_args, risk_data.get("risk_per_trade_pct"), cli_args.trade_risk_pct)),
            max_deposit_share=float(ConfigLoader._resolve("deposit_share", cli_args, risk_data.get("max_deposit_share"), cli_args.deposit_share)),
        )

        # 2. Инструменты: если в CLI передан -s (--symbols), фильтруем или переопределяем список
        explicit_set = getattr(cli_args, "explicit_cli", set())
        cli_symbols_filter = set(s.upper() for s in cli_args.symbols) if "symbols" in explicit_set else None

        items = data.get("portfolio", [])
        configs: List[InstrumentConfig] = []
        used_symbols = set()

        for idx, item in enumerate(items):
            if not item.get("enabled", True):
                continue

            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue

            # Если в консоли указали конкретные тикеры вместе с -c, берём только их из конфига
            if cli_symbols_filter is not None and symbol not in cli_symbols_filter:
                continue

            if symbol in used_symbols:
                logger.warning(f"Конфиг [{symbol}]: дубликат тикера пропущен.")
                continue

            strat_name = str(ConfigLoader._resolve("strategy", cli_args, item.get("strategy"), cli_args.strategy)).strip()
            if strat_name not in Strategy.__members__:
                logger.error(f"Конфиг [{symbol}]: неизвестная стратегия '{strat_name}'.")
                continue

            used_symbols.add(symbol)
            configs.append(
                InstrumentConfig(
                    symbol=symbol,
                    strategy_name=strat_name,
                    timeframe=str(ConfigLoader._resolve("timeframe", cli_args, item.get("timeframe"), cli_args.timeframe)).strip(),
                    buy_sell=bool(ConfigLoader._resolve("buy_sell", cli_args, item.get("buy_sell"), cli_args.buy_sell)),
                    trailing_stop=ConfigLoader._resolve("trailing_stop", cli_args, item.get("trailing_stop"), cli_args.trailing_stop),
                    dynamic_take_profit=bool(ConfigLoader._resolve("dynamic_take_profit", cli_args, item.get("dynamic_take_profit"), cli_args.dynamic_take_profit)),
                    bars_range=int(ConfigLoader._resolve("range", cli_args, item.get("range"), cli_args.range)),
                )
            )

        return configs, risk_config

    @staticmethod
    def build_from_args(cli_args) -> Tuple[List[InstrumentConfig], RiskConfig]:
        if cli_args.config:
            return ConfigLoader.load_from_json(cli_args.config, cli_args)

        risk_config = RiskConfig(
            max_open_positions=int(cli_args.max_positions),
            risk_per_trade_pct=float(cli_args.trade_risk_pct),
            max_deposit_share=float(cli_args.deposit_share),
        )

        unique_symbols = list(dict.fromkeys(cli_args.symbols or []))
        configs = [
            InstrumentConfig(
                symbol=symbol,
                strategy_name=cli_args.strategy,
                timeframe=cli_args.timeframe,
                buy_sell=bool(cli_args.buy_sell),
                trailing_stop=cli_args.trailing_stop,
                dynamic_take_profit=bool(cli_args.dynamic_take_profit),
                bars_range=int(cli_args.range),
            )
            for symbol in unique_symbols
        ]
        return configs, risk_config
