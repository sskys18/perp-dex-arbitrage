"""Tests for Nado exchange adapter"""

import asyncio
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.nado import NadoAdapter, NADO_PRODUCT_MAP


async def test_list_symbols():
    """Test fetching available symbols with detailed logging"""
    adapter = NadoAdapter()
    try:
        symbols = await adapter.list_symbols()
        print(f"\n[list_symbols] Found {len(symbols)} symbols:")
        for sym in symbols:
            product_id = adapter._product_id_map.get(sym)
            print(f"  {sym} -> product_id: {product_id}")
        print(f"\nSymbol map: {adapter._symbol_map}")
        print(f"Reverse map: {adapter._reverse_map}")
    finally:
        await adapter.close()


async def test_get_symbol_info():
    """Test fetching symbol info"""
    adapter = NadoAdapter()
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
    adapter = NadoAdapter()
    try:
        symbols = await adapter.list_symbols()
        if symbols:
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
    adapter = NadoAdapter()
    try:
        fees = await adapter.get_fee_rates()
        print(f"\n[get_fee_rates]")
        print(f"  maker: {fees.maker_fee} ({float(fees.maker_fee)*100:.4f}%)")
        print(f"  taker: {fees.taker_fee} ({float(fees.taker_fee)*100:.4f}%)")
    finally:
        await adapter.close()


async def test_websocket():
    """Test websocket subscription with detailed raw message logging"""
    adapter = NadoAdapter()
    messages_received = []
    scale = Decimal("1000000000000000000")

    try:
        symbols = await adapter.list_symbols()
        test_symbols = ["BTC", "ETH", "SOL"] if "BTC" in symbols else symbols[:3]

        print(f"\n[websocket] Testing symbols: {test_symbols}")
        print(f"Product ID mapping:")
        for sym in test_symbols:
            pid = adapter._product_id_map.get(sym)
            print(f"  {sym} -> product_id: {pid}")

        async def on_update(update):
            messages_received.append(update)
            print(f"\n[WS UPDATE] {update.symbol} ({update.exchange})")
            print(f"  bid: {update.bid_px} x {update.bid_sz}")
            print(f"  ask: {update.ask_px} x {update.ask_sz}")

        # Patch handle_message to log raw data
        original_subscribe = adapter.subscribe_market_data

        async def patched_subscribe(syms, callback):
            scale = Decimal("1000000000000000000")

            async def handle_message_with_log(data):
                print(f"\n[RAW MESSAGE] {data}")

                if not isinstance(data, dict):
                    return

                msg_type = data.get("type")
                if msg_type != "best_bid_offer":
                    print(f"  Skipping: type={msg_type}")
                    return

                product_id = data.get("product_id")
                print(f"  product_id: {product_id}")
                print(f"  reverse_map keys: {list(adapter._reverse_map.keys())}")

                if not product_id or str(product_id) not in adapter._reverse_map:
                    print(f"  Skipping: product_id {product_id} not in reverse_map")
                    return

                bid_price = data.get("bid_price")
                ask_price = data.get("ask_price")
                bid_qty = data.get("bid_qty")
                ask_qty = data.get("ask_qty")

                print(f"  Raw bid_price: {bid_price}")
                print(f"  Raw ask_price: {ask_price}")
                print(f"  Scaled bid: {Decimal(str(bid_price)) / scale}")
                print(f"  Scaled ask: {Decimal(str(ask_price)) / scale}")

                symbol = adapter._reverse_map[str(product_id)]
                print(f"  Mapped symbol: {symbol}")

                from models import MarketUpdate
                update = MarketUpdate(
                    exchange=adapter.name,
                    symbol=symbol,
                    bid_px=Decimal(str(bid_price)) / scale,
                    bid_sz=Decimal(str(bid_qty)) / scale if bid_qty else Decimal(0),
                    ask_px=Decimal(str(ask_price)) / scale,
                    ask_sz=Decimal(str(ask_qty)) / scale if ask_qty else Decimal(0),
                    ts_local=0,
                )
                await callback(update)

            from exchanges.nado.perp.ws_client import NadoPerpWsClient
            adapter.ws = NadoPerpWsClient(on_message=handle_message_with_log)

            async def on_connect():
                for sym in syms:
                    product_id = adapter._product_id_map.get(sym)
                    if product_id:
                        print(f"  Subscribing to product_id: {product_id} ({sym})")
                        await adapter.ws.subscribe_best_bid_offer(product_id)

            connect_task = asyncio.create_task(adapter.ws.connect())
            await asyncio.sleep(1)
            await on_connect()
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
    print("Testing Nado Adapter (Detailed Logging)")
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
