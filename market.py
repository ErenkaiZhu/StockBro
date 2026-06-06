from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from accounting import (
    capture_trade_snapshot,
    ensure_agent_non_negative,
    validate_trade_accounting,
)
from config import MarketConfig
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

    def expire(
        self,
        *,
        date: int,
        session: int,
        sessions_per_day: int,
        ttl_sessions: int,
    ) -> list[dict]:
        if ttl_sessions <= 0:
            return []
        now = self._session_index(date, session, sessions_per_day)
        expired = []
        self.buy = self._keep_active(self.buy, now, ttl_sessions, expired)
        self.sell = self._keep_active(self.sell, now, ttl_sessions, expired)
        return expired

    def add(self, action: dict, *, date: int, session: int, sessions_per_day: int) -> None:
        order = action.copy()
        order["created_date"] = date
        order["created_session"] = session
        order["created_index"] = self._session_index(date, session, sessions_per_day)
        if order["action_type"] == "buy":
            self.buy.append(order)
            self.buy.sort(key=lambda item: (-item["price"], item["created_index"]))
        else:
            self.sell.append(order)
            self.sell.sort(key=lambda item: (item["price"], item["created_index"]))

    def snapshot(self, depth_levels: int = 5) -> dict:
        buy_orders = [order.copy() for order in self.buy]
        sell_orders = [order.copy() for order in self.sell]
        best_bid = max((order["price"] for order in buy_orders), default=None)
        best_ask = min((order["price"] for order in sell_orders), default=None)
        spread = None
        spread_pct = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            midpoint = (best_bid + best_ask) / 2
            spread_pct = spread / midpoint if midpoint else None

        return {
            "buy": buy_orders,
            "sell": sell_orders,
            "depth": {
                "buy": self._depth_levels(buy_orders, reverse=True, limit=depth_levels),
                "sell": self._depth_levels(sell_orders, reverse=False, limit=depth_levels),
            },
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "spread_pct": spread_pct,
        }

    @staticmethod
    def _keep_active(
        orders: list[dict],
        now: int,
        ttl_sessions: int,
        expired: list[dict],
    ) -> list[dict]:
        active = []
        for order in orders:
            if now - order.get("created_index", now) >= ttl_sessions:
                expired.append(order)
            else:
                active.append(order)
        return active

    @staticmethod
    def _session_index(date: int, session: int, sessions_per_day: int) -> int:
        return (date - 1) * sessions_per_day + session

    @staticmethod
    def _depth_levels(orders: list[dict], *, reverse: bool, limit: int) -> list[dict]:
        levels = {}
        for order in orders:
            levels[order["price"]] = levels.get(order["price"], 0) + order["amount"]
        sorted_prices = sorted(levels.keys(), reverse=reverse)
        return [
            {"price": price, "amount": levels[price]}
            for price in sorted_prices[:limit]
        ]


