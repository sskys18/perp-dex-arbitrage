"""Normalized data models for cross-exchange arbitrage"""

from decimal import Decimal
from typing import Optional, List, Dict
from pydantic import BaseModel


class SymbolInfo(BaseModel):
    """Normalized symbol information"""
    symbol: str                     # Normalized: "BTC", "ETH"
    exchange_symbol: str            # Raw: "BTC-USD-PERP", "BTC_USDC", etc.
    base_asset: str                 # "BTC"
    quote_asset: str                # "USD", "USDC", "USDT"
    price_decimals: int             # e.g., 2 for $42000.50
    size_decimals: int              # e.g., 4 for 0.0001 BTC
    min_size: Optional[Decimal] = None
    max_size: Optional[Decimal] = None
    tick_size: Optional[Decimal] = None
    max_leverage: Optional[Decimal] = None
    is_active: bool = True


class FundingRate(BaseModel):
    """Normalized funding rate"""
    symbol: str                     # Normalized symbol
    funding_rate: Decimal           # Rate as decimal (0.0001 = 0.01%)
    mark_price: Optional[Decimal] = None
    index_price: Optional[Decimal] = None
    next_funding_time: Optional[int] = None  # Timestamp ms
    timestamp: int                  # Data timestamp ms


class FeeRates(BaseModel):
    """Normalized fee rates"""
    maker_fee: Decimal              # Maker fee as decimal (0.0002 = 0.02%)
    taker_fee: Decimal              # Taker fee as decimal
    symbol_fees: Optional[Dict[str, Dict[str, Decimal]]] = None


class PriceLevel(BaseModel):
    """Order book price level"""
    px: Decimal
    sz: Decimal


class MarketUpdate(BaseModel):
    """Normalized market data update"""
    exchange: str
    symbol: str                     # Normalized symbol
    bid_px: Decimal
    bid_sz: Decimal
    ask_px: Decimal
    ask_sz: Decimal
    bid_levels: Optional[List[PriceLevel]] = None
    ask_levels: Optional[List[PriceLevel]] = None
    ts_exchange: Optional[int] = None
    ts_local: int


class Signal(BaseModel):
    """Arbitrage signal"""
    signal_id: str
    symbol: str
    sell_exchange: str
    buy_exchange: str
    qty: Decimal
    sell_price: Decimal
    buy_price: Decimal
    sell_score: Decimal
    buy_score: Decimal
    edge_absolute: Decimal
    edge_bps: Decimal
    sell_fee: Decimal
    buy_fee: Decimal
    sell_funding: Decimal
    buy_funding: Decimal
    created_ts: int
