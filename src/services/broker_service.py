# -*- coding: utf-8 -*-
"""BrokerService — high-level facade for broker integration.

Loads config, creates broker instance, and provides methods to:
- Get account info / positions
- Execute a trade decision signal via broker
- Sync broker positions to local Portfolio DB
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.config import get_config
from broker_provider import (
    BaseBroker,
    BrokerAccountInfo,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPosition,
    OrderSide,
    create_broker,
    BROKER_IBKR,
    BROKER_MOCK,
)
from broker_provider.sync import sync_positions_to_local_db, get_broker_positions_summary

logger = logging.getLogger(__name__)


class BrokerService:
    """High-level facade for broker operations."""

    def __init__(self, *, simulate: Optional[bool] = None) -> None:
        config = get_config()
        self._enabled = config.broker_enabled
        self._simulate: bool = (
            simulate if simulate is not None else config.broker_simulate
        )
        self._broker: Optional[BaseBroker] = None

        if not self._enabled:
            logger.info("Broker integration is disabled (BROKER_ENABLED=false)")
            return

        provider = config.broker_provider
        # If simulate=True, force mock regardless of provider
        if self._simulate:
            resolved_provider = "mock"
            logger.info(
                "Broker simulate mode active — using MockBroker "
                "(set BROKER_SIMULATE=false for real execution)"
            )
        else:
            resolved_provider = provider

        self._broker = create_broker(
            resolved_provider,
            host=config.broker_host,
            port=config.broker_port,
            client_id=config.broker_client_id,
            account_id=config.broker_account_id,
            timeout_seconds=config.broker_timeout_seconds,
            simulate=self._simulate,
        )

    # -- lifecycle --

    def connect(self) -> None:
        """Connect to broker (no-op if disabled)."""
        if not self._broker:
            return
        try:
            self._broker.connect()
            info = self._broker.get_account_info()
            logger.info(
                "Broker connected: account=%s cash=%.2f paper=%s",
                info.account_id,
                info.cash_balance,
                info.is_paper,
            )
        except Exception as exc:
            logger.error("Broker connection failed: %s", exc)

    def disconnect(self) -> None:
        if self._broker:
            self._broker.disconnect()

    @property
    def is_connected(self) -> bool:
        return bool(self._broker and self._broker.is_connected())

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- account / positions --

    def get_account_info(self) -> Optional[BrokerAccountInfo]:
        if not self._broker:
            return None
        try:
            return self._broker.get_account_info()
        except Exception as exc:
            logger.error("Failed to get account info: %s", exc)
            return None

    def get_positions(self) -> List[BrokerPosition]:
        if not self._broker:
            return []
        try:
            return self._broker.get_positions()
        except Exception as exc:
            logger.error("Failed to get positions: %s", exc)
            return []

    # -- trade execution --

    def execute_signal(
        self,
        *,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: str = "MKT",  # MKT / LMT
        limit_price: Optional[float] = None,
        note: Optional[str] = None,
    ) -> BrokerOrderResult:
        """Execute a single trade signal via broker."""
        if not self._broker:
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id="",
                symbol=symbol,
                side=side,
                status="failed",
                error_message="Broker not enabled (BROKER_ENABLED=false)",
            )

        if not self._broker.is_connected():
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id="",
                symbol=symbol,
                side=side,
                status="failed",
                error_message="Broker not connected. Call connect() first.",
            )

        request = BrokerOrderRequest(
            side=side,
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price if order_type in ("LMT", "STPLMT") else None,
            time_in_force="DAY",
            extras={"note": note or ""},
        )
        logger.info(
            "Executing %s %s/%s %s (qty=%.2f)",
            side.value,
            quantity,
            symbol,
            order_type,
            quantity,
        )
        return self._broker.execute_order(request)

    def sync_to_local_db(
        self,
        portfolio_account_id: int = 1,
    ) -> str:
        """Sync IBKR positions into local Portfolio DB.

        Returns a human-readable summary string.
        """
        if not self._broker:
            return "Broker not enabled."

        try:
            added, updated, unchanged = sync_positions_to_local_db(
                self._broker,
                portfolio_account_id=portfolio_account_id,
            )
            return f"Sync done: added={added}, updated={updated}, unchanged={unchanged}"
        except Exception as exc:
            logger.exception("Position sync failed")
            return f"Sync failed: {exc}"

    # -- report helper --

    def report_summary(self) -> str:
        """Return a text block for embedding in the daily report."""
        if not self._enabled:
            return ""

        info = self.get_account_info()
        if not info:
            return "**Portfolio:** Broker connection unavailable"

        positions = self.get_positions()
        lines = [
            f"**Portfolio:** ${info.total_value:,.2f} | "
            f"Cash: ${info.cash_balance:,.2f} | "
            f"Buying Power: ${info.buying_power:,.2f} | "
            f"{'Paper' if info.is_paper else 'Live'}"
        ]
        if positions:
            total_pnl = sum(p.unrealized_pnl for p in positions)
            lines.append(f"**Positions:** {len(positions)} holdings, P&L: ${total_pnl:+,.2f}")
            for p in positions[:5]:  # top 5
                lines.append(
                    f"- {p.symbol}: {p.quantity:.2f} @ ${p.market_price:.2f} "
                    f"(P&L: ${p.unrealized_pnl:+,.2f})"
                )
            if len(positions) > 5:
                lines.append(f"- ... ({len(positions) - 5} more)")
        else:
            lines.append("No open positions.")

        return "\n".join(lines)
