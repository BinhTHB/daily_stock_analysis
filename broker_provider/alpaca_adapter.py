# -*- coding: utf-8 -*-
"""Alpaca Broker Adapter using Alpaca REST API."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

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

# Fallback default configuration
_DEFAULT_CONFIG = BrokerConnectionConfig()


class AlpacaAdapter(BaseBroker):
    """
    Broker adapter for Alpaca Markets (REST API).
    Supports both Paper and Live accounts.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(_DEFAULT_CONFIG)
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        self.timeout_seconds = timeout_seconds
        self._connected = False

        if self.paper:
            self.base_url = "https://paper-api.alpaca.markets/v2"
        else:
            self.base_url = "https://api.alpaca.markets/v2"

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.api_secret or "",
            "Content-Type": "application/json",
        }

    # ---- lifecycle ----

    def connect(self) -> None:
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca connection failed: API key or Secret is missing.")
            self._connected = False
            return

        try:
            # Simple health check via account endpoint
            response = requests.get(
                f"{self.base_url}/account",
                headers=self.headers,
                timeout=self.timeout_seconds,
            )
            if response.status_code == 200:
                self._connected = True
                logger.info(
                    "AlpacaAdapter connected successfully (paper=%s)", self.paper
                )
            else:
                self._connected = False
                logger.error(
                    "Alpaca connection refused (HTTP %s): %s",
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            self._connected = False
            logger.error("Alpaca connection failed: %s", exc)

    def disconnect(self) -> None:
        self._connected = False
        logger.info("AlpacaAdapter disconnected.")

    def is_connected(self) -> bool:
        return self._connected

    # ---- account ----

    def get_account_info(self) -> BrokerAccountInfo:
        if not self._connected:
            raise ConnectionError("Broker not connected.")

        response = requests.get(
            f"{self.base_url}/account",
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        return BrokerAccountInfo(
            account_id=data.get("account_number", "unknown"),
            cash_balance=float(data.get("cash", 0.0)),
            total_value=float(data.get("portfolio_value", 0.0)),
            buying_power=float(data.get("buying_power", 0.0)),
            currency=data.get("currency", "USD"),
            is_paper=self.paper,
            last_updated=datetime.now(timezone.utc),
        )

    def get_positions(self) -> List[BrokerPosition]:
        if not self._connected:
            raise ConnectionError("Broker not connected.")

        response = requests.get(
            f"{self.base_url}/positions",
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        positions = []
        for pos in data:
            positions.append(
                BrokerPosition(
                    symbol=pos.get("symbol", ""),
                    quantity=float(pos.get("qty", 0.0)),
                    market_price=float(pos.get("current_price", 0.0)),
                    cost_basis=float(pos.get("avg_entry_price", 0.0)) * float(pos.get("qty", 0.0)),
                    unrealized_pnl=float(pos.get("unrealized_pl", 0.0)),
                    realized_pnl=float(pos.get("realized_pl", 0.0)),
                    currency="USD",
                    account_id=self.api_key,  # temporary reference
                )
            )
        return positions

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
                error_message="Broker not connected.",
            )

        # Map DSA order types/sides to Alpaca REST
        # DSA uses OrderSide.BUY/SELL, which values are 'buy' and 'sell'
        # DSA order_type is usually 'MKT' or 'LMT'
        alpaca_side = request.side.value.lower()
        alpaca_type = "market" if request.order_type.upper() == "MKT" else "limit"

        order_data: Dict[str, Any] = {
            "symbol": request.symbol.upper(),
            "qty": str(request.quantity),
            "side": alpaca_side,
            "type": alpaca_type,
            "time_in_force": request.time_in_force.lower(),
        }

        if alpaca_type == "limit" and request.limit_price is not None:
            order_data["limit_price"] = str(request.limit_price)

        try:
            logger.info("Submitting order to Alpaca: %s", order_data)
            response = requests.post(
                f"{self.base_url}/orders",
                headers=self.headers,
                json=order_data,
                timeout=self.timeout_seconds,
            )
            
            if response.status_code != 200 and response.status_code != 201:
                logger.error("Alpaca order placement failed: %s", response.text)
                return BrokerOrderResult(
                    success=False,
                    order_id="",
                    external_id=request.external_id or "",
                    symbol=request.symbol,
                    side=request.side,
                    status=BrokerOrderStatus.REJECTED,
                    error_message=f"Alpaca rejected: {response.text}",
                )

            order_info = response.json()
            order_id = order_info.get("id", "")
            
            # Start polling until order is filled, cancelled or timeout
            logger.info("Order %s submitted, polling for status...", order_id)
            start_time = time.time()
            poll_interval = 1.0

            while time.time() - start_time < self.timeout_seconds:
                poll_resp = requests.get(
                    f"{self.base_url}/orders/{order_id}",
                    headers=self.headers,
                    timeout=5.0,
                )
                if poll_resp.status_code == 200:
                    status_info = poll_resp.json()
                    alpaca_status = status_info.get("status", "")
                    logger.debug("Alpaca order %s status: %s", order_id, alpaca_status)

                    if alpaca_status == "filled":
                        return BrokerOrderResult(
                            success=True,
                            order_id=order_id,
                            external_id=request.external_id or "",
                            symbol=request.symbol,
                            side=request.side,
                            filled_quantity=float(status_info.get("filled_qty", 0.0)),
                            avg_fill_price=float(status_info.get("filled_avg_price", 0.0)),
                            status=BrokerOrderStatus.FILLED,
                            filled_at=datetime.now(timezone.utc),
                        )
                    elif alpaca_status in ("canceled", "cancelled"):
                        return BrokerOrderResult(
                            success=False,
                            order_id=order_id,
                            external_id=request.external_id or "",
                            symbol=request.symbol,
                            side=request.side,
                            status=BrokerOrderStatus.CANCELLED,
                            error_message="Order was cancelled.",
                        )
                    elif alpaca_status in ("rejected", "suspended"):
                        return BrokerOrderResult(
                            success=False,
                            order_id=order_id,
                            external_id=request.external_id or "",
                            symbol=request.symbol,
                            side=request.side,
                            status=BrokerOrderStatus.REJECTED,
                            error_message=f"Order rejected by Alpaca status: {alpaca_status}",
                        )
                
                time.sleep(poll_interval)

            # Timeout fallback: leave order pending with Alpaca if still active
            logger.warning("Order %s timed out. Leaving it active in Alpaca.", order_id)
            try:
                final_resp = requests.get(
                    f"{self.base_url}/orders/{order_id}",
                    headers=self.headers,
                    timeout=5.0,
                )
                if final_resp.status_code == 200:
                    status_info = final_resp.json()
                    alpaca_status = status_info.get("status", "")
                    filled_qty = float(status_info.get("filled_qty", 0.0))
                    avg_price = float(status_info.get("filled_avg_price", 0.0))
                    status = BrokerOrderStatus.SUBMITTED
                    if alpaca_status in ("filled", "partially_filled"):
                        status = BrokerOrderStatus.FILLED if alpaca_status == "filled" else BrokerOrderStatus.PARTIALLY_FILLED
                    elif alpaca_status in ("canceled", "cancelled"):
                        status = BrokerOrderStatus.CANCELLED
                    elif alpaca_status in ("rejected", "suspended"):
                        status = BrokerOrderStatus.REJECTED
                    logger.info("Order %s final status: %s filled=%.2f, avg=%.2f", order_id, status, filled_qty, avg_price)
                    return BrokerOrderResult(
                        success=status in (BrokerOrderStatus.FILLED, BrokerOrderStatus.PARTIALLY_FILLED, BrokerOrderStatus.SUBMITTED),
                        order_id=order_id,
                        external_id=request.external_id or "",
                        symbol=request.symbol,
                        side=request.side,
                        filled_quantity=filled_qty,
                        avg_fill_price=avg_price,
                        status=status,
                        error_message=None if status in (BrokerOrderStatus.FILLED, BrokerOrderStatus.PARTIALLY_FILLED, BrokerOrderStatus.SUBMITTED) else f"Order status is: {alpaca_status}",
                    )
            except Exception as exc:
                logger.warning("Failed to fetch final order status: %s", exc)
            return BrokerOrderResult(
                success=True,
                order_id=order_id,
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                status=BrokerOrderStatus.SUBMITTED,
                error_message="Order pending after timeout (still active in Alpaca).",
            )

        except Exception as exc:
            logger.error("Error executing Alpaca order: %s", exc)
            return BrokerOrderResult(
                success=False,
                order_id="",
                external_id=request.external_id or "",
                symbol=request.symbol,
                side=request.side,
                status=BrokerOrderStatus.FAILED,
                error_message=str(exc),
            )

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected:
            return False
        try:
            response = requests.delete(
                f"{self.base_url}/orders/{order_id}",
                headers=self.headers,
                timeout=self.timeout_seconds,
            )
            return response.status_code == 204
        except Exception as exc:
            logger.error("Failed to cancel Alpaca order %s: %s", order_id, exc)
            return False
