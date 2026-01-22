"""Hyperliquid exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.hyperliquid.perp.rest_client import HyperliquidPerpRestClient
from exchanges.hyperliquid.perp.ws_client import HyperliquidPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class HyperliquidAdapter(BaseExchangeAdapter):
    """Hyperliquid perpetual exchange adapter"""

    name = "hyperliquid"
    default_taker_fee = Decimal("0.00035")  # 0.035%
    default_maker_fee = Decimal("0.0001")   # 0.01%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://api.hyperliquid.xyz", signer=None)
        self.rest = HyperliquidPerpRestClient(http=self.http, signer=None)
        self.ws: Optional[HyperliquidPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._meta_cache = None
        self._ctx_cache = None

    async def _fetch_meta_and_ctxs(self):
        """Fetch meta and asset contexts (API returns list [meta, ctxs])"""
        response = await self.http.post("/info", json={"type": "metaAndAssetCtxs"})
        self._meta_cache = response[0]
        self._ctx_cache = response[1]
        return self._meta_cache, self._ctx_cache

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        meta = await self.rest.meta()
        symbols = []
        for asset in meta.universe:
            normalized = asset.name  # Hyperliquid uses "BTC", "ETH" directly
            self._symbol_map[normalized] = asset.name
            self._reverse_map[asset.name] = normalized
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        meta, ctxs = await self._fetch_meta_and_ctxs()
        results = []
        for asset, ctx in zip(meta.get("universe", []), ctxs):
            normalized = asset.get("name", "")
            if symbol and normalized != symbol:
                continue
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=asset.get("name", ""),
                base_asset=asset.get("name", ""),
                quote_asset="USD",
                price_decimals=8,
                size_decimals=asset.get("szDecimals", 4),
                is_active=True,
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        meta, ctxs = await self._fetch_meta_and_ctxs()
        exc_sym = self._symbol_map.get(symbol, symbol)
        for asset, ctx in zip(meta.get("universe", []), ctxs):
            if asset.get("name") == exc_sym:
                return FundingRate(
                    symbol=symbol,
                    funding_rate=Decimal(ctx.get("funding", "0")),
                    mark_price=Decimal(ctx.get("markPx", "0")),
                    index_price=Decimal(ctx.get("oraclePx", "0")),
                    timestamp=int(time.time() * 1000),
                )
        raise ValueError(f"Symbol {symbol} not found")

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
        """Subscribe to real-time L2 book data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return
            channel = data.get("channel")
            if channel != "l2Book":
                return

            book_data = data.get("data", {})
            coin = book_data.get("coin")
            if coin not in self._reverse_map:
                return

            levels = book_data.get("levels", [[], []])
            bids, asks = levels[0], levels[1]
            if not bids or not asks:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[coin],
                bid_px=Decimal(bids[0]["px"]),
                bid_sz=Decimal(bids[0]["sz"]),
                ask_px=Decimal(asks[0]["px"]),
                ask_sz=Decimal(asks[0]["sz"]),
                bid_levels=[PriceLevel(px=Decimal(l["px"]), sz=Decimal(l["sz"])) for l in bids[:5]],
                ask_levels=[PriceLevel(px=Decimal(l["px"]), sz=Decimal(l["sz"])) for l in asks[:5]],
                ts_exchange=book_data.get("time"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = HyperliquidPerpWsClient(on_message=handle_message)

        # Start connect in background, wait for ready, then subscribe
        import asyncio
        asyncio.create_task(self.ws.connect())
        # Wait for connection to establish (check ws.ws is set)
        for _ in range(50):  # 5 second timeout
            if self.ws.ws is not None:
                break
            await asyncio.sleep(0.1)
        for sym in symbols:
            exc_sym = self._symbol_map.get(sym, sym)
            await self.ws.subscribe_l2_book(exc_sym)

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
