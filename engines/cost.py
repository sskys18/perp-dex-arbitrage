"""Cost engine for computing trading costs and scores"""

from decimal import Decimal
from typing import Dict, Tuple

from models import FeeRates


class CostEngine:
    """Computes trading costs and adjusted scores"""

    def __init__(self, fee_rates: Dict[str, FeeRates]):
        """
        Initialize cost engine

        Args:
            fee_rates: Dict of exchange name -> FeeRates
        """
        self._fees = fee_rates
        # Funding rates: (exchange, symbol) -> rate
        self._funding: Dict[Tuple[str, str], Decimal] = {}

    def update_fees(self, exchange: str, fee_rates: FeeRates) -> None:
        """Update fee rates for an exchange"""
        self._fees[exchange] = fee_rates

    def update_funding(self, exchange: str, symbol: str, rate: Decimal) -> None:
        """Update funding rate for an exchange/symbol pair"""
        self._funding[(exchange, symbol)] = rate

    def get_taker_fee(self, exchange: str) -> Decimal:
        """Get taker fee for an exchange"""
        fee_rates = self._fees.get(exchange)
        if fee_rates:
            return fee_rates.taker_fee
        return Decimal("0.0005")  # Default 0.05%

    def get_maker_fee(self, exchange: str) -> Decimal:
        """Get maker fee for an exchange"""
        fee_rates = self._fees.get(exchange)
        if fee_rates:
            return fee_rates.maker_fee
        return Decimal("0.0002")  # Default 0.02%

    def get_funding(self, exchange: str, symbol: str) -> Decimal:
        """Get funding rate for an exchange/symbol pair"""
        return self._funding.get((exchange, symbol), Decimal("0"))

    def compute_sell_score(self, price: Decimal, exchange: str, symbol: str) -> Decimal:
        """
        Compute sell score: effective price after costs for selling.
        Higher is better for selling.

        SellScore = price * (1 - taker_fee) - funding_cost
        """
        fee = self.get_taker_fee(exchange)
        funding = self.get_funding(exchange, symbol)
        return price * (Decimal("1") - fee) - funding

    def compute_buy_score(self, price: Decimal, exchange: str, symbol: str) -> Decimal:
        """
        Compute buy score: effective price after costs for buying.
        Lower is better for buying.

        BuyScore = price * (1 + taker_fee) + funding_cost
        """
        fee = self.get_taker_fee(exchange)
        funding = self.get_funding(exchange, symbol)
        return price * (Decimal("1") + fee) + funding
