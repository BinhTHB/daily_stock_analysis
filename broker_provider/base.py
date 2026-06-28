# -*- coding: utf-8 -*-
"""Base abstract class for all brokers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .order import (
    BrokerAccountInfo,
    BrokerConnectionConfig,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPosition,
)


class BaseBroker(ABC):
    """
    Unified abstract interface for executing trades and querying account status.
    """

    def __init__(self, config: BrokerConnectionConfig) -> None:
        self.config = config

    @abstractmethod
    def connect(self) -> None:
        """Establish connection with broker api/gateway."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down broker connection."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connection is alive, False otherwise."""

    @abstractmethod
    def get_account_info(self) -> BrokerAccountInfo:
        """Fetch account balance, buying power, and paper trading state."""

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        """Fetch active positions in broker account."""

    @abstractmethod
    def execute_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        """Submit trade order to the broker and block until filled, rejected or timeout."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Attempt to cancel an active order."""
