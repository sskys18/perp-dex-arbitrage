"""Pacifica exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.pacifica.perp.rest_client import PacificaPerpRestClient
from core.ws.client import WsClient

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
        self.ws: Optional[WsClient] = None
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
            if not channel.startswith("bbo."):
                return

            exc_sym = channel.replace("bbo.", "")
            if exc_sym not in self._reverse_map:
                return

            bbo_data = data.get("data", {})
            bid = bbo_data.get("bid", {})
            ask = bbo_data.get("ask", {})
            if not bid or not ask:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[exc_sym],
                bid_px=Decimal(str(bid.get("price", "0"))),
                bid_sz=Decimal(str(bid.get("size", "0"))),
                ask_px=Decimal(str(ask.get("price", "0"))),
                ask_sz=Decimal(str(ask.get("size", "0"))),
                ts_exchange=bbo_data.get("timestamp"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = WsClient(
            url="wss://api.pacifica.fi/ws",
            on_message=handle_message
        )

        async def on_connect():
            for sym in symbols:
                exc_sym = self._symbol_map.get(sym, sym)
                await self.ws.send({
                    "type": "subscribe",
                    "channel": f"bbo.{exc_sym}"
                })

        import asyncio
        connect_task = asyncio.create_task(self.ws.connect())
        await asyncio.sleep(1)
        await on_connect()
        await connect_task

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
