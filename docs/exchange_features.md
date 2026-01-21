# Perp Exchange Feature Matrix Report

**Generated:** 2026-01-20

## Summary

| Feature | Supported | Total | Rate |
|---------|-----------|-------|------|
| list_symbols | 8 | 8 | 100% |
| get_symbol_info | 8 | 8 | 100% |
| get_funding_rate | 8 | 8 | 100% |
| get_fee_rates | 4 | 8 | 50% |
| subscribe_bbo_or_l2 | 8 | 8 | 100% |

## Feature Matrix

| Exchange | list_symbols | get_symbol_info | get_funding_rate | get_fee_rates | subscribe_bbo_or_l2 |
|----------|:------------:|:---------------:|:----------------:|:-------------:|:-------------------:|
| hyperliquid/perp | ✅ `meta` | ✅ `meta` | ✅ `funding_history` | ✅ `user_fees` | ✅ `subscribe_l2_book` |
| grvt/perp | ✅ `get_all_instruments` | ✅ `get_instrument` | ✅ `get_funding_rate` | ❌ | ✅ `subscribe_mini_book` |
| nado/perp | ✅ `get_contracts` | ✅ `get_contracts` | ✅ `get_contracts` | ✅ `get_fee_rates` | ✅ `subscribe_best_bid_offer` |
| extended/perp | ✅ `get_markets` | ✅ `get_markets` | ✅ `get_funding_rates` | ✅ `get_fees` | ✅ `subscribe_bbo` |
| paradex/perp | ✅ `get_markets` | ✅ `get_markets` | ✅ `get_markets_summary` | ✅ `get_account` | ✅ `subscribe_bbo` |
| pacifica/perp | ✅ `get_markets` | ✅ `get_markets` | ✅ `get_funding` | ❌ | ✅ `subscribe_bbo` |
| standx/perp | ✅ `list_symbols` | ✅ `query_symbol_info` | ✅ `query_symbol_market` | ❌ | ✅ `subscribe_depth_book` |
| backpack/perp | ✅ `get_markets` | ✅ `get_markets` | ✅ `get_mark_prices` | ❌ | ✅ `subscribe_depth` |

---

## API Reference by Exchange

### Hyperliquid

**Base URL:** `https://api.hyperliquid.xyz`

#### list_symbols: `meta()`

- **Method:** POST `/info`
- **Request:**

```json
{"type": "meta"}
```

- **Response:** `Meta`

```python
class AssetInfo(BaseModel):
    name: str
    szDecimals: int

class Meta(BaseModel):
    universe: List[AssetInfo]
```

#### get_symbol_info: `meta_and_asset_ctxs()`

- **Method:** POST `/info`
- **Request:**

```json
{"type": "metaAndAssetCtxs"}
```

- **Response:** `MetaAndAssetCtxs`

```python
class PerpAssetCtx(BaseModel):
    dayNtlVlm: str
    funding: str
    impactPxs: Optional[List[str]]
    markPx: str
    midPx: Optional[str]
    openInterest: str
    oraclePx: str
    premium: Optional[str]
    prevDayPx: str

class MetaAndAssetCtxs(BaseModel):
    meta: Meta
    assetCtxs: List[PerpAssetCtx]
```

#### get_funding_rate: `funding_history()`

- **Method:** POST `/info`
- **Request:**

```json
{"type": "fundingHistory", "coin": "BTC", "startTime": 1704067200000}
```

- **Parameters:**
  - `coin` (str): Coin name
  - `start_time` (int): Start timestamp in ms
  - `end_time` (int, optional): End timestamp in ms
- **Response:** `List[FundingHistory]`

```python
class FundingHistory(BaseModel):
    coin: str
    fundingRate: str
    premium: str
    time: int
```

#### get_fee_rates: `user_fees()`

- **Method:** POST `/info`
- **Request:**

```json
{"type": "userFees", "user": "0x..."}
```

- **Parameters:**
  - `address` (str): User wallet address
- **Response:** `UserFees`

```python
class UserFees(BaseModel):
    userCrossRate: str
    userRate: str
    userAddRate: str
    userWithdrawRate: str
    userStakingRate: str
```

---

### Grvt

**Base URL:** `https://edge.grvt.io`

#### list_symbols: `get_all_instruments()`

- **Method:** POST `/full/v1/all_instruments`
- **Request:**

```json
{"is_active": false}
```

- **Parameters:**
  - `is_active` (bool): Filter active instruments only
