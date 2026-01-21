"""Configuration for arbitrage signal generator"""

from decimal import Decimal
from dataclasses import dataclass, field
from typing import List


@dataclass
class ArbitrageConfig:
    """Arbitrage engine configuration"""

    # Minimum edge in basis points to emit a signal
    min_edge_bps: Decimal = Decimal("5")

    # Minimum absolute edge in USD
    min_edge_absolute: Decimal = Decimal("0.10")

    # Cooldown between signals for same symbol (seconds)
    signal_cooldown_seconds: int = 5

    # Max quote age in milliseconds before considering stale
    max_quote_age_ms: int = 2000

    # Symbols to trade (empty = all common symbols)
    symbols: List[str] = field(default_factory=list)

    # Exchanges to enable (empty = all)
    enabled_exchanges: List[str] = field(default_factory=list)


# Default configuration
DEFAULT_CONFIG = ArbitrageConfig()


# Default fee rates for exchanges without fee API
DEFAULT_FEES = {
    "hyperliquid": {"maker": Decimal("0.0001"), "taker": Decimal("0.00035")},
    "paradex": {"maker": Decimal("0.0002"), "taker": Decimal("0.0004")},
    "backpack": {"maker": Decimal("0.0002"), "taker": Decimal("0.0005")},
    "grvt": {"maker": Decimal("-0.000001"), "taker": Decimal("0.00045")},
    "nado": {"maker": Decimal("0.0002"), "taker": Decimal("0.0005")},
    "extended": {"maker": Decimal("0.0002"), "taker": Decimal("0.0004")},
    "pacifica": {"maker": Decimal("0.000075"), "taker": Decimal("0.0002")},
    "standx": {"maker": Decimal("0.0001"), "taker": Decimal("0.0004")},
}
