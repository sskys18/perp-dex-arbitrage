"""Test WebSocket connectivity for each exchange independently"""
import asyncio
from adapters import (
    HyperliquidAdapter, ParadexAdapter, BackpackAdapter,
    NadoAdapter, ExtendedAdapter, PacificaAdapter, StandxAdapter
)

TEST_SYMBOLS = ["BTC", "ETH"]
TIMEOUT = 15  # seconds per exchange

async def test_exchange(adapter_class):
    name = adapter_class.__name__.replace("Adapter", "").lower()
    print(f"\n{'='*50}")
    print(f"Testing: {name}")
    print(f"{'='*50}")

    adapter = adapter_class()
    messages = []

    async def on_update(update):
        messages.append(update)
        print(f"  [{name}] {update.symbol}: bid={update.bid_px} ask={update.ask_px}")

    try:
        # 1. Test symbol discovery
        symbols = await adapter.list_symbols()
        print(f"  Symbols: {len(symbols)} found")

        # 2. Filter test symbols
        test_syms = [s for s in TEST_SYMBOLS if s in symbols]
        if not test_syms:
            print(f"  SKIP: No matching symbols")
            return name, "no_symbols", 0

        print(f"  Subscribing to: {test_syms}")

        # 3. Subscribe with timeout
        task = asyncio.create_task(adapter.subscribe_market_data(test_syms, on_update))
        await asyncio.sleep(TIMEOUT)
        task.cancel()

    except Exception as e:
        print(f"  ERROR: {e}")
        return name, "error", 0
    finally:
        await adapter.close()

    status = "ok" if messages else "no_data"
    print(f"  Result: {len(messages)} messages received")
    return name, status, len(messages)

async def main():
    adapters = [
        HyperliquidAdapter,
        ParadexAdapter,
        BackpackAdapter,
        NadoAdapter,
        ExtendedAdapter,
        PacificaAdapter,
        StandxAdapter,
    ]

    results = []
    for adapter_class in adapters:
        result = await test_exchange(adapter_class)
        results.append(result)

    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    for name, status, count in results:
        icon = "✓" if status == "ok" else "✗"
        print(f"  {icon} {name}: {status} ({count} msgs)")

if __name__ == "__main__":
    asyncio.run(main())
