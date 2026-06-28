# -*- coding: utf-8 -*-
"""
broker_provider — Multi-broker abstraction layer for trade execution.

Provides a unified interface and concrete adapters:
- IBKR (via ib_insync)
- Mock (simulation for testing / dry-run)
"""
from __future__ import annotations

from .base import BaseBroker
from .order import (
    BrokerAccountInfo,
    BrokerConnectionConfig,
    BrokerOrderStatus,
    OrderSide,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPosition,
    BrokerError,
    BrokerAuthError,
    BrokerConnectionError,
    BrokerOrderRejectedError,
)
from .factory import (
    create_broker,
    PROVIDER_IBKR as BROKER_IBKR,
    PROVIDER_MOCK as BROKER_MOCK,
    PROVIDER_ALPACA as BROKER_ALPACA,
)
from .sync import sync_positions_to_local_db, get_broker_positions_summary

__all__ = [
    "BaseBroker",
    "BrokerAccountInfo",
    "BrokerConnectionConfig",
    "BrokerOrderStatus",
    "OrderSide",
    "BrokerOrderRequest",
    "BrokerOrderResult",
    "BrokerPosition",
    "BrokerError",
    "BrokerAuthError",
    "BrokerConnectionError",
    "BrokerOrderRejectedError",
    "create_broker",
    "BROKER_IBKR",
    "BROKER_MOCK",
    "BROKER_ALPACA",
    "sync_positions_to_local_db",
    "get_broker_positions_summary",
]
