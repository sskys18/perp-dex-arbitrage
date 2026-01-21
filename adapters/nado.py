"""Nado exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.nado.perp.rest_client import NadoPerpRestClient
from exchanges.nado.perp.ws_client import NadoPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


# Product ID to symbol mapping for Nado
NADO_PRODUCT_MAP = {
    1: "BTC",
    2: "ETH",
    3: "SOL",
    4: "ARB",
    5: "OP",
}
NADO_SYMBOL_TO_PRODUCT = {v: k for k, v in NADO_PRODUCT_MAP.items()}


class NadoAdapter(BaseExchangeAdapter):
    """Nado perpetual exchange adapter"""

    name = "nado"
    default_taker_fee = Decimal("0.0005")   # 0.05%
    default_maker_fee = Decimal("0.0002")   # 0.02%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://gateway.prod.nado.xyz", signer=None)
        self.rest = NadoPerpRestClient(http=self.http, signer=None)
        self.ws: Optional[NadoPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._products_cache: dict = {}
        self._product_id_map: dict = {}  # normalized -> product_id

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        # Fetch raw API response (has {status, data, request_type} wrapper)
        response = await self.http.get("/query", params={"type": "all_products"})
        data = response.get("data", {})
        perp_products = data.get("perp_products", [])

        symbols = []
        for product in perp_products:
            product_id = product.get("product_id")
            # Build mapping dynamically from API
            symbol_name = product.get("symbol", "")
            if symbol_name:
                normalized = symbol_name.replace("-PERP", "").replace("_PERP", "")
            elif product_id in NADO_PRODUCT_MAP:
                normalized = NADO_PRODUCT_MAP[product_id]
            else:
                continue

            self._symbol_map[normalized] = str(product_id)
            self._reverse_map[str(product_id)] = normalized
            self._product_id_map[normalized] = product_id
            self._products_cache[normalized] = product
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._products_cache:
            await self.list_symbols()

        results = []
        for normalized, product in self._products_cache.items():
            if symbol and normalized != symbol:
                continue
            # Product is now a dict from raw API
            product_id = product.get("product_id", 0) if isinstance(product, dict) else getattr(product, 'product_id', 0)
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=str(product_id),
                base_asset=normalized,
                quote_asset="USDT",
                price_decimals=6,
                size_decimals=6,
                is_active=True,
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        product_id = self._product_id_map.get(symbol)
        if not product_id:
            raise ValueError(f"Symbol {symbol} not found")

        # Fetch perp prices directly from API
        response = await self.http.get("/query", params={"type": "perp_prices", "product_id": product_id})
        data = response.get("data", {})

        # Nado uses x18 format (divide by 10^18)
        scale = Decimal("1000000000000000000")

        mark_price_x18 = data.get("mark_price_x18", "0")
        index_price_x18 = data.get("index_price_x18", "0")

        # Funding rate from product state
        funding_rate = Decimal("0")
        if self._products_cache.get(symbol):
            product = self._products_cache[symbol]
            state = product.get("state", {}) if isinstance(product, dict) else {}
            if state:
                funding_rate = Decimal(str(state.get("funding_rate_x18", "0"))) / scale

        return FundingRate(
            symbol=symbol,
            funding_rate=funding_rate,
            mark_price=Decimal(str(mark_price_x18)) / scale,
            index_price=Decimal(str(index_price_x18)) / scale,
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (default, requires subaccount for user-specific)"""
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
        scale = Decimal("1000000000000000000")

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            msg_type = data.get("type")
            if msg_type != "best_bid_offer":
                return

            stream = data.get("stream", {})
            product_id = stream.get("product_id")
            if not product_id or str(product_id) not in self._reverse_map:
                return

            bbo_data = data.get("data", {})
            bid_price = bbo_data.get("bid_price_x18")
            ask_price = bbo_data.get("ask_price_x18")
            if not bid_price or not ask_price:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[str(product_id)],
                bid_px=Decimal(str(bid_price)) / scale,
                bid_sz=Decimal(str(bbo_data.get("bid_qty_x18", "0"))) / scale,
                ask_px=Decimal(str(ask_price)) / scale,
                ask_sz=Decimal(str(bbo_data.get("ask_qty_x18", "0"))) / scale,
                ts_exchange=bbo_data.get("timestamp"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = NadoPerpWsClient(on_message=handle_message)

        async def on_connect():
            for sym in symbols:
                product_id = self._product_id_map.get(sym)
                if product_id:
                    await self.ws.subscribe_best_bid_offer(product_id)

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
