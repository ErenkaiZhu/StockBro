from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from log.custom_logger import log
from stock import Stock


ADMIN_AGENT_ID = -1


@dataclass
class OrderBook:
    buy: list[dict] = field(default_factory=list)
    sell: list[dict] = field(default_factory=list)

    def clear(self) -> None:
        self.buy.clear()
        self.sell.clear()

    def snapshot(self) -> dict[str, list[dict]]:
        return {
            "buy": [order.copy() for order in self.buy],
            "sell": [order.copy() for order in self.sell],
        }


class MatchingEngine:
    def __init__(self, trade_recorder: Callable[..., None]):
        self.record_trade = trade_recorder

    def submit(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        *,
        date: int,
        session: int,
    ) -> None:
        action_type = action["action_type"]
        if action_type == "buy":
            self._submit_buy(action, order_book, agents_by_id, stock, date, session)
        elif action_type == "sell":
            self._submit_sell(action, order_book, agents_by_id, stock, date, session)

    def _submit_buy(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        date: int,
        session: int,
    ) -> None:
        for sell_order in order_book.sell[:]:
            if sell_order["price"] > action["price"]:
                continue

            trade_price = sell_order["price"]
            close_amount = self._close_amount(
                action,
                sell_order,
                agents_by_id,
                stock.name,
                trade_price,
            )
            if close_amount <= 0:
                order_book.sell.remove(sell_order)
                continue

            self._execute_trade(
                buyer_id=action["agent"],
                seller_id=sell_order["agent"],
                agents_by_id=agents_by_id,
                stock=stock,
                amount=close_amount,
                price=trade_price,
                date=date,
                session=session,
            )
            action["amount"] -= close_amount
            sell_order["amount"] -= close_amount
            if sell_order["amount"] <= 0:
                order_book.sell.remove(sell_order)
            if action["amount"] <= 0:
                return

        order_book.buy.append(action)

    def _submit_sell(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        date: int,
        session: int,
    ) -> None:
        for buy_order in order_book.buy[:]:
            if buy_order["price"] < action["price"]:
                continue

            trade_price = buy_order["price"]
            close_amount = self._close_amount(
                buy_order,
                action,
                agents_by_id,
                stock.name,
                trade_price,
            )
            if close_amount <= 0:
                order_book.buy.remove(buy_order)
                continue

            self._execute_trade(
                buyer_id=buy_order["agent"],
                seller_id=action["agent"],
                agents_by_id=agents_by_id,
                stock=stock,
                amount=close_amount,
                price=trade_price,
                date=date,
                session=session,
            )
            buy_order["amount"] -= close_amount
            action["amount"] -= close_amount
            if buy_order["amount"] <= 0:
                order_book.buy.remove(buy_order)
            if action["amount"] <= 0:
                return

        order_book.sell.append(action)

    @staticmethod
    def _close_amount(
        buy_order: dict,
        sell_order: dict,
        agents_by_id: dict[int, object],
        stock_name: str,
        trade_price: float,
    ) -> int:
        buyer = agents_by_id.get(buy_order["agent"])
        seller = agents_by_id.get(sell_order["agent"])
        if buyer is None:
            return 0

        buyer_affordable_amount = int(buyer.cash // trade_price)
        seller_available_amount = sell_order["amount"]
        if sell_order["agent"] != ADMIN_AGENT_ID:
            if seller is None:
                return 0
            seller_available_amount = seller.holding(stock_name)

        return max(
            0,
            min(
                buy_order["amount"],
                sell_order["amount"],
                buyer_affordable_amount,
                seller_available_amount,
            ),
        )

    def _execute_trade(
        self,
        *,
        buyer_id: int,
        seller_id: int,
        agents_by_id: dict[int, object],
        stock: Stock,
        amount: int,
        price: float,
        date: int,
        session: int,
    ) -> None:
        buyer = agents_by_id[buyer_id]
        seller = agents_by_id.get(seller_id)

        if not buyer.buy_stock(stock.name, amount, price):
            log.logger.warning("Trade skipped because buyer %s failed validation.", buyer_id)
            return
        if seller_id != ADMIN_AGENT_ID and seller is not None:
            if not seller.sell_stock(stock.name, amount, price):
                buyer.sell_stock(stock.name, amount, price)
                log.logger.warning("Trade skipped because seller %s failed validation.", seller_id)
                return

        stock.add_session_deal({"price": price, "amount": amount})
        self.record_trade(date, session, stock.name, buyer_id, seller_id, amount, price)
        log.logger.info(
            "ACTION - BUY:%s, SELL:%s, STOCK:%s, PRICE:%s, AMOUNT:%s",
            buyer_id,
            seller_id,
            stock.name,
            price,
            amount,
        )
