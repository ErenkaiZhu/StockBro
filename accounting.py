from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


EPSILON = 1e-6


@dataclass(frozen=True)
class AgentTradeState:
    cash: float
    holding: int


@dataclass(frozen=True)
class TradeSnapshot:
    buyer: AgentTradeState
    seller: Optional[AgentTradeState]
    fee_pool: float


def capture_trade_snapshot(
    *,
    buyer: object,
    seller: Optional[object],
    stock_name: str,
    fee_pool: float,
) -> TradeSnapshot:
    return TradeSnapshot(
        buyer=AgentTradeState(cash=buyer.cash, holding=buyer.holding(stock_name)),
        seller=(
            AgentTradeState(cash=seller.cash, holding=seller.holding(stock_name))
            if seller is not None
            else None
        ),
        fee_pool=fee_pool,
    )


def ensure_agent_non_negative(agent: object) -> None:
    if agent.cash < -EPSILON:
        raise RuntimeError(f"Agent {getattr(agent, 'order', '?')} has negative cash: {agent.cash}")
    for stock_name in ("A", "B"):
        if agent.holding(stock_name) < 0:
            raise RuntimeError(
                f"Agent {getattr(agent, 'order', '?')} has negative {stock_name} holdings: "
                f"{agent.holding(stock_name)}"
            )


def validate_trade_accounting(
    *,
    before: TradeSnapshot,
    after: TradeSnapshot,
    amount: int,
    price: float,
    buyer_fee: float,
    seller_fee: float,
) -> None:
    gross_value = amount * price
    _close(
        after.buyer.cash,
        before.buyer.cash - gross_value - buyer_fee,
        "buyer cash",
    )
    if after.buyer.holding != before.buyer.holding + amount:
        raise RuntimeError("Buyer holdings did not increase by traded amount.")

    if before.seller is not None and after.seller is not None:
        _close(
            after.seller.cash,
            before.seller.cash + gross_value - seller_fee,
            "seller cash",
        )
        if after.seller.holding != before.seller.holding - amount:
            raise RuntimeError("Seller holdings did not decrease by traded amount.")

    _close(after.fee_pool, before.fee_pool + buyer_fee + seller_fee, "fee pool")


def _close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > EPSILON:
        raise RuntimeError(f"{label} invariant failed: actual={actual}, expected={expected}")
