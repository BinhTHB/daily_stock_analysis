# -*- coding: utf-8 -*-
"""
Order schemas and broker abstractions for trade execution.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class BrokerOrderStatus(str, enum.Enum):
    PENDING = "pending"          # Created locally, not yet sent
    SUBMITTED = "submitted"      # Sent to broker, awaiting fill
    PARTIALLY_FILLED = "partial" # Some shares filled
    FILLED = "filled"            # Fully filled
    CANCELLED = "cancelled"      # Cancelled before fill
    REJECTED = "rejected"        # Rejected by broker
    FAILED = "failed"            # Transmission error


@dataclass(frozen=True)
class BrokerConnectionConfig:
    """Connection parameters for a broker adapter."""
    host: str = "127.0.0.1"
    port: int = 7497              # TWS Paper: 7497, Live: 7496; Gateway Paper: 4002, Live: 4001
    client_id: int = 1
    account_id: Optional[str] = None  # IBKR account number (optional, for multi-account)
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class BrokerAccountInfo:
    """Read-only snapshot of broker account."""
    account_id: str
    cash_balance: float
    total_value: float
    buying_power: float
    currency: str = "USD"
    is_paper: bool = True
    last_updated: Optional[datetime] = None


@dataclass(frozen=True)
class BrokerOrderRequest:
    """Request to place an order."""
    side: OrderSide
    symbol: str
    quantity: float
    order_type: str = "MKT"       # MKT / LMT / STPLMT
    limit_price: Optional[float] = None
    time_in_force: str = "DAY"    # DAY / GTC / IOC
    external_id: Optional[str] = None  # Broker-assigned order id after placement
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerPosition:
    """Current position held in broker account."""
    symbol: str
    quantity: float
    market_price: float
    cost_basis: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    currency: str = "USD"
    account_id: Optional[str] = None


@dataclass(frozen=True)
class BrokerOrderResult:
    """Result of an order execution attempt."""
    success: bool
    order_id: str                # Broker-assigned order identifier
    external_id: str             # Our request identifier
    symbol: str
    side: OrderSide
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    status: BrokerOrderStatus = BrokerOrderStatus.FAILED
    commission: float = 0.0
    error_message: Optional[str] = None
    # For pending/partial orders, these reflect the partially filled state
    remaining_quantity: float = 0.0
    filled_at: Optional[datetime] = None


class BrokerError(Exception):
    """Base exception for broker operations."""


class BrokerAuthError(BrokerError):
    """Authentication/connection refused by broker."""


class BrokerConnectionError(BrokerError):
    """Cannot reach broker gateway."""


class BrokerOrderRejectedError(BrokerError):
    """Order rejected by broker risk/validation."""
