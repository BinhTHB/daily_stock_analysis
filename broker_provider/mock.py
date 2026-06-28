# -*- coding: utf-8 -*-
"""Mock broker adapter for testing and dry-run mode — no real connection required."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from .base import BaseBroker
from .order import (
    BrokerAccountInfo,
    BrokerConnectionConfig,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPosition,
    OrderSide,
)

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = BrokerConnectionConfig()


class MockBroker(BaseBroker):
    """In-process mock broker that simulates fills at last-quoted price."""

    def __init__(self, config: Optional[BrokerConnectionConfig] = None):
        super().__init__(config or _DEFAULT_CONFIG)
        self._connected = False
        self._pending_orders: dict = {}
        self._positions: dict = {}
        self._cash: float = 1_000_000.0  # $1M starting cash

    # ---- lifecycle ----

    def connect(self) -> None:
        self._connected = True
        logger.info("MockBroker connected (simulated)")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("MockBroker disconnected (simulated)")

    def is_connected(self) -> bool:
        return self._connected

    # ---- account ----

    def get_account_info(self) -> BrokerAccountInfo:
        positions_value = sum(
            p.quantity * p.market_price for p in self._positions.values()
        )
        total_value = self._cash + positions_value
        return BrokerAccountInfo(
            account_id="mock001",
            cash_balance=self._cash,
            total_value=total_value,
            buying_power=self._cash,
            currency="USD",
            is_paper=True,
            last_updated=datetime.now(timezone.utc),
        )

    def get_positions(self) -> List[BrokerPosition]:
        return list(self._positions.values())

    # ---- orders ----

    def execute_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        if not self._connected:
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                status=BrokerOrderStatus.FAILED,
                error_message="Not connected",
            )

        order_id = secrets.token_hex(8)
        # Simulate instant fill at 'market price' (use limit_price if LMT, else 100.0)
        fill_price = request.limit_price or 100.0
        filled_qty = request.quantity

        # Update positions
        symbol = request.symbol.upper()
        current = self._positions.get(symbol)
        if request.side == OrderSide.BUY:
            new_qty = (current.quantity if current else 0.0) + filled_qty
            cost_basis = (
                current.cost_basis if current else fill_price
            )
            self._cash -= fill_price * filled_qty
        else:  # SELL
            new_qty = (current.quantity if current else 0.0) - filled_qty
            cost_basis = current.cost_basis if current else fill_price
            self._cash += fill_price * filled_qty

        if new_qty > 0:
            self._positions[symbol] = BrokerPosition(
                symbol=symbol,
                quantity=new_qty,
                market_price=fill_price,
                cost_basis=cost_basis,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                currency="USD",
                account_id="mock001",
            )
        else:
            self._positions.pop(symbol, None)

        logger.info(
            "MockBroker %s %s/%s at %.2f (qty=%.2f)",
            request.side.value,
            filled_qty,
            symbol,
            fill_price,
            filled_qty,
        )

        return BrokerOrderResult(
            success=True,
            order_id=order_id,
            external_id=request.external_id or "",
            symbol=symbol,
            side=request.side,
            filled_quantity=filled_qty,
            avg_fill_price=fill_price,
            status=BrokerOrderStatus.FILLED,
            commission=0.0,
            filled_at=datetime.now(timezone.utc),
        )

    def cancel_order(self, order_id: str) -> bool:
        self._pending_orders.pop(order_id, None)
        return True
