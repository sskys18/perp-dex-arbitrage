"""Arbitrage engine for detecting and emitting signals"""

import time
import uuid
from decimal import Decimal
from typing import Dict, Optional, Callable, Awaitable

from config import ArbitrageConfig
from models import Signal, MarketUpdate
from .state import StateEngine
from .cost import CostEngine


class ArbitrageEngine:
    """Detects arbitrage opportunities and emits signals"""

    def __init__(
        self,
        config: ArbitrageConfig,
        state_engine: StateEngine,
        cost_engine: CostEngine,
        on_signal: Callable[[Signal], Awaitable[None]],
    ):
        """
        Initialize arbitrage engine

        Args:
            config: Arbitrage configuration
            state_engine: State engine for market data
            cost_engine: Cost engine for fee calculations
            on_signal: Async callback when signal is detected
        """
        self.config = config
        self.state = state_engine
        self.cost = cost_engine
        self.on_signal = on_signal
        # Cooldown tracking: symbol -> last_signal_time
        self._cooldowns: Dict[str, float] = {}

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Check if symbol is on cooldown"""
        last_signal = self._cooldowns.get(symbol, 0)
        return (time.time() - last_signal) < self.config.signal_cooldown_seconds

    def _set_cooldown(self, symbol: str) -> None:
        """Set cooldown for symbol"""
        self._cooldowns[symbol] = time.time()

    async def evaluate(self, symbol: str) -> Optional[Signal]:
        """
        Evaluate arbitrage opportunity for a symbol.
        Called after each market update.

        Returns Signal if opportunity found, None otherwise.
        """
        # Check cooldown
        if self._is_on_cooldown(symbol):
            return None

        # Get all valid quotes for this symbol
        quotes = self.state.get_all_quotes(symbol)
        if len(quotes) < 2:
            return None  # Need at least 2 exchanges

        # Compute scores for each exchange
        best_sell: Optional[tuple] = None  # (exchange, score, price, size)
        best_buy: Optional[tuple] = None   # (exchange, score, price, size)

        for exchange, quote in quotes.items():
            # Sell side: we sell at bid price
            sell_score = self.cost.compute_sell_score(quote.bid_px, exchange, symbol)
            if best_sell is None or sell_score > best_sell[1]:
                best_sell = (exchange, sell_score, quote.bid_px, quote.bid_sz)

            # Buy side: we buy at ask price
            buy_score = self.cost.compute_buy_score(quote.ask_px, exchange, symbol)
            if best_buy is None or buy_score < best_buy[1]:
                best_buy = (exchange, buy_score, quote.ask_px, quote.ask_sz)

        if not best_sell or not best_buy:
            return None

        # Ensure different exchanges
        if best_sell[0] == best_buy[0]:
            return None

        sell_exchange, sell_score, sell_price, sell_size = best_sell
        buy_exchange, buy_score, buy_price, buy_size = best_buy

        # Calculate edge
        edge_absolute = sell_score - buy_score
        mid_price = (sell_price + buy_price) / 2
        edge_bps = (edge_absolute / mid_price) * Decimal("10000") if mid_price > 0 else Decimal("0")

        # Check thresholds
        if edge_bps < self.config.min_edge_bps:
            return None
        if edge_absolute < self.config.min_edge_absolute:
            return None

        # Determine quantity (min of both sides)
        qty = min(sell_size, buy_size)

        # Create signal
        signal = Signal(
            signal_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            sell_exchange=sell_exchange,
            buy_exchange=buy_exchange,
            qty=qty,
            sell_price=sell_price,
            buy_price=buy_price,
            sell_score=sell_score,
            buy_score=buy_score,
            edge_absolute=edge_absolute,
            edge_bps=edge_bps,
            sell_fee=self.cost.get_taker_fee(sell_exchange),
            buy_fee=self.cost.get_taker_fee(buy_exchange),
            sell_funding=self.cost.get_funding(sell_exchange, symbol),
            buy_funding=self.cost.get_funding(buy_exchange, symbol),
            created_ts=int(time.time() * 1000),
        )

        # Set cooldown and emit
        self._set_cooldown(symbol)
        await self.on_signal(signal)
        return signal
