# -*- coding: utf-8 -*-
"""
Sync utility: fetch IBKR positions and align them with the local Portfolio DB.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from .base import BaseBroker
from .order import BrokerPosition

logger = logging.getLogger(__name__)

try:
    from src.services.portfolio_service import PortfolioService
except ImportError:
    PortfolioService = None  # type: ignore


def sync_positions_to_local_db(
    broker: BaseBroker,
    portfolio_account_id: int,
    *,
    portfolio_service: Optional[object] = None,
) -> Tuple[int, int, int]:
    """
    Fetch all positions from ``broker`` and reconcile them with the local
    Portfolio DB for the given ``portfolio_account_id``.

    Returns (added, updated, unchanged).
    """
    if PortfolioService is None:
        logger.error("PortfolioService not available; cannot sync to DB")
        return (0, 0, 0)

    svc = portfolio_service or PortfolioService()
    remote = broker.get_positions()

    added = updated = unchanged = 0
    remote_symbols = set()

    for pos in remote:
        remote_symbols.add(pos.symbol)
        # Check if this position already exists
        local_positions = svc.list_positions(account_id=portfolio_account_id)
        found = [lp for lp in local_positions if lp.get("symbol") == pos.symbol]

        if not found:
            # Add trade to mirror broker position (lazy approach: record as a buy event)
            try:
                svc.add_trade(
                    account_id=portfolio_account_id,
                    symbol=pos.symbol,
                    market=detect_market(pos.symbol),
                    currency=pos.currency,
                    side="buy",
                    quantity=pos.quantity,
                    price=pos.cost_basis,
                    fee=0.0,
                    tax=0.0,
                    note=f"Imported from broker sync (unrealized P&L: {pos.unrealized_pnl:.2f})",
                )
                added += 1
            except Exception:
                logger.exception("Failed to sync position %s", pos.symbol)
        else:
            unchanged += 1

    return (added, updated, unchanged)


def detect_market(symbol: str) -> str:
    """Heuristic: IBKR symbols are uppercase; try to detect market."""
    if len(symbol) <= 4 and symbol.isalpha():
        # Likely US stock
        return "us"
    if symbol.startswith("0") or symbol.startswith("3") or symbol.startswith("6"):
        return "cn"
    if symbol.endswith(".HK") or symbol.endswith(".hk"):
        return "hk"
    return "us"


def get_broker_positions_summary(
    broker: BaseBroker,
) -> str:
    """
    Return a human-readable summary of all positions for use in reports.
    """
    try:
        positions = broker.get_positions()
    except Exception as exc:
        return f"⚠️ Cannot fetch positions: {exc}"

    if not positions:
        return "No open positions."

    lines = ["**Current Positions:**"]
    total_market = 0.0
    total_pnl = 0.0
    for p in positions:
        market_value = p.quantity * p.market_price
        total_market += market_value
        total_pnl += p.unrealized_pnl
        lines.append(
            f"- {p.symbol}: {p.quantity:.2f} @ {p.market_price:.2f} "
            f"(value={market_value:.2f}, P&L={p.unrealized_pnl:+.2f})"
        )
    lines.append(f"- **Total Value**: {total_market:.2f}")
    lines.append(f"- **Unrealized P&L**: {total_pnl:+.2f}")
    return "\n".join(lines)
