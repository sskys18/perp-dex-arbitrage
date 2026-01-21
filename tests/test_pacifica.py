"""Tests for Pacifica exchange adapter"""

import asyncio
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.pacifica import PacificaAdapter


async def test_list_symbols():
    """Test fetching available symbols with detailed logging"""
    adapter = PacificaAdapter()
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
    adapter = PacificaAdapter()
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
    adapter = PacificaAdapter()
    try:
        symbols = await adapter.list_symbols()
        if "BTC" in symbols:
            symbol = "BTC"
        else:
            symbol = symbols[0]
        funding = await adapter.get_funding_rate(symbol)
        print(f"\n[get_funding_rate] {symbol}:")
        print(f"  funding_rate: {funding.funding_rate}")
    finally:
        await adapter.close()


async def test_get_fee_rates():
    """Test fetching fee rates"""
    adapter = PacificaAdapter()
    try:
        fees = await adapter.get_fee_rates()
        print(f"\n[get_fee_rates]")
        print(f"  maker: {fees.maker_fee} ({float(fees.maker_fee)*100:.4f}%)")
        print(f"  taker: {fees.taker_fee} ({float(fees.taker_fee)*100:.4f}%)")
    finally:
        await adapter.close()


async def test_websocket():
    """Test websocket subscription with detailed raw message logging"""
    adapter = PacificaAdapter()
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

                channel = data.get("channel", "")
                print(f"  channel: {channel}")

                if not channel.startswith("bbo."):
                    print(f"  Skipping: not bbo channel")
                    return

                exc_sym = channel.replace("bbo.", "")
                print(f"  exc_sym: {exc_sym}")
                print(f"  reverse_map keys sample: {list(adapter._reverse_map.keys())[:5]}")

                if exc_sym not in adapter._reverse_map:
                    print(f"  Skipping: {exc_sym} not in reverse_map")
                    return

                bbo_data = data.get("data", {})
                bid = bbo_data.get("bid", {})
                ask = bbo_data.get("ask", {})
                print(f"  bid: {bid}")
                print(f"  ask: {ask}")

                if not bid or not ask:
                    print(f"  Skipping: missing bid or ask")
                    return

                from models import MarketUpdate
                update = MarketUpdate(
                    exchange=adapter.name,
                    symbol=adapter._reverse_map[exc_sym],
                    bid_px=Decimal(str(bid.get("price", "0"))),
                    bid_sz=Decimal(str(bid.get("size", "0"))),
                    ask_px=Decimal(str(ask.get("price", "0"))),
                    ask_sz=Decimal(str(ask.get("size", "0"))),
                    ts_exchange=bbo_data.get("timestamp"),
                    ts_local=0,
                )
                await callback(update)

            from core.ws.client import WsClient
            adapter.ws = WsClient(
                url="wss://api.pacifica.fi/ws",
                on_message=handle_message_with_log
            )

            async def on_connect():
                for sym in syms:
                    exc_sym = adapter._symbol_map.get(sym, sym)
                    print(f"  Subscribing to: bbo.{exc_sym}")
                    await adapter.ws.send({
                        "type": "subscribe",
                        "channel": f"bbo.{exc_sym}"
                    })

            connect_task = asyncio.create_task(adapter.ws.connect())
            await asyncio.sleep(1)
            await on_connect()
            await connect_task

        print("\nStarting websocket (1s)...")
        task = asyncio.create_task(patched_subscribe(test_symbols, on_update))
        await asyncio.sleep(1)
        task.cancel()

        print(f"\n[websocket] Received {len(messages_received)} updates")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await adapter.close()


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Testing Pacifica Adapter (Detailed Logging)")
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
