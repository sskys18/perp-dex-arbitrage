"""Arbitrage engine for detecting and emitting signals"""

import asyncio
import time
import uuid
from decimal import Decimal
from typing import Dict, Optional, Callable, Awaitable, Tuple

from config import ArbitrageConfig
from models import Signal, MarketUpdate
from .state import StateEngine, Quote
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
        # Incremental best-score tracking: symbol -> (exchange, score, price, size)
        self._best_sell: Dict[str, Tuple[str, Decimal, Decimal, Decimal]] = {}
        self._best_buy: Dict[str, Tuple[str, Decimal, Decimal, Decimal]] = {}

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Check if symbol is on cooldown"""
        last_signal = self._cooldowns.get(symbol, 0)
        return (time.time() - last_signal) < self.config.signal_cooldown_seconds

    def _set_cooldown(self, symbol: str) -> None:
        """Set cooldown for symbol"""
        self._cooldowns[symbol] = time.time()

    def _update_best_scores(
        self, symbol: str, exchange: str, quote: Quote, now_ms: int
    ) -> None:
        """Update incremental best-score tracking for a single exchange update"""
        # Update sell score (we sell at bid price, want highest score)
        sell_score = self.cost.compute_sell_score(quote.bid_px, exchange, symbol)
        cached_sell = self._best_sell.get(symbol)
        if cached_sell is None or sell_score > cached_sell[1]:
            self._best_sell[symbol] = (exchange, sell_score, quote.bid_px, quote.bid_sz)

        # Update buy score (we buy at ask price, want lowest score)
        buy_score = self.cost.compute_buy_score(quote.ask_px, exchange, symbol)
        cached_buy = self._best_buy.get(symbol)
        if cached_buy is None or buy_score < cached_buy[1]:
            self._best_buy[symbol] = (exchange, buy_score, quote.ask_px, quote.ask_sz)

    def _full_rescan(self, symbol: str, quotes: Dict[str, Quote], now_ms: int) -> None:
        """Full rescan of all exchanges for a symbol (when cached best is stale)"""
        best_sell: Optional[Tuple[str, Decimal, Decimal, Decimal]] = None
        best_buy: Optional[Tuple[str, Decimal, Decimal, Decimal]] = None

        for exchange, quote in quotes.items():
            sell_score = self.cost.compute_sell_score(quote.bid_px, exchange, symbol)
            if best_sell is None or sell_score > best_sell[1]:
                best_sell = (exchange, sell_score, quote.bid_px, quote.bid_sz)

            buy_score = self.cost.compute_buy_score(quote.ask_px, exchange, symbol)
            if best_buy is None or buy_score < best_buy[1]:
                best_buy = (exchange, buy_score, quote.ask_px, quote.ask_sz)

        if best_sell:
            self._best_sell[symbol] = best_sell
        if best_buy:
            self._best_buy[symbol] = best_buy

    async def evaluate(self, symbol: str, exchange: str = None) -> Optional[Signal]:
        """
        Evaluate arbitrage opportunity for a symbol.
        Called after each market update.

        Args:
            symbol: The symbol to evaluate
            exchange: The exchange that triggered this update (for incremental tracking)

        Returns Signal if opportunity found, None otherwise.
        """
        # Check cooldown
        if self._is_on_cooldown(symbol):
            return None

        # Cache timestamp once for this evaluation
        now_ms = int(time.time() * 1000)

        # Get all valid quotes for this symbol
        quotes = self.state.get_all_quotes(symbol, now_ms=now_ms)
        if len(quotes) < 2:
            return None  # Need at least 2 exchanges

        # Check if cached best exchanges are still in the valid quotes
        cached_sell = self._best_sell.get(symbol)
        cached_buy = self._best_buy.get(symbol)
        need_rescan = (
            cached_sell is None or cached_sell[0] not in quotes or
            cached_buy is None or cached_buy[0] not in quotes
        )

        if need_rescan:
            # Full rescan when cached best is stale/missing
            self._full_rescan(symbol, quotes, now_ms)
        elif exchange and exchange in quotes:
            # Incremental update for the exchange that changed
            self._update_best_scores(symbol, exchange, quotes[exchange], now_ms)

        # Get current best
        best_sell = self._best_sell.get(symbol)
        best_buy = self._best_buy.get(symbol)

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
            created_ts=now_ms,
        )

        # Set cooldown and emit (fire-and-forget to not block hot path)
        self._set_cooldown(symbol)
        self._emit_signal(signal)
        return signal

    def _emit_signal(self, signal: Signal) -> None:
        """Emit signal with error logging"""
        async def _run():
            try:
                await self.on_signal(signal)
            except Exception as e:
                print(f"[SIGNAL ERROR] {signal.symbol}: {e}")
        asyncio.create_task(_run())