class MatchingEngine:
    def __init__(
        self,
        trade_recorder: Callable[..., None],
        *,
        market_config: Optional[MarketConfig] = None,
        trace_recorder: Optional[Callable[[str, dict], None]] = None,
        sessions_per_day: int = 3,
    ):
        self.record_trade = trade_recorder
        self.market_config = market_config or MarketConfig()
        self.trace_recorder = trace_recorder
        self.sessions_per_day = sessions_per_day
        self.fee_pool = 0.0

    def expire_orders(self, order_book: OrderBook, *, date: int, session: int, stock_name: str) -> None:
        expired = order_book.expire(
            date=date,
            session=session,
            sessions_per_day=self.sessions_per_day,
            ttl_sessions=self.market_config.order_ttl_sessions,
        )
        for order in expired:
            self._trace("order_expired", {"date": date, "session": session, "stock": stock_name, "order": order})

    def submit(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        *,
        date: int,
        session: int,
    ) -> list[dict]:
        if not self._can_accept_order(action, agents_by_id, stock.name, date, session):
            return []
        if not stock.is_price_allowed(action["price"], self.market_config.daily_price_limit_pct):
            lower, upper = stock.price_bounds(self.market_config.daily_price_limit_pct)
            self._trace(
                "order_rejected",
                {
                    "date": date,
                    "session": session,
                    "stock": stock.name,
                    "reason": "daily_price_limit",
                    "price": action["price"],
                    "lower_limit": lower,
                    "upper_limit": upper,
                    "order": action,
                },
            )
            return []

        if action["action_type"] == "buy":
            trades = self._submit_buy(action, order_book, agents_by_id, stock, date, session)
        elif action["action_type"] == "sell":
            trades = self._submit_sell(action, order_book, agents_by_id, stock, date, session)
        else:
            trades = []
        return trades

    def _can_accept_order(
        self,
        action: dict,
        agents_by_id: dict[int, object],
        stock_name: str,
        date: int,
        session: int,
    ) -> bool:
        agent = agents_by_id.get(action["agent"])
        if agent is None:
            self._trace("order_rejected", {"date": date, "session": session, "reason": "unknown_agent", "order": action})
            return False
        if action["action_type"] == "buy":
            if not agent.can_buy(action["amount"], action["price"], self.market_config.transaction_fee_rate):
                self._trace("order_rejected", {"date": date, "session": session, "reason": "insufficient_cash_for_fee", "order": action})
                return False
        elif action["action_type"] == "sell":
            if not agent.can_sell(stock_name, action["amount"]):
                self._trace("order_rejected", {"date": date, "session": session, "reason": "insufficient_holdings", "order": action})
                return False
        return True

    def _submit_buy(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        date: int,
        session: int,
    ) -> list[dict]:
        trades = []
        for sell_order in order_book.sell[:]:
            if not stock.is_price_allowed(sell_order["price"], self.market_config.daily_price_limit_pct):
                order_book.sell.remove(sell_order)
                self._trace("order_rejected", {"date": date, "session": session, "reason": "resting_order_outside_limit", "order": sell_order})
                continue
            if sell_order["price"] > action["price"]:
                continue

            execution_price = self._execution_price(
                resting_price=sell_order["price"],
                incoming_limit=action["price"],
                incoming_side="buy",
                amount=min(action["amount"], sell_order["amount"]),
                stock=stock,
            )
            if execution_price is None:
                continue

            close_amount = self._close_amount(action, sell_order, agents_by_id, stock.name, execution_price)
            if close_amount <= 0:
                order_book.sell.remove(sell_order)
                continue

            trade = self._execute_trade(
                buyer_id=action["agent"],
                seller_id=sell_order["agent"],
                agents_by_id=agents_by_id,
                stock=stock,
                amount=close_amount,
                price=execution_price,
                resting_price=sell_order["price"],
                date=date,
                session=session,
            )
            if trade is not None:
                trades.append(trade)
            action["amount"] -= close_amount
            sell_order["amount"] -= close_amount
            if sell_order["amount"] <= 0:
                order_book.sell.remove(sell_order)
            if action["amount"] <= 0:
                return trades

        order_book.add(action, date=date, session=session, sessions_per_day=self.sessions_per_day)
        self._trace("order_added", {"date": date, "session": session, "stock": stock.name, "order": action})
        return trades

    def _submit_sell(
        self,
        action: dict,
        order_book: OrderBook,
        agents_by_id: dict[int, object],
        stock: Stock,
        date: int,
        session: int,
    ) -> list[dict]:
        trades = []
        for buy_order in order_book.buy[:]:
            if not stock.is_price_allowed(buy_order["price"], self.market_config.daily_price_limit_pct):
                order_book.buy.remove(buy_order)
                self._trace("order_rejected", {"date": date, "session": session, "reason": "resting_order_outside_limit", "order": buy_order})
                continue
            if buy_order["price"] < action["price"]:
                continue

            execution_price = self._execution_price(
                resting_price=buy_order["price"],
                incoming_limit=action["price"],
                incoming_side="sell",
                amount=min(action["amount"], buy_order["amount"]),
                stock=stock,
            )
            if execution_price is None:
                continue

            close_amount = self._close_amount(buy_order, action, agents_by_id, stock.name, execution_price)
            if close_amount <= 0:
                order_book.buy.remove(buy_order)
                continue

            trade = self._execute_trade(
                buyer_id=buy_order["agent"],
                seller_id=action["agent"],
                agents_by_id=agents_by_id,
                stock=stock,
                amount=close_amount,
                price=execution_price,
                resting_price=buy_order["price"],
                date=date,
                session=session,
            )
            if trade is not None:
                trades.append(trade)
            buy_order["amount"] -= close_amount
            action["amount"] -= close_amount
            if buy_order["amount"] <= 0:
                order_book.buy.remove(buy_order)
            if action["amount"] <= 0:
                return trades

        order_book.add(action, date=date, session=session, sessions_per_day=self.sessions_per_day)
        self._trace("order_added", {"date": date, "session": session, "stock": stock.name, "order": action})
        return trades

    def _execution_price(
        self,
        *,
        resting_price: float,
        incoming_limit: float,
        incoming_side: str,
        amount: int,
        stock: Stock,
    ) -> Optional[float]:
        depth_factor = min(1.0, amount / max(1, self.market_config.max_fill_per_price_level))
        slippage = resting_price * self.market_config.slippage_rate * depth_factor
        if incoming_side == "buy":
            price = min(incoming_limit, resting_price + slippage)
            if price < resting_price:
                return None
        else:
            price = max(incoming_limit, resting_price - slippage)
            if price > resting_price:
                return None

        price = round(price, 6)
        if not stock.is_price_allowed(price, self.market_config.daily_price_limit_pct):
            return None
        return price

    def _close_amount(
        self,
        buy_order: dict,
        sell_order: dict,
        agents_by_id: dict[int, object],
        stock_name: str,
        trade_price: float,
    ) -> int:
        buyer = agents_by_id.get(buy_order["agent"])
        seller = agents_by_id.get(sell_order["agent"])
        if buyer is None or trade_price <= 0:
            return 0

        fee_rate = self.market_config.transaction_fee_rate
        buyer_affordable_amount = int(buyer.cash // (trade_price * (1 + fee_rate)))
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
                self.market_config.max_fill_per_price_level,
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
        resting_price: float,
        date: int,
        session: int,
    ) -> Optional[dict]:
        buyer = agents_by_id[buyer_id]
        seller = agents_by_id.get(seller_id)
        fee_rate = self.market_config.transaction_fee_rate
        buyer_fee = amount * price * fee_rate
        seller_fee = amount * price * fee_rate if seller_id != ADMIN_AGENT_ID else 0.0
        before = capture_trade_snapshot(
            buyer=buyer,
            seller=seller if seller_id != ADMIN_AGENT_ID else None,
            stock_name=stock.name,
            fee_pool=self.fee_pool,
        )

        if not buyer.can_buy(amount, price, fee_rate):
            log.logger.warning("Trade skipped because buyer %s failed validation.", buyer_id)
            return None
        if seller_id != ADMIN_AGENT_ID and (seller is None or not seller.can_sell(stock.name, amount)):
            log.logger.warning("Trade skipped because seller %s failed validation.", seller_id)
            return None

        buyer.buy_stock(stock.name, amount, price, fee_rate)
        if seller_id != ADMIN_AGENT_ID and seller is not None:
            seller.sell_stock(stock.name, amount, price, fee_rate)
        self.fee_pool += buyer_fee + seller_fee

        after = capture_trade_snapshot(
            buyer=buyer,
            seller=seller if seller_id != ADMIN_AGENT_ID else None,
            stock_name=stock.name,
            fee_pool=self.fee_pool,
        )
        ensure_agent_non_negative(buyer)
        if seller is not None:
            ensure_agent_non_negative(seller)
        validate_trade_accounting(
            before=before,
            after=after,
            amount=amount,
            price=price,
            buyer_fee=buyer_fee,
            seller_fee=seller_fee,
        )

        gross_value = amount * price
        slippage = price - resting_price
        trade = {
            "date": date,
            "session": session,
            "stock": stock.name,
            "buyer": buyer_id,
            "seller": seller_id,
            "amount": amount,
            "price": price,
            "gross_value": gross_value,
            "buyer_fee": buyer_fee,
            "seller_fee": seller_fee,
            "slippage": slippage,
        }
        stock.add_session_deal(trade)
        self.record_trade(
            date,
            session,
            stock.name,
            buyer_id,
            seller_id,
            amount,
            price,
            gross_value,
            buyer_fee,
            seller_fee,
            slippage,
        )
        self._trace("trade_executed", trade)
        log.logger.info(
            "ACTION - BUY:%s, SELL:%s, STOCK:%s, PRICE:%s, AMOUNT:%s",
            buyer_id,
            seller_id,
            stock.name,
            price,
            amount,
        )
        return trade

    def _trace(self, event_type: str, payload: dict) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder(event_type, payload)
