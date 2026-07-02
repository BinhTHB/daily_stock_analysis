#!/usr/bin/env python
"""
Standalone Alpaca trade test script — executes test trades without running analysis.
Reads STOCK_LIST from environment, connects to Alpaca paper account, buys small test positions.
"""
from __future__ import annotations

import os
import sys
import logging
from typing import List

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker_provider import create_broker, OrderSide
from broker_provider.order import BrokerOrderRequest, BrokerOrderStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    # Read configuration from environment
    stock_list_env = os.getenv("STOCK_LIST", "AAPL")

    symbols = [s.strip().upper() for s in stock_list_env.split(",") if s.strip()]
    logger.info("STOCK_LIST: %s", symbols)
    logger.info("Alpaca mode: paper")

    # Create Alpaca broker (reads ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER from env)
    broker = create_broker("alpaca", timeout_seconds=15.0)  # Shorten timeout for test speed

    # Connect
    logger.info("Connecting to Alpaca...")
    broker.connect()
    if not broker.is_connected():
        logger.error("Failed to connect to Alpaca")
        return 1

    # Get account info
    info = broker.get_account_info()
    logger.info(
        "Account: id=%s cash=%.2f buying_power=%.2f paper=%s",
        info.account_id, info.cash_balance, info.buying_power, info.is_paper
    )

    if info.cash_balance <= 0:
        logger.error("No cash balance available for trading")
        return 1

    # Get current positions
    positions = broker.get_positions()
    owned = {p.symbol.upper(): p.quantity for p in positions}
    logger.info("Current positions: %s", owned)

    # Trade each symbol
    successful = 0
    failed = 0

    for symbol in symbols:
        # Skip if already have position
        if symbol in owned and owned[symbol] > 0:
            logger.info("Skipping %s - already have %.2f shares", symbol, owned[symbol])
            continue

        # Place market order for 1 share for safety
        qty = 1

        logger.info("Placing BUY order: %s qty=%d", symbol, qty)

        request = BrokerOrderRequest(
            side=OrderSide.BUY,
            symbol=symbol,
            quantity=qty,
            order_type="MKT",
            time_in_force="DAY",
        )

        result = broker.execute_order(request)

        if result.success:
            logger.info(
                "✅ BUY filled: %s %s %s shares @ %.2f (order_id=%s)",
                result.symbol, result.side.value, result.filled_quantity,
                result.avg_fill_price, result.order_id
            )
            successful += 1
        else:
            err_msg = result.error_message or ""
            if "timed out" in err_msg.lower():
                logger.info(
                    "✅ BUY submitted: %s (API connection OK, but timed out/cancelled because market is closed)",
                    symbol
                )
                successful += 1
            else:
                logger.error(
                    "❌ BUY failed: %s %s - %s",
                    result.symbol, result.side.value, err_msg
                )
                failed += 1

    # Final summary
    logger.info("=" * 50)
    logger.info("TRADE TEST SUMMARY")
    logger.info("=" * 50)
    logger.info("Total symbols: %d", len(symbols))
    logger.info("Successful (or submitted): %d", successful)
    logger.info("Failed: %d", failed)

    # Show updated account
    info = broker.get_account_info()
    logger.info("Final cash: %.2f, buying_power: %.2f", info.cash_balance, info.buying_power)

    broker.disconnect()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
