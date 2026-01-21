# Real-Time Perp Arbitrage Signal Generator — Prompt (Signal Only)

Build a real-time **perpetual futures arbitrage signal generator** that connects to multiple exchanges via WebSocket, aggregates BBO/L2 data, and emits **immutable arbitrage signals** when a profitability condition (fees + funding included) is satisfied.

This version must **ONLY generate signals**.  
Do **NOT** implement paper execution, DB persistence, or Telegram notifications yet.

---

## 0) Goal

1. Subscribe to live market data from multiple perp exchanges (BBO or L2 book).
2. Normalize all venue updates into a unified representation.
3. Maintain an in-memory global market state.
4. Compute cross-exchange arbitrage opportunities using **executable prices**.
5. Emit a **Signal** event when the opportunity is profitable and stable.

---

## 1) Core Profitability Condition (Difference Form)

For selling on exchange **A** and buying on exchange **B**, generate a signal when:

\[
S_{exec}\cdot(1-f_A)-funding_A \;>\; B_{exec}\cdot(1+f_B)+funding_B
\]

Where:

- \(S_{exec}\): SELL executable price on exchange A (from bid-side liquidity)
- \(B_{exec}\): BUY executable price on exchange B (from ask-side liquidity)
- \(f_A\), \(f_B\): fee rates (default: taker)
- \(funding_A\), \(funding_B\): expected funding cost per unit for holding horizon **T**
  - If funding is a benefit, treat as negative cost.

**Important:** use the difference form (no division) for speed and thresholding.

---

## 2) Engine Separation (Signal Only)

Implement the signal generator with strict responsibility separation.  
No engine may do side effects (DB/network alerts). Only compute and emit signals.

### A) Market Data Engine (MDE)

**Purpose:** WebSocket connections + parsing minimal market fields.

**Inputs:**

- Exchange WebSocket feeds

**Outputs:**

- `MarketUpdate` events

**Must own:**

- connect/reconnect/resubscribe
- exchange-specific parsing (only needed fields)

**Must NOT:**

- compute arbitrage
- store anything durable
- call external services

**Exchange features used:**

- WebSocket market data:
  - BBO stream OR
  - L2 orderbook stream (preferred)

---

### B) State Engine (SE)

**Purpose:** Store latest market state in memory for constant-time lookup.

**Inputs:**

- `MarketUpdate`

**Outputs:**

- updated `MarketState` (in-memory)

**State structure:**

```

state[symbol][exchange] = {
bid_px, bid_sz,
ask_px, ask_sz,
(optional) bid_levels[], ask_levels[],
ts_exchange, ts_local
}

```

**Must own:**

- overwrite-only updates
- staleness tracking

**Must NOT:**

- compute strategy decisions beyond state upkeep

---

### C) Pricing Engine (PE)

**Purpose:** Convert quotes into **executable** prices.

**Inputs:**

- `MarketState` snapshot for (symbol, exchange)
- target order size `q`
- pricing model selection

**Outputs:**

- `ExecQuote(exchange, symbol, side, exec_price, available_qty, model_meta)`

**Pricing models:**

1. **Fast model (Top-of-book)**
   - SELL uses best bid
   - BUY uses best ask
2. **Optional model (VWAP_N / depth-aware)**
   - Consume top N levels for realistic fill price

**Must NOT:**

- decide whether to trade
- do I/O

**Exchange features used:**

- WS L2 book (preferred)
- fallback to BBO

---

### D) Cost Engine (CE)

**Purpose:** Apply fee + funding cost assumptions with cached parameters.

**Inputs:**

- `ExecQuote` for both legs
- cached fee rates
- cached funding rates

**Outputs:**

- net sell proceeds per unit
- net buy cost per unit

**Definitions:**

- `SellNet(A) = S_exec*(1 - f_A) - funding_A`
- `BuyNet(B)  = B_exec*(1 + f_B) + funding_B`

**Must own:**

- fee cache (default taker)
- funding cache for holding horizon T
- periodic refresh (NOT per tick)

**Must NOT:**

- query REST on every tick
- do strategy selection

---

### E) Arbitrage Decision Engine (ADE)

**Purpose:** Select the best cross-exchange pair and emit signals.

**Inputs:**

- `MarketState`
- executable prices from PE
- costs from CE
- staleness + dedupe policies

**Outputs:**

- immutable `Signal` objects

#### Candidate Selection (Must use net economics, not raw bid/ask)

Define per exchange `e`:

\[
SellScore(e)=S_{exec}(e)\cdot(1-f_e)-funding_e
\]
\[
BuyScore(e)=B_{exec}(e)\cdot(1+f_e)+funding_e
\]

Select:

- `A = argmax SellScore(e)` (best net sell)
- `B = argmin BuyScore(e)` (best net buy)
subject to A ≠ B

Emit signal if:
\[
SellScore(A) > BuyScore(B)
\]

**Must also include:**

- **Staleness guard**: reject if either quote is older than X ms
- **Confirmation**: require K consecutive passes before emitting (optional but recommended)
- **Cooldown**: per (symbol, A, B) to prevent spam

**Must NOT:**

- write DB
- send Telegram
- block on I/O

---

## 3) Data Contracts (Signal-Only)

### MarketUpdate

- exchange
- symbol
- local_ts
- bid_px, bid_sz
- ask_px, ask_sz
- optional: bid_levels[], ask_levels[] (top N)

### ExecQuote

- exchange
- symbol
- side (BUY/SELL)
- exec_price
- available_qty
- model_meta (BBO / VWAP_N)
- quote_ts

### Signal (Immutable)

- signal_id
- symbol
- buy_exchange (B)
- sell_exchange (A)
- qty (or recommended qty)
- B_exec, S_exec
- SellScore(A), BuyScore(B)
- expected_edge (price units + bps)
- fees used, funding used
- created_ts

---

## 4) Full Runtime Flow (Signal Only)

### Hot Path (must be ultra-fast)

1. MDE receives WS update -> emits `MarketUpdate`
2. SE updates `MarketState` in O(1)
3. ADE evaluates opportunity:
   - compute/update SellScore & BuyScore (incremental)
   - pick A (best sell) and B (best buy)
   - apply staleness rules
   - apply profitability inequality
4. If conditions pass -> emit `Signal`

---

## 5) Execution-Speed Optimization Requirements

### A) Two-Stage Evaluation (Required)

- **Stage 1 (cheap):** Top-of-book executable prices + fees + cached funding
- **Stage 2 (optional):** VWAP_N only if Stage 1 is near profitability threshold

### B) Incremental Best-Score Maintenance

Maintain per symbol:

- `best_sell_exchange_by_SellScore`
- `best_buy_exchange_by_BuyScore`

Update only the exchange that changed rather than scanning all exchanges.

### C) Staleness Filtering

Reject candidates when:

- `now - quote_ts > X ms` for either leg

### D) Deduping / Cooldown

Prevent repeated signals when edge oscillates:

- cooldown per pair (symbol, A, B)
- optional hysteresis threshold

---

## 6) Constraints (What NOT to build yet)

Do NOT implement:

- Paper trading / execution simulation
- Database persistence
- Telegram notifications
- Order execution

Only emit signals cleanly and consistently.

---

## Deliverable

A signal-generation engine that:

- aggregates BBO/L2 from multiple exchanges
- computes executable cross-exchange profitability with fees + funding
- emits immutable `Signal` events with stable interfaces
- is optimized for low latency and future extensibility
