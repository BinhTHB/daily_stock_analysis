"""Minimal end-to-end test: place a real market buy order on Alpaca Paper."""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from broker_provider.alpaca_adapter import AlpacaAdapter
from broker_provider.order import BrokerOrderRequest, OrderSide

def main():
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_API_SECRET")

    if not api_key or not api_secret:
        logger.error("ALPACA_API_KEY / ALPACA_API_SECRET not set")
        sys.exit(1)

    adapter = AlpacaAdapter(api_key=api_key, api_secret=api_secret, paper=True)
    adapter.connect()

    if not adapter.is_connected():
        logger.error("Failed to connect to Alpaca")
        sys.exit(1)

    logger.info("Connected to Alpaca Paper")

    # Get account info for confirmation
    info = adapter.get_account_info()
    logger.info("Account: %s | Cash: $%.2f | Buying Power: $%.2f",
                info.account_id, info.cash_balance, info.buying_power)

    # Place a market buy for 1 share of AAPL
    request = BrokerOrderRequest(
        side=OrderSide.BUY,
        symbol="AAPL",
        quantity=1,
        order_type="MKT",
        time_in_force="DAY",
    )

    logger.info("Placing market buy for 1 AAPL...")
    result = adapter.execute_order(request)

    if result.success:
        logger.info("=== ORDER FILLED ===")
        logger.info("Order ID: %s", result.order_id)
        logger.info("Symbol: %s", result.symbol)
        logger.info("Side: %s", result.side.value)
        logger.info("Filled Qty: %s", result.filled_quantity)
        logger.info("Avg Fill Price: $%.2f", result.avg_fill_price)
        logger.info("Filled At: %s", result.filled_at)
        print("\n✅ ORDER PLACED AND FILLED SUCCESSFULLY")
    else:
        logger.error("Order failed: %s", result.error_message)
        print(f"\n❌ ORDER FAILED: {result.error_message}")
        sys.exit(1)

    adapter.disconnect()
    logger.info("Disconnected")

if __name__ == "__main__":
    main()
