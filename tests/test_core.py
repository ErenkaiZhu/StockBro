import unittest

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

    def buy_stock(self, stock_name, amount, price):
        if self.cash < amount * price:
            return False
        self.cash -= amount * price
        if stock_name == "A":
            self.stock_a_amount += amount
        else:
            self.stock_b_amount += amount
        return True

    def sell_stock(self, stock_name, amount, price):
        if self.holding(stock_name) < amount:
            return False
        if stock_name == "A":
            self.stock_a_amount -= amount
        else:
            self.stock_b_amount -= amount
        self.cash += amount * price
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


class MatchingEngineTest(unittest.TestCase):
    def test_buy_limit_crosses_existing_sell_order(self):
        records = []
        engine = MatchingEngine(lambda *row: records.append(row))
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
        self.assertEqual(records, [(1, 1, "A", 1, 2, 3, 10.0)])


if __name__ == "__main__":
    unittest.main()
