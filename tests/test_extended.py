"""Tests for Extended exchange adapter"""

import asyncio
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.extended import ExtendedAdapter


async def test_list_symbols():
    """Test fetching available symbols with detailed logging"""
    adapter = ExtendedAdapter()
    try:
        symbols = await adapter.list_symbols()
        print(f"\n[list_symbols] Found {len(symbols)} symbols:")
        for sym in symbols[:10]:
            exc_sym = adapter._symbol_map.get(sym)
            print(f"  {sym} -> {exc_sym}")
        print(f"\nReverse map sample: {dict(list(adapter._reverse_map.items())[:5])}")
    finally:
        await adapter.close()


async def test_get_symbol_info():
    """Test fetching symbol info"""
    adapter = ExtendedAdapter()
    try:
        await adapter.list_symbols()
        infos = await adapter.get_symbol_info()
        print(f"\n[get_symbol_info] Got info for {len(infos)} symbols:")
        for info in infos[:5]:
            print(f"  {info.symbol}: exchange={info.exchange_symbol}, base={info.base_asset}, quote={info.quote_asset}")
    finally:
        await adapter.close()


async def test_get_funding_rate():
    """Test fetching funding rate"""
    adapter = ExtendedAdapter()
    try:
        symbols = await adapter.list_symbols()
        if "BTC" in symbols:
            symbol = "BTC"
        else:
            symbol = symbols[0]
        funding = await adapter.get_funding_rate(symbol)
        print(f"\n[get_funding_rate] {symbol}:")
        print(f"  funding_rate: {funding.funding_rate}")
        print(f"  mark_price: {funding.mark_price}")
        print(f"  index_price: {funding.index_price}")
    finally:
        await adapter.close()


async def test_get_fee_rates():
    """Test fetching fee rates"""
    adapter = ExtendedAdapter()
    try:
        fees = await adapter.get_fee_rates()
        print(f"\n[get_fee_rates]")
        print(f"  maker: {fees.maker_fee} ({float(fees.maker_fee)*100:.4f}%)")
        print(f"  taker: {fees.taker_fee} ({float(fees.taker_fee)*100:.4f}%)")
    finally:
        await adapter.close()


async def test_websocket():
    """Test websocket subscription with detailed raw message logging"""
    adapter = ExtendedAdapter()
    messages_received = []

    try:
        symbols = await adapter.list_symbols()
        test_symbols = ["BTC", "ETH", "SOL"] if "BTC" in symbols else symbols[:3]

        print(f"\n[websocket] Testing symbols: {test_symbols}")
        print(f"Exchange symbol mapping:")
        for sym in test_symbols:
            exc_sym = adapter._symbol_map.get(sym)
            print(f"  {sym} -> {exc_sym}")

        async def on_update(update):
            messages_received.append(update)
            print(f"\n[WS UPDATE] {update.symbol} ({update.exchange})")
            print(f"  bid: {update.bid_px} x {update.bid_sz}")
            print(f"  ask: {update.ask_px} x {update.ask_sz}")

        async def patched_subscribe(syms, callback):
            async def handle_message_with_log(data):
                print(f"\n[RAW MESSAGE] {str(data)[:500]}")

                if not isinstance(data, dict):
                    return

                # Extended uses nested data with b/a for bids/asks
                inner = data.get("data", {})
                bids = inner.get("b", [])
                asks = inner.get("a", [])
                print(f"  bids: {bids[:2] if bids else []}")
                print(f"  asks: {asks[:2] if asks else []}")

                if not bids or not asks:
                    print(f"  Skipping: missing bids or asks")
                    return

                try:
                    from models import MarketUpdate
                    # Format: {'p': '89713', 'q': '1.33419'}
                    update = MarketUpdate(
                        exchange=adapter.name,
                        symbol="BTC",  # URL-based, single symbol
                        bid_px=Decimal(str(bids[0]["p"])),
                        bid_sz=Decimal(str(bids[0]["q"])),
                        ask_px=Decimal(str(asks[0]["p"])),
                        ask_sz=Decimal(str(asks[0]["q"])),
                        ts_exchange=data.get("ts"),
                        ts_local=0,
                    )
                    await callback(update)
                except Exception as e:
                    print(f"  ERROR creating update: {e}")

            from core.ws.client import WsClient
            from exchanges.extended.perp.constants import WS_URL
            # Extended uses URL-based streaming - no subscription needed
            exc_sym = adapter._symbol_map.get("BTC", "BTC-USD")
            ws_url = f"{WS_URL}/orderbooks/{exc_sym}?depth=1"
            print(f"  Connecting to: {ws_url}")
            adapter.ws = WsClient(
                url=ws_url,
                on_message=handle_message_with_log
            )

            connect_task = asyncio.create_task(adapter.ws.connect())
            await asyncio.sleep(1)
            await connect_task

        print("\nStarting websocket (10s)...")
        task = asyncio.create_task(patched_subscribe(test_symbols, on_update))
        await asyncio.sleep(10)
        task.cancel()

        print(f"\n[websocket] Received {len(messages_received)} updates")
        assert len(messages_received) > 0, "No websocket data received"

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await adapter.close()


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Testing Extended Adapter (Detailed Logging)")
    print("=" * 60)

    tests = [
        ("list_symbols", test_list_symbols),
        ("get_symbol_info", test_get_symbol_info),
        ("get_funding_rate", test_get_funding_rate),
        ("get_fee_rates", test_get_fee_rates),
        ("websocket", test_websocket),
    ]

    for name, test in tests:
        try:
            await test()
            print(f"\nPASS: {name}")
            print("-" * 40)
        except Exception as e:
            print(f"\nFAIL: {name} - {e}")
            import traceback
            traceback.print_exc()
            print("-" * 40)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
