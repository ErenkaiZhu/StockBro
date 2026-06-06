from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import SimulationConfig


@dataclass
class Stock:
    name: str
    price: float
    initial_stock: int = 0
    is_new: bool = False
    day_open_price: Optional[float] = None
    history: dict[int, list[dict]] = field(default_factory=dict)
    session_deals: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.day_open_price is None:
            self.day_open_price = self.price

    def start_day(self) -> None:
        self.day_open_price = self.price

    def financial_report(self, config: SimulationConfig, index: int) -> str:
        if self.name == "A":
            return config.financial_reports_a[index]
        if self.name == "B":
            return config.financial_reports_b[index]
        raise ValueError(f"Unknown stock name: {self.name}")

    def add_session_deal(self, price_and_amount: dict) -> None:
        self.session_deals.append(price_and_amount)

    def price_bounds(self, daily_price_limit_pct: float) -> tuple[float, float]:
        if daily_price_limit_pct <= 0:
            return 0.0, float("inf")
        lower = self.day_open_price * (1 - daily_price_limit_pct)
        upper = self.day_open_price * (1 + daily_price_limit_pct)
        return lower, upper

    def is_price_allowed(self, price: float, daily_price_limit_pct: float) -> bool:
        lower, upper = self.price_bounds(daily_price_limit_pct)
        return lower <= price <= upper

    def update_price(self, date: int) -> None:
        if not self.session_deals:
            return
        self.price = self.session_deals[-1]["price"]
        self.history.setdefault(date, []).extend(deal.copy() for deal in self.session_deals)
        self.session_deals.clear()
