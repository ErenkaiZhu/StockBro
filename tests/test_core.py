import unittest

from config import MarketConfig
from market import MatchingEngine, OrderBook
from secretary import Secretary
from stock import Stock


class FakeAgent:
    def __init__(self, cash=0, stock_a=0, stock_b=0):
        self.cash = cash
        self.stock_a_amount = stock_a
        self.stock_b_amount = stock_b
        self.quit = False

    def holding(self, stock_name):
        if stock_name == "A":
            return self.stock_a_amount
        return self.stock_b_amount

    def can_buy(self, amount, price, fee_rate=0.0):
        return self.cash >= amount * price * (1 + fee_rate)

    def can_sell(self, stock_name, amount):
        return self.holding(stock_name) >= amount

    def buy_stock(self, stock_name, amount, price, fee_rate=0.0):
        if not self.can_buy(amount, price, fee_rate):
            return False
        self.cash -= amount * price * (1 + fee_rate)
        if stock_name == "A":
            self.stock_a_amount += amount
        else:
            self.stock_b_amount += amount
        return True

    def sell_stock(self, stock_name, amount, price, fee_rate=0.0):
        if not self.can_sell(stock_name, amount):
            return False
        if stock_name == "A":
            self.stock_a_amount -= amount
        else:
            self.stock_b_amount -= amount
        self.cash += amount * price * (1 - fee_rate)
        return True


class SecretaryTest(unittest.TestCase):
    def test_extracts_action_json_from_text(self):
        secretary = Secretary()
        ok, fail_response, action = secretary.check_action(
            'Here is my order: {"action_type": "buy", "stock": "A", "amount": 2, "price": 30}',
            cash=100,
            stock_a_amount=0,
            stock_b_amount=0,
            stock_a_price=30,
            stock_b_price=40,
        )

        self.assertTrue(ok, fail_response)
        self.assertEqual(action["action_type"], "buy")
        self.assertEqual(action["amount"], 2)
        self.assertEqual(action["price"], 30.0)

    def test_rejects_oversell(self):
        secretary = Secretary()
        ok, fail_response, action = secretary.check_action(
            '{"action_type": "sell", "stock": "B", "amount": 3, "price": 40}',
            cash=100,
            stock_a_amount=0,
            stock_b_amount=2,
            stock_a_price=30,
            stock_b_price=40,
        )

        self.assertFalse(ok)
        self.assertIsNone(action)
        self.assertIn("should not exceed", fail_response)

    def test_accepts_structured_forum_message(self):
        secretary = Secretary()
        ok, fail_response, message = secretary.check_message('{"message": "Stay liquid."}')

        self.assertTrue(ok, fail_response)
        self.assertEqual(message["message"], "Stay liquid.")


class MatchingEngineTest(unittest.TestCase):
    def test_buy_limit_crosses_existing_sell_order(self):
        records = []
        engine = MatchingEngine(
            lambda *row: records.append(row),
            market_config=MarketConfig(
                transaction_fee_rate=0.0,
                slippage_rate=0.0,
                daily_price_limit_pct=0.0,
            ),
        )
        order_book = OrderBook()
        order_book.sell.append({
            "agent": 2,
            "action_type": "sell",
            "stock": "A",
            "amount": 5,
            "price": 10.0,
        })
        agents = {
            1: FakeAgent(cash=100),
            2: FakeAgent(cash=0, stock_a=5),
        }
        stock = Stock("A", 12.0)

        engine.submit(
            {
                "agent": 1,
                "action_type": "buy",
                "stock": "A",
                "amount": 3,
                "price": 12.0,
            },
            order_book,
            agents,
            stock,
            date=1,
            session=1,
        )

        self.assertEqual(agents[1].cash, 70)
        self.assertEqual(agents[1].stock_a_amount, 3)
        self.assertEqual(agents[2].cash, 30)
        self.assertEqual(agents[2].stock_a_amount, 2)
        self.assertEqual(order_book.sell[0]["amount"], 2)
        self.assertEqual(records, [(1, 1, "A", 1, 2, 3, 10.0, 30.0, 0.0, 0.0, 0.0)])

    def test_trade_fees_are_accounted_for(self):
        records = []
        engine = MatchingEngine(
            lambda *row: records.append(row),
            market_config=MarketConfig(transaction_fee_rate=0.01, slippage_rate=0.0),
        )
        order_book = OrderBook()
        order_book.sell.append({
            "agent": 2,
            "action_type": "sell",
            "stock": "A",
            "amount": 3,
            "price": 10.0,
        })
        agents = {
            1: FakeAgent(cash=100),
            2: FakeAgent(cash=0, stock_a=3),
        }
        stock = Stock("A", 10.0)

        engine.submit(
            {
                "agent": 1,
                "action_type": "buy",
                "stock": "A",
                "amount": 3,
                "price": 10.0,
            },
            order_book,
            agents,
            stock,
            date=1,
            session=1,
        )

        self.assertAlmostEqual(agents[1].cash, 69.7)
        self.assertEqual(agents[1].stock_a_amount, 3)
        self.assertAlmostEqual(agents[2].cash, 29.7)
        self.assertEqual(agents[2].stock_a_amount, 0)
        self.assertAlmostEqual(engine.fee_pool, 0.6)

    def test_daily_price_limit_rejects_outside_order(self):
        traces = []
        engine = MatchingEngine(
            lambda *row: None,
            market_config=MarketConfig(daily_price_limit_pct=0.10),
            trace_recorder=lambda event_type, payload: traces.append((event_type, payload)),
        )
        stock = Stock("A", 100.0)
        stock.start_day()
        order_book = OrderBook()

        trades = engine.submit(
            {
                "agent": 1,
                "action_type": "buy",
                "stock": "A",
                "amount": 1,
                "price": 120.0,
            },
            order_book,
            {1: FakeAgent(cash=1_000)},
            stock,
            date=1,
            session=1,
        )

        self.assertEqual(trades, [])
        self.assertEqual(order_book.buy, [])
        self.assertEqual(traces[0][0], "order_rejected")
        self.assertEqual(traces[0][1]["reason"], "daily_price_limit")

    def test_order_expiration(self):
        traces = []
        engine = MatchingEngine(
            lambda *row: None,
            market_config=MarketConfig(order_ttl_sessions=1),
            trace_recorder=lambda event_type, payload: traces.append((event_type, payload)),
            sessions_per_day=3,
        )
        order_book = OrderBook()
        order_book.add(
            {
                "agent": 1,
                "action_type": "buy",
                "stock": "A",
                "amount": 1,
                "price": 10.0,
            },
            date=1,
            session=1,
            sessions_per_day=3,
        )

        engine.expire_orders(order_book, date=1, session=2, stock_name="A")

        self.assertEqual(order_book.buy, [])
        self.assertEqual(traces[0][0], "order_expired")


if __name__ == "__main__":
    unittest.main()
