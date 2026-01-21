"""Abstract base class for exchange adapters"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate


class BaseExchangeAdapter(ABC):
    """
    Abstract base for all exchange adapters.
    Normalizes all 5 features: list_symbols, get_symbol_info, get_funding_rate,
    get_fee_rates, subscribe_market_data
    """

    name: str                       # Exchange identifier
    default_taker_fee: Decimal      # Fallback taker fee
    default_maker_fee: Decimal      # Fallback maker fee

    def __init__(self):
        self._symbol_map: dict = {}     # normalized -> exchange
        self._reverse_map: dict = {}    # exchange -> normalized

    # ==================== Feature 1: list_symbols ====================
    @abstractmethod
    async def list_symbols(self) -> List[str]:
        """
        Fetch all available perp symbols.
        Returns: List of normalized symbol names ["BTC", "ETH", ...]
        """
        pass

    # ==================== Feature 2: get_symbol_info ====================
    @abstractmethod
    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """
        Get detailed symbol information.
        Args:
            symbol: Normalized symbol (optional, None = all symbols)
        Returns: List of SymbolInfo
        """
        pass

    # ==================== Feature 3: get_funding_rate ====================
    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """
        Get current funding rate for a symbol.
        Args:
            symbol: Normalized symbol
        Returns: FundingRate with current rate
        """
        pass

    # ==================== Feature 4: get_fee_rates ====================
    @abstractmethod
    async def get_fee_rates(self) -> FeeRates:
        """
        Get fee rates for this exchange.
        Returns: FeeRates (from API or default values)
        """
        pass

    # ==================== Feature 5: subscribe_market_data ====================
    @abstractmethod
    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """
        Subscribe to real-time market data (BBO or L2).
        Args:
            symbols: List of normalized symbols
            on_update: Async callback for MarketUpdate events
        """
        pass

    # ==================== Utility Methods ====================
    def get_exchange_symbol(self, normalized_symbol: str) -> str:
        """Convert normalized symbol to exchange-specific format"""
        return self._symbol_map.get(normalized_symbol, normalized_symbol)

    def get_normalized_symbol(self, exchange_symbol: str) -> str:
        """Convert exchange-specific symbol to normalized format"""
        return self._reverse_map.get(exchange_symbol, exchange_symbol)

    @abstractmethod
    async def close(self) -> None:
        """Close all connections"""
        pass
