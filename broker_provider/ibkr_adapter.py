# -*- coding: utf-8 -*-
"""IBKR adapter — executes trades via TWS/Gateway using ib_insync.

Requires ``ib_insync`` (pip install ib_insync) and a running TWS or IB Gateway
instance.  Uses port 7497 (TWS paper) / 4002 (Gateway paper) by default.
"""
from __future__ import annotations

import logging
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
    BrokerError,
    BrokerAuthError,
    BrokerConnectionError,
    BrokerOrderRejectedError,
    OrderSide as LocalSide,
)

logger = logging.getLogger(__name__)

# Lazily import ib_insync so the module is loadable without it.
_ib_insync = None


def _get_ib():
    global _ib_insync
    if _ib_insync is None:
        try:
            import ib_insync  # noqa: F811

            _ib_insync = ib_insync
        except ImportError as exc:
            raise ImportError(
                "ib_insync is required for IBKR adapter. "
                "Install with: pip install ib_insync"
            ) from exc
    return _ib_insync


class IBKRAdapter(BaseBroker):
    """IBKR adapter using ib_insync over TWS/Gateway API."""

    def __init__(self, config: BrokerConnectionConfig):
        super().__init__(config)
        self._ib = None  # ib_insync.IB instance
        self._connected_id: Optional[str] = None

    # ---- lifecycle ----

    def connect(self) -> None:
        ib = _get_ib()
        self._ib = ib.IB()
        try:
            self._ib.connect(
                host=self.config.host,
                port=self.config.port,
                clientId=self.config.client_id,
                timeout=self.config.timeout_seconds,
            )
        except ConnectionRefusedError as exc:
            raise BrokerConnectionError(
                f"Cannot connect to IBKR at {self.config.host}:{self.config.port}. "
                "Ensure TWS/Gateway is running with API enabled."
            ) from exc
        except Exception as exc:
            raise BrokerError(
                f"IBKR connection failed: {exc}"
            ) from exc

        # Verify connection — retry up to 45s for IBC auto-login
        import time
        last_exc = None
        for attempt in range(15):  # 15 retries × 3s = 45s
            try:
                account_summary = self._ib.accountSummary()
                if account_summary:
                    break
            except Exception as exc:
                last_exc = exc
                time.sleep(3)
                continue
        else:
            self._ib.disconnect()
            msg = (
                "IBKR connected but auth/login failed after 45s retries. "
                "Check IBKR_USERNAME/IBKR_PASSWORD secrets and TradingMode."
            )
            raise BrokerAuthError(msg) from last_exc

        self._connected_id = f"{self.config.host}:{self.config.port}"
        logger.info(
            "IBKR connected to %s:%s (client_id=%s)",
            self.config.host,
            self.config.port,
            self.config.client_id,
        )

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            logger.info("IBKR disconnected")
        self._connected_id = None

    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    # ---- account ----

    def get_account_info(self) -> BrokerAccountInfo:
        self._require_connected()
        ib = self._ib
        summary = {s.tag: s.value for s in ib.accountSummary()}

        cash = float(summary.get("TotalCashValue", 0))
        total = float(summary.get("NetLiquidation", 0))
        buying_power = float(summary.get("BuyingPower", 0))
        currency = summary.get("Currency", "USD")

        # Determine paper vs live from connection port (convention)
        is_paper = self.config.port in (7497, 4002)

        return BrokerAccountInfo(
            account_id=self.config.account_id or summary.get("AccountType", "unknown"),
            cash_balance=cash,
            total_value=total,
            buying_power=buying_power,
            currency=currency,
            is_paper=is_paper,
            last_updated=datetime.now(timezone.utc),
        )

    def get_positions(self) -> List[BrokerPosition]:
        self._require_connected()
        ib = self._ib
        raw = ib.positions()
        positions = []
        for pos in raw:
            positions.append(
                BrokerPosition(
                    symbol=pos.contract.symbol,
                    quantity=float(pos.position),
                    market_price=float(pos.marketPrice) if pos.marketPrice else 0.0,
                    cost_basis=float(pos.avgCost) if pos.avgCost else 0.0,
                    unrealized_pnl=float(pos.unrealizedPNL) if pos.unrealizedPNL else 0.0,
                    realized_pnl=float(pos.realizedPNL) if pos.realizedPNL else 0.0,
                    currency=pos.contract.currency,
                    account_id=str(pos.account),
                )
            )
        return positions

    # ---- orders ----

    def execute_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        self._require_connected()
        ib = self._ib
        ib_insync = _get_ib()

        # Build contract
        contract = ib_insync.Stock(request.symbol, "SMART", "USD")

        # Build order
        side = "BUY" if request.side == LocalSide.BUY else "SELL"
        order_type = request.order_type.upper()

        if order_type == "MKT":
            order = ib_insync.MarketOrder(side, request.quantity)
        elif order_type == "LMT":
            if request.limit_price is None:
                return BrokerOrderResult(
                    success=False,
                    order_id="",
                    external_id=request.external_id or "",
                    symbol=request.symbol,
                    side=request.side,
                    status=BrokerOrderStatus.REJECTED,
                    error_message="Limit price required for LMT order",
                )
            order = ib_insync.LimitOrder(side, request.quantity, request.limit_price)
        elif order_type == "STPLMT":
            if request.limit_price is None:
                return BrokerOrderResult(
                    success=False,
                    order_id="",
                    external_id=request.external_id or "",
                    symbol=request.symbol,
                    side=request.side,
                    status=BrokerOrderStatus.REJECTED,
                    error_message="Limit price required for STPLMT order",
                )
            stop_price = request.extras.get("stop_price", request.limit_price * 0.98)
            order = ib_insync.StopLimitOrder(
                side, request.quantity, request.limit_price, stop_price
            )
        else:
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                status=BrokerOrderStatus.REJECTED,
                error_message=f"Unsupported order type: {order_type}",
            )

        order.tif = request.time_in_force or "DAY"
        if request.external_id:
            order.orderRef = request.external_id

        # Place
        try:
            trade = ib.placeOrder(contract, order)
            # Wait for fill or rejection
            ib.sleep(0.5)
            ib.waitOnUpdate(timeout=10.0)
        except Exception as exc:
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                status=BrokerOrderStatus.FAILED,
                error_message=str(exc),
            )

        order_status = trade.orderStatus.status.lower()
        filled_qty = float(trade.orderStatus.filled)
        remaining = float(trade.orderStatus.remaining)
        avg_price = float(trade.orderStatus.avgFillPrice) if filled_qty else 0.0

        # Map status
        if order_status == "filled":
            status = BrokerOrderStatus.FILLED
        elif order_status == "partiallyfilled":
            status = BrokerOrderStatus.PARTIALLY_FILLED
        elif order_status == "cancelled":
            status = BrokerOrderStatus.CANCELLED
        elif order_status == "rejected":
            status = BrokerOrderStatus.REJECTED
            error_msg = self._extract_rejection_reason(trade)
            return BrokerOrderResult(
                success=False,
                order_id=str(trade.order.permId or trade.order.orderId),
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                status=BrokerOrderStatus.REJECTED,
                error_message=error_msg,
            )
        else:
            status = BrokerOrderStatus.SUBMITTED

        filled_at = datetime.now(timezone.utc) if filled_qty else None

        return BrokerOrderResult(
            success=filled_qty > 0,
            order_id=str(trade.order.permId or trade.order.orderId),
            external_id=request.external_id or "",
            symbol=request.symbol,
            side=request.side,
            filled_quantity=filled_qty,
            avg_fill_price=avg_price,
            status=status,
            remaining_quantity=remaining,
            commission=0.0,  # IBKR provides commission later via trade log
            filled_at=filled_at,
        )

    def cancel_order(self, order_id: str) -> bool:
        self._require_connected()
        try:
            ib = self._ib
            trades = ib.trades()
            for trade in trades:
                if str(trade.order.permId) == order_id:
                    ib.cancelOrder(trade.order)
                    return True
            return False
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            return False

    # ---- internal ----

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise BrokerConnectionError("Not connected to IBKR. Call connect() first.")

    def _extract_rejection_reason(self, trade) -> str:
        try:
            messages = trade.log
            if messages:
                reasons = [
                    str(msg.message)
                    for msg in messages
                    if hasattr(msg, "message") and msg.message
                ]
                return "; ".join(reasons)
        except Exception:
            pass
        return "Order rejected by IBKR (no detail)"
