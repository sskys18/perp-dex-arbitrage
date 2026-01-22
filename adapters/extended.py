"""Extended exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.extended.perp.rest_client import ExtendedPerpRestClient
from core.ws.client import WsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


# Limit Extended to top 5 high-volume symbols (creates 1 WS per symbol)
EXTENDED_HIGH_VOLUME_SYMBOLS = {"BTC", "ETH", "SOL", "XRP", "DOGE"}


class ExtendedAdapter(BaseExchangeAdapter):
    """Extended perpetual exchange adapter"""

    name = "extended"
    default_taker_fee = Decimal("0.0004")   # 0.04%
    default_maker_fee = Decimal("0.0002")   # 0.02%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://api.starknet.extended.exchange/api/v1", signer=None)
        self.rest = ExtendedPerpRestClient(http=self.http, signer=None)
        self._ws_clients: list[WsClient] = []  # Multiple WS connections
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._markets_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from BTC-PERP format"""
        parts = exchange_symbol.split("-")
        return parts[0] if parts else exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        response = await self.rest.get_markets()
        # API returns {status, data} wrapper
        markets = response.get("data", []) if isinstance(response, dict) else response
        symbols = []
        for market in markets:
            exc_sym = market.get("name", "")
            if not exc_sym.endswith("-USD"):
                continue
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
            trading_config = market.get("tradingConfig", {})
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=market.get("name", ""),
                base_asset=market.get("assetName", normalized),
                quote_asset=market.get("collateralAssetName", "USD"),
                price_decimals=market.get("collateralAssetPrecision", 6),
                size_decimals=market.get("assetPrecision", 0),
                min_size=Decimal(str(trading_config.get("minOrderSize", "0"))) if trading_config.get("minOrderSize") else None,
                max_leverage=Decimal(str(trading_config.get("maxLeverage", "20"))) if trading_config.get("maxLeverage") else None,
                is_active=market.get("active", True),
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        if not self._markets_cache:
            await self.list_symbols()

        market = self._markets_cache.get(symbol)
        if not market:
            raise ValueError(f"No data for {symbol}")

        # Funding data is embedded in marketStats
        stats = market.get("marketStats", {})
        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal(str(stats.get("fundingRate", "0"))),
            mark_price=Decimal(str(stats.get("markPrice", "0"))) if stats.get("markPrice") else None,
            index_price=Decimal(str(stats.get("indexPrice", "0"))) if stats.get("indexPrice") else None,
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (default, requires auth for user-specific)"""
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time BBO data via URL-based streaming"""
        from exchanges.extended.perp.constants import WS_URL
        self._on_update = on_update

        def make_handler(symbol: str):
            async def handle_message(data):
                if not isinstance(data, dict):
                    return

                # Extended uses nested data with b/a for bids/asks
                inner = data.get("data", {})
                bids = inner.get("b", [])
                asks = inner.get("a", [])
                if not bids or not asks:
                    return

                # Format: {'p': '89713', 'q': '1.33419'}
                update = MarketUpdate(
                    exchange=self.name,
                    symbol=symbol,
                    bid_px=Decimal(str(bids[0]["p"])),
                    bid_sz=Decimal(str(bids[0]["q"])),
                    ask_px=Decimal(str(asks[0]["p"])),
                    ask_sz=Decimal(str(asks[0]["q"])),
                    ts_exchange=data.get("ts"),
                    ts_local=int(time.time() * 1000),
                )
                await self._on_update(update)
            return handle_message

        # Extended uses URL-based streaming - create one WS per symbol
        # Limit to high-volume symbols to reduce connection count
        import asyncio
        filtered_symbols = [s for s in symbols if s in EXTENDED_HIGH_VOLUME_SYMBOLS]
        if not filtered_symbols:
            filtered_symbols = symbols[:5]  # Fallback to first 5 if no matches

        tasks = []
        for symbol in filtered_symbols:
            exc_sym = self._symbol_map.get(symbol, f"{symbol}-USD")
            ws_url = f"{WS_URL}/orderbooks/{exc_sym}?depth=1"
            ws = WsClient(url=ws_url, on_message=make_handler(symbol))
            self._ws_clients.append(ws)
            tasks.append(asyncio.create_task(ws.connect()))

        await asyncio.gather(*tasks)

    async def close(self) -> None:
        """Close all connections"""
        for ws in self._ws_clients:
            await ws.close()
        await self.http.close()