- **Response:** `Dict[str, Any]` (contains list of instruments)

#### get_symbol_info: `get_instrument()`

- **Method:** POST `/full/v1/instrument`
- **Request:**

```json
{"instrument": "BTC_USDT_PERP"}
```

- **Parameters:**
  - `instrument` (str): Instrument name
- **Response:** `Dict[str, Any]`

#### get_funding_rate: `get_funding_rate()`

- **Method:** POST `/full/v1/funding`
- **Request:**

```json
{
  "instrument": "BTC_USDT_PERP",
  "limit": 500,
  "cursor": "",
  "agg_type": "FUNDING_INTERVAL"
}
```

- **Parameters:**
  - `instrument` (str): Instrument name
  - `start_time` (str, optional): Start time
  - `end_time` (str, optional): End time
  - `limit` (int): Number of records (default 500)
  - `cursor` (str): Pagination cursor
  - `agg_type` (str): Aggregation type (default "FUNDING_INTERVAL")
- **Response:** `Dict[str, Any]`

#### get_fee_rates

- **Status:** ❌ Not implemented
- **Fixed Fees:** Maker: -0.0001%, Taker: 0.045%

---

### Nado

**Base URL:** `https://gateway.prod.nado.xyz`

#### list_symbols: `get_all_products()`

- **Method:** GET `/query?type=all_products`
- **Request:** Query params
- **Response:** `AllProducts`

```python
class PerpProduct(BaseModel):
    product_id: int
    oracle_price_x18: str
    risk: Dict[str, Any]
    state: Dict[str, Any]
    config: Dict[str, Any]
    lp_state: Optional[Dict[str, Any]]

class AllProducts(BaseModel):
    spot_products: List[SpotProduct]
    perp_products: List[PerpProduct]
```

#### get_symbol_info: `get_all_products()`

- Same as list_symbols - symbol info included in product data

#### get_funding_rate: `get_perp_prices()`

- **Method:** GET `/query?type=perp_prices&product_id=X`
- **Parameters:**
  - `product_id` (int): Product ID
- **Response:** `PerpPrices`

```python
class PerpPrices(BaseModel):
    product_id: int
    index_price_x18: str
    mark_price_x18: str
```

#### get_fee_rates: `get_fee_rates()`

- **Method:** GET `/query?type=fee_rates&sender=X`
- **Parameters:**
  - `subaccount` (str): Subaccount hex string
- **Response:** `FeeRates`

```python
class FeeRates(BaseModel):
    maker_fee_rate_x18: str
    taker_fee_rate_x18: str
    withdraw_sequencer_fee: str
```

---

### Extended

**Base URL:** `https://api.starknet.extended.exchange/api/v1`

#### list_symbols: `get_markets()`

- **Method:** GET `/info/markets`
- **Response:** `List[Dict]` containing market info

#### get_symbol_info: `get_markets()`

- Same as list_symbols

#### get_funding_rate: `get_funding_rates()`

- **Method:** GET `/info/{market}/funding`
- **Parameters:**
  - `market` (str): Market symbol (e.g., "BTC-PERP")
  - `start_time` (int, optional): Start timestamp in ms
  - `end_time` (int, optional): End timestamp in ms
- **Response:** `List[Dict]`

#### get_fee_rates: `get_fees()`

- **Method:** GET `/user/fees`
- **Auth Required:** Yes
- **Response:** `Dict` with maker_rate, taker_rate, tier

---
r

### Paradex

**Base URL:** `https://api.prod.paradex.trade/v1`

#### list_symbols: `get_markets()`

- **Method:** GET `/markets`
- **Response:** `List[Dict]` containing market info

```json
[
  {
    "symbol": "BTC-USD-PERP",
    "base_currency": "BTC",
    "quote_currency": "USD",
    ...
  }
]
```

#### get_symbol_info: `get_markets()`

- Same as list_symbols

#### get_funding_rate: `get_funding_data()`

- **Method:** GET `/funding/data`
- **Parameters:**
  - `market` (str, optional): Market symbol to filter
- **Response:** `List[Dict]`

```json
[
  {
    "market": "BTC-USD-PERP",
    "funding_rate": "0.0001",
    "timestamp": 1704067200
  }
]
```

#### get_fee_rates: `get_account()`

- **Method:** GET `/account`
- **Auth Required:** Yes
- **Response:** Contains fee info in account data

---

### Pacifica

**Base URL:** `https://api.pacifica.fi`

