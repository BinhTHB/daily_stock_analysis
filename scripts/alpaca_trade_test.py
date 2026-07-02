#!/usr/bin/env python
"""
Standalone Alpaca trade test script — executes test trades without running analysis.
Submits market orders directly via REST API (fire-and-forget) so they queue until market opens.
"""
from __future__ import annotations

import os
import sys
import logging
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from broker_provider import create_broker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    stock_list_env = os.getenv("STOCK_LIST", "AAPL")
    symbols = [s.strip().upper() for s in stock_list_env.split(",") if s.strip()]
    logger.info("STOCK_LIST: %s", symbols)

    broker = create_broker("alpaca", timeout_seconds=15.0)
    broker.connect()
    if not broker.is_connected():
        logger.error("Failed to connect to Alpaca")
        return 1

    info = broker.get_account_info()
    logger.info(
        "Account: id=%s cash=%.2f buying_power=%.2f paper=%s",
        info.account_id, info.cash_balance, info.buying_power, info.is_paper
    )
    if info.cash_balance <= 0:
        logger.error("No cash balance available")
        return 1

    positions = broker.get_positions()
    owned = {p.symbol.upper(): p.quantity for p in positions}
    logger.info("Current positions: %s", owned)

    # Place orders directly via REST API — fire-and-forget, no cancel
    headers = {
        "APCA-API-KEY-ID": broker.api_key,
        "APCA-API-SECRET-KEY": broker.api_secret,
        "Content-Type": "application/json",
    }
    base_url = broker.base_url

    successful = 0
    failed = 0

    for symbol in symbols:
        if symbol in owned and owned[symbol] > 0:
            logger.info("Skipping %s — already have %.2f shares", symbol, owned[symbol])
            continue

        order_data = {
            "symbol": symbol,
            "qty": "1",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }

        logger.info("Submitting order: %s", order_data)
        try:
            resp = requests.post(
                f"{base_url}/orders",
                headers=headers,
                json=order_data,
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                order = resp.json()
                logger.info(
                    "✅ BUY submitted: %s -> order_id=%s status=%s (will fill when market opens)",
                    symbol, order.get("id", "?"), order.get("status", "?")
                )
                successful += 1
            else:
                logger.error("❌ BUY failed: %s HTTP %s - %s", symbol, resp.status_code, resp.text)
                failed += 1
        except Exception as e:
            logger.error("❌ BUY exception: %s - %s", symbol, e)
            failed += 1

    logger.info("=" * 50)
    logger.info("TRADE TEST SUMMARY")
    logger.info("=" * 50)
    logger.info("Total symbols: %d", len(symbols))
    logger.info("Submitted: %d (will fill when market opens at 9:30 AM ET)", successful)
    logger.info("Failed: %d", failed)

    broker.disconnect()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
