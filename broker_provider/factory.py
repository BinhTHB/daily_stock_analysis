# -*- coding: utf-8 -*-
"""Broker factory: resolve provider name to a concrete broker instance."""
from __future__ import annotations

import logging
from typing import Optional

from .order import BrokerConnectionConfig
from .base import BaseBroker
from .ibkr_adapter import IBKRAdapter
from .mock import MockBroker

logger = logging.getLogger(__name__)

# Provider identifiers
PROVIDER_IBKR = "ibkr"
PROVIDER_MOCK = "mock"

SUPPORTED_BROKERS = {PROVIDER_IBKR, PROVIDER_MOCK}


class BrokerNotFoundError(ValueError):
    """Raised when the requested broker provider is not supported."""


def create_broker(
    provider: str,
    *,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    client_id: int = 1,
    account_id: Optional[str] = None,
    timeout_seconds: float = 30.0,
    simulate: bool = False,
) -> BaseBroker:
    """
    Factory function — returns an instance of the requested broker adapter.

    If ``simulate=True`` and the provider would attempt a real connection,
    return a MockBroker instead (safety override).
    """
    normalized = provider.strip().lower()

    if normalized == PROVIDER_IBKR:
        resolved = PROVIDER_MOCK if simulate else PROVIDER_IBKR
    else:
        resolved = normalized

    if resolved not in SUPPORTED_BROKERS:
        raise BrokerNotFoundError(
            f"Unsupported broker provider: {provider!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_BROKERS))}"
        )

    if resolved == PROVIDER_MOCK:
        logger.info("Using MockBroker (simulation mode)")
        return MockBroker()

    if resolved == PROVIDER_IBKR:
        effective_port = port or 7497  # default TWS paper
        config = BrokerConnectionConfig(
            host=host,
            port=effective_port,
            client_id=int(client_id),
            account_id=account_id,
            timeout_seconds=timeout_seconds,
        )
        logger.info(
            "Connecting to IBKR TWS/Gateway at %s:%s (client_id=%s)",
            host,
            effective_port,
            client_id,
        )
        return IBKRAdapter(config)
