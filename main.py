"""Main entry point for perpetual arbitrage signal generator"""

# Apply compatibility shim before importing adapters
import compat  # noqa: F401

import asyncio
import sys
from collections import Counter
from decimal import Decimal
from typing import List

from config import ArbitrageConfig, DEFAULT_CONFIG
from models import FeeRates, MarketUpdate, Signal
from engines import StateEngine, CostEngine, ArbitrageEngine
from adapters import (
    BaseExchangeAdapter,
    HyperliquidAdapter,
    ParadexAdapter,
    BackpackAdapter,
    GrvtAdapter,
    NadoAdapter,
    ExtendedAdapter,
    PacificaAdapter,
    StandxAdapter,
)


def create_adapters() -> List[BaseExchangeAdapter]:
    """Create all exchange adapters"""
    # Note: GrvtAdapter skipped - requires authentication for public endpoints
    return [
        HyperliquidAdapter(),
        ParadexAdapter(),
        BackpackAdapter(),
        NadoAdapter(),
        ExtendedAdapter(),
        PacificaAdapter(),
        StandxAdapter(),
    ]


async def print_signal(signal: Signal) -> None:
    """Print signal to console"""
    print(f"\n{'='*60}")
    print(f"SIGNAL: {signal.symbol}")
    print(f"  ID: {signal.signal_id}")
    print(f"  SELL {signal.sell_exchange}: {signal.sell_price} ({signal.sell_score:.4f})")
    print(f"  BUY  {signal.buy_exchange}: {signal.buy_price} ({signal.buy_score:.4f})")
    print(f"  QTY: {signal.qty}")
    print(f"  EDGE: {signal.edge_absolute:.4f} USD ({signal.edge_bps:.2f} bps)")
    print(f"{'='*60}\n")


async def main():
    """Main entry point"""
    config = DEFAULT_CONFIG
    adapters = create_adapters()

    print("Perpetual DEX Arbitrage Signal Generator")
    print("=" * 50)

    # 1. Fetch symbols from all exchanges
    print("\n[1] Discovering symbols...")
    exchange_symbols = {}
    for adapter in adapters:
        try:
            symbols = await adapter.list_symbols()
            exchange_symbols[adapter.name] = set(symbols)
            print(f"  {adapter.name}: {len(symbols)} symbols - {symbols[:5]}...")
        except Exception as e:
            print(f"  {adapter.name}: FAILED - {e}")
            exchange_symbols[adapter.name] = set()

    # 2. Find common symbols (on 2+ exchanges)
    symbol_counts = Counter()
    for symbols in exchange_symbols.values():
        for sym in symbols:
            symbol_counts[sym] += 1

    tradeable = [s for s, c in symbol_counts.items() if c >= 2]
    print(f"\n  Tradeable symbols (on 2+ exchanges): {tradeable[:10]}...")
    print(f"  Total: {len(tradeable)} symbols")

    if not tradeable:
        print("\nNo tradeable symbols found. Exiting.")
        return

    # 3. Fetch fee rates
    print("\n[2] Loading fee rates...")
    fees = {}
    for adapter in adapters:
        try:
            fee_rates = await adapter.get_fee_rates()
            fees[adapter.name] = fee_rates
            print(f"  {adapter.name}: maker={fee_rates.maker_fee*100:.3f}%, taker={fee_rates.taker_fee*100:.3f}%")
        except Exception as e:
            fees[adapter.name] = FeeRates(
                maker_fee=adapter.default_maker_fee,
                taker_fee=adapter.default_taker_fee,
            )
            print(f"  {adapter.name}: using defaults (maker={adapter.default_maker_fee*100:.3f}%, taker={adapter.default_taker_fee*100:.3f}%)")

    # 4. Initialize engines
    print("\n[3] Initializing engines...")
    state_engine = StateEngine(max_quote_age_ms=config.max_quote_age_ms)
    cost_engine = CostEngine(fees)
    arb_engine = ArbitrageEngine(
        config=config,
        state_engine=state_engine,
        cost_engine=cost_engine,
        on_signal=print_signal,
    )

    # 5. Create update handler
    async def on_update(update: MarketUpdate) -> None:
        state_engine.update(update)
        await arb_engine.evaluate(update.symbol)

    # 6. Subscribe to market data
    print("\n[4] Subscribing to market data...")
    tasks = []
    for adapter in adapters:
        adapter_symbols = [s for s in tradeable if s in exchange_symbols.get(adapter.name, set())]
        if adapter_symbols:
            print(f"  {adapter.name}: subscribing to {len(adapter_symbols)} symbols")
            task = asyncio.create_task(
                adapter.subscribe_market_data(adapter_symbols, on_update)
            )
            tasks.append(task)

    if not tasks:
        print("\nNo subscriptions created. Exiting.")
        return

    print("\n[5] Running... Press Ctrl+C to stop\n")

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for adapter in adapters:
            try:
                await adapter.close()
            except:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)