#### list_symbols: `get_markets()`

- **Method:** GET `/markets`
- **Response:** `List[Dict]` containing market info

#### get_symbol_info: `get_markets()`

- Same as list_symbols

#### get_funding_rate: `get_funding()`

- **Method:** GET `/funding`
- **Parameters:**
  - `market` (str): Market symbol
  - `start_time` (int, optional): Start timestamp in ms
  - `end_time` (int, optional): End timestamp in ms
  - `limit` (int, optional): Number of records
- **Response:** `List[Dict]`

#### get_fee_rates

- **Status:** ❌ Not implemented
- **Fixed Fees:** Maker: 0.0075%, Taker: 0.020%

---

### StandX

**Base URL:** `https://perps.standx.com`

#### list_symbols: `list_symbols()`

- **Method:** Hardcoded
- **Response:** `["BTC-USD", "ETH-USD"]`

#### get_symbol_info: `query_symbol_info()`

- **Method:** GET `/api/query_symbol_info`
- **Parameters:**
  - `symbol` (str, optional): Symbol name
- **Response:** `List[SymbolInfo]`

```python
class SymbolInfo(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    base_decimals: int
    quote_decimals: int
    price_tick_decimals: int
    qty_tick_decimals: int
    min_order_qty: str
    max_order_qty: str
    max_position_size: str
    max_open_orders: str
    def_leverage: str
    max_leverage: str
    maker_fee: str
    taker_fee: str
    depth_ticks: str
    price_cap_ratio: str
    price_floor_ratio: str
    status: str
    created_at: str
    updated_at: str
```

#### get_funding_rate: `query_funding_rates()`

- **Method:** GET `/api/query_funding_rates`
- **Parameters:**
  - `symbol` (str): Symbol name
  - `start_time` (int): Start timestamp (required)
  - `end_time` (int): End timestamp (required)
- **Response:** `List[FundingRate]`

```python
class FundingRate(BaseModel):
    id: int
    symbol: str
    funding_rate: str
    index_price: str
    mark_price: str
    premium: str
    time: int
    created_at: str
    updated_at: str
```

#### get_fee_rates

- **Status:** ❌ No dedicated API
- **Source:** Available in `SymbolInfo.maker_fee` and `SymbolInfo.taker_fee`
- **Fixed Fees:** Maker: 0.01%, Taker: 0.04%

---

### Backpack

**Base URL:** `https://api.backpack.exchange`

#### list_symbols: `get_markets()`

- **Method:** GET `/api/v1/markets`
- **Response:** `List[Market]`

```python
class Market(BaseModel):
    symbol: str
    baseSymbol: str
    quoteSymbol: str
    filters: Optional[dict]
```

#### get_symbol_info: `get_markets()`

- Same as list_symbols

#### get_funding_rate: `get_mark_prices()`

- **Method:** GET `/api/v1/markPrices`
- **Response:** `List[MarkPrice]`

```python
class MarkPrice(BaseModel):
    symbol: str
    markPrice: str
    indexPrice: Optional[str]
    estimatedFundingRate: Optional[str]
    nextFundingTime: Optional[int]
```

#### get_fee_rates

- **Status:** ❌ Not implemented
- **Fixed Fees:** Maker: 0.02%, Taker: 0.05%

---

## Notes

- ✅ indicates the method exists in the adapter code
- ❌ indicates the method is not implemented or fees are fixed/tier-based

### Fee Rate Sources

| Exchange | Fee API | Fixed Fees |
|----------|---------|------------|
| hyperliquid | `user_fees` | - |
| grvt | ❌ | Maker: -0.0001%, Taker: 0.045% |
| nado | `get_fee_rates` | - |
| extended | `get_fees` | - |
| paradex | `get_account` | - |
| pacifica | ❌ | Maker: 0.0075%, Taker: 0.020% |
| standx | ❌ | Maker: 0.01%, Taker: 0.04% |
| backpack | ❌ | Maker: 0.02%, Taker: 0.05% |

### Request Pattern Summary

| Exchange | Style | Auth |
|----------|-------|------|
| hyperliquid | RPC-style POST with `type` | EIP-712 |
| grvt | POST with JSON body | API Key |
| nado | RPC-style GET with `type` | EIP-712 |
| extended | RESTful | Starknet |
| paradex | RESTful | Starknet/JWT |
| pacifica | RESTful | Solana |
| standx | RESTful | Custom |
| backpack | RESTful | Solana |
