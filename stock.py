from __future__ import annotations

from dataclasses import dataclass, field

from config import SimulationConfig


@dataclass
class Stock:
    name: str
    price: float
    initial_stock: int = 0
    is_new: bool = False
    history: dict[int, list[dict]] = field(default_factory=dict)
    session_deals: list[dict] = field(default_factory=list)

    def financial_report(self, config: SimulationConfig, index: int) -> str:
        if self.name == "A":
            return config.financial_reports_a[index]
        if self.name == "B":
            return config.financial_reports_b[index]
        raise ValueError(f"Unknown stock name: {self.name}")

    def add_session_deal(self, price_and_amount: dict) -> None:
        self.session_deals.append(price_and_amount)

    def update_price(self, date: int) -> None:
        if not self.session_deals:
            return
        self.price = self.session_deals[-1]["price"]
        self.history.setdefault(date, []).extend(deal.copy() for deal in self.session_deals)
        self.session_deals.clear()
