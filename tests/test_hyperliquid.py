"""Tests for Hyperliquid exchange adapter"""

import asyncio
from decimal import Decimal

import sys
sys.path.insert(0, '..')

from adapters.hyperliquid import HyperliquidAdapter


async def test_list_symbols():
    """Test fetching available symbols"""
    adapter = HyperliquidAdapter()
    try:
        symbols = await adapter.list_symbols()
        print(f"[list_symbols] Found {len(symbols)} symbols: {symbols[:5]}...")
        assert len(symbols) > 0, "Should have at least one symbol"
        assert isinstance(symbols[0], str), "Symbols should be strings"
    finally:
        await adapter.close()


async def test_get_symbol_info():
    """Test fetching symbol info"""
    adapter = HyperliquidAdapter()
    try:
        await adapter.list_symbols()
        infos = await adapter.get_symbol_info()
        print(f"[get_symbol_info] Got info for {len(infos)} symbols")
        assert len(infos) > 0, "Should have symbol info"
        info = infos[0]
        print(f"  Sample: {info.symbol} - {info.exchange_symbol}")
        assert info.symbol, "Should have normalized symbol"
        assert info.exchange_symbol, "Should have exchange symbol"
    finally:
        await adapter.close()


async def test_get_funding_rate():
    """Test fetching funding rate"""
    adapter = HyperliquidAdapter()
    try:
        symbols = await adapter.list_symbols()
        if symbols:
            symbol = symbols[0]
            funding = await adapter.get_funding_rate(symbol)
            print(f"[get_funding_rate] {symbol}: rate={funding.funding_rate}, mark={funding.mark_price}")
            assert funding.symbol == symbol, "Symbol should match"
            assert isinstance(funding.funding_rate, Decimal), "Rate should be Decimal"
    finally:
        await adapter.close()


async def test_get_fee_rates():
    """Test fetching fee rates"""
    adapter = HyperliquidAdapter()
    try:
        fees = await adapter.get_fee_rates()
        print(f"[get_fee_rates] maker={fees.maker_fee}, taker={fees.taker_fee}")
        assert isinstance(fees.maker_fee, Decimal), "Maker fee should be Decimal"
        assert isinstance(fees.taker_fee, Decimal), "Taker fee should be Decimal"
    finally:
        await adapter.close()


async def run_all_tests():
    """Run all tests"""
    print("=" * 50)
    print("Testing Hyperliquid Adapter")
    print("=" * 50)

    tests = [
        ("list_symbols", test_list_symbols),
        ("get_symbol_info", test_get_symbol_info),
        ("get_funding_rate", test_get_funding_rate),
        ("get_fee_rates", test_get_fee_rates),
    ]

    for name, test in tests:
        try:
            await test()
            print(f"PASS: {name}\n")
        except Exception as e:
            print(f"FAIL: {name} - {e}\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
