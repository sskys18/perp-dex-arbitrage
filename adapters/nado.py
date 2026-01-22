"""Nado exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.nado.perp.rest_client import NadoPerpRestClient
from exchanges.nado.perp.ws_client import NadoPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


# Product ID to symbol mapping for Nado (perp products have even IDs)
NADO_PRODUCT_MAP = {
    2: "BTC",
    4: "ETH",
    8: "SOL",
    10: "XRP",
    14: "BNB",
    16: "LINK",
    18: "BCH",
    20: "DOGE",
    22: "XLM",
    24: "NEAR",
    26: "LTC",
    28: "TON",
    30: "SHIB",
    32: "APT",
    34: "SUI",
    36: "ARB",
    38: "PEPE",
    40: "BONK",
    42: "WIF",
}
NADO_SYMBOL_TO_PRODUCT = {v: k for k, v in NADO_PRODUCT_MAP.items()}


class NadoAdapter(BaseExchangeAdapter):
    """Nado perpetual exchange adapter"""

    name = "nado"
    default_taker_fee = Decimal("0.0005")   # 0.05%
    default_maker_fee = Decimal("0.0002")   # 0.02%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://gateway.prod.nado.xyz/v2", signer=None)
        self.rest = NadoPerpRestClient(http=self.http, signer=None)
        self.ws: Optional[NadoPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._assets_cache: dict = {}
        self._product_id_map: dict = {}  # normalized -> product_id

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols from /assets endpoint"""
        response = await self.http.get("/assets")
        assets = response if isinstance(response, list) else response.get("data", [])

        symbols = []
        for asset in assets:
            # Only include perp markets
            if asset.get("market_type") != "perp":
                continue

            product_id = asset.get("product_id")
            symbol_name = asset.get("symbol", "")  # e.g. "BTC-PERP"
            if symbol_name:
                normalized = symbol_name.replace("-PERP", "").replace("_PERP", "")
            elif product_id in NADO_PRODUCT_MAP:
                normalized = NADO_PRODUCT_MAP[product_id]
            else:
                continue

            self._symbol_map[normalized] = str(product_id)
            self._reverse_map[str(product_id)] = normalized
            self._product_id_map[normalized] = product_id
            self._assets_cache[normalized] = asset
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._assets_cache:
            await self.list_symbols()

        results = []
        for normalized, asset in self._assets_cache.items():
            if symbol and normalized != symbol:
                continue
            product_id = asset.get("product_id", 0)
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=asset.get("ticker_id", str(product_id)),
                base_asset=normalized,
                quote_asset="USDT",
                price_decimals=6,
                size_decimals=6,
                is_active=True,
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        if not self._assets_cache:
            await self.list_symbols()

        asset = self._assets_cache.get(symbol)
        if not asset:
            raise ValueError(f"Symbol {symbol} not found")

        # Assets endpoint doesn't have funding data, return placeholder
        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal("0"),
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates from assets endpoint"""
        if not self._assets_cache:
            await self.list_symbols()

        # Use first asset's fees if available
        for asset in self._assets_cache.values():
            maker = asset.get("maker_fee")
            taker = asset.get("taker_fee")
            if maker is not None or taker is not None:
                return FeeRates(
                    maker_fee=Decimal(str(maker)) if maker else self.default_maker_fee,
                    taker_fee=Decimal(str(taker)) if taker else self.default_taker_fee,
                )
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

            product_id = data.get("product_id")
            if not product_id or str(product_id) not in self._reverse_map:
                return

            bid_price = data.get("bid_price")
            ask_price = data.get("ask_price")
            if not bid_price or not ask_price:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[str(product_id)],
                bid_px=Decimal(str(bid_price)) / scale,
                bid_sz=Decimal(str(data.get("bid_qty", "0"))) / scale,
                ask_px=Decimal(str(ask_price)) / scale,
                ask_sz=Decimal(str(data.get("ask_qty", "0"))) / scale,
                ts_exchange=data.get("timestamp"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = NadoPerpWsClient(on_message=handle_message)

        # Start connect in background, wait for ready, then subscribe
        import asyncio
        asyncio.create_task(self.ws.connect())
        for _ in range(50):  # 5 second timeout
            if self.ws.ws is not None:
                break
            await asyncio.sleep(0.1)
        for sym in symbols:
            product_id = self._product_id_map.get(sym)
            if product_id:
                await self.ws.subscribe_best_bid_offer(product_id)

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
