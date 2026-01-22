"""Pacifica exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.pacifica.perp.rest_client import PacificaPerpRestClient
from exchanges.pacifica.perp import PacificaPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class PacificaAdapter(BaseExchangeAdapter):
    """Pacifica perpetual exchange adapter"""

    name = "pacifica"
    default_taker_fee = Decimal("0.0002")    # 0.02%
    default_maker_fee = Decimal("0.000075")  # 0.0075%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://api.pacifica.fi/api/v1", signer=None)
        self.rest = PacificaPerpRestClient(http=self.http, signer=None)
        self.ws: Optional[PacificaPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._markets_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from symbol"""
        # Pacifica may use formats like "BTC-PERP" or "BTC"
        if "-" in exchange_symbol:
            return exchange_symbol.split("-")[0]
        return exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        response = await self.rest.get_markets()
        # API returns {success, data, error, code} wrapper
        if isinstance(response, dict):
            markets = response.get("data", [])
        else:
            markets = response

        symbols = []
        for market in markets:
            exc_sym = market.get("symbol", "")
            normalized = self._normalize_symbol(exc_sym)
            self._symbol_map[normalized] = exc_sym
            self._reverse_map[exc_sym] = normalized
            self._markets_cache[normalized] = market
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._markets_cache:
            await self.list_symbols()

        results = []
        for normalized, market in self._markets_cache.items():
            if symbol and normalized != symbol:
                continue
            # Count decimal places from tick_size
            tick_size = market.get("tick_size", "0.01")
            price_decimals = len(tick_size.split(".")[-1]) if "." in tick_size else 0
            lot_size = market.get("lot_size", "0.01")
            size_decimals = len(lot_size.split(".")[-1]) if "." in lot_size else 0

            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=market.get("symbol", ""),
                base_asset=normalized,
                quote_asset="USDC",
                price_decimals=price_decimals,
                size_decimals=size_decimals,
                min_size=Decimal(str(market.get("min_order_size", "0"))) if market.get("min_order_size") else None,
                max_leverage=Decimal(str(market.get("max_leverage", "20"))) if market.get("max_leverage") else None,
                is_active=True,
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        if not self._markets_cache:
            await self.list_symbols()

        market = self._markets_cache.get(symbol)
        if not market:
            raise ValueError(f"No data for {symbol}")

        # Funding rate is embedded in market info
        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal(str(market.get("funding_rate", "0"))),
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (fixed, no public API)"""
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time BBO data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            channel = data.get("channel", "")
            if channel != "bbo":
                return

            bbo_data = data.get("data", {})
            symbol = bbo_data.get("s", "")
            if symbol not in self._symbol_map:
                return

            # Format: s=symbol, b=bid, B=bid_size, a=ask, A=ask_size, t=timestamp
            bid_px = bbo_data.get("b")
            bid_sz = bbo_data.get("B")
            ask_px = bbo_data.get("a")
            ask_sz = bbo_data.get("A")
            if not bid_px or not ask_px:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=symbol,
                bid_px=Decimal(str(bid_px)),
                bid_sz=Decimal(str(bid_sz or "0")),
                ask_px=Decimal(str(ask_px)),
                ask_sz=Decimal(str(ask_sz or "0")),
                ts_exchange=bbo_data.get("t"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = PacificaPerpWsClient(on_message=handle_message)

        # Start connect in background, wait for ready, then subscribe
        import asyncio
        asyncio.create_task(self.ws.connect())
        for _ in range(50):  # 5 second timeout
            if self.ws.ws is not None:
                break
            await asyncio.sleep(0.1)
        for sym in symbols:
            await self.ws.subscribe_bbo(sym)

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
