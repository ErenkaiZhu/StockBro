from __future__ import annotations

import math
import random

from config import SimulationConfig
from llm_client import LLMClient
from log.custom_logger import log
from prompt.agent_prompt import (
    render_loan_prompt,
    render_loan_retry_prompt,
    render_next_day_estimate_prompt,
    render_next_day_estimate_retry_prompt,
    render_post_message_prompt,
    render_stock_prompt,
    render_stock_retry_prompt,
)
from secretary import Secretary
from stock import Stock


DEFAULT_NO_LOAN = {"loan": "no"}
DEFAULT_NO_ACTION = {"action_type": "no"}
DEFAULT_NO_ESTIMATE = {
    "buy_A": "no",
    "buy_B": "no",
    "sell_A": "no",
    "sell_B": "no",
    "loan": "no",
}


def random_initial_state(
    config: SimulationConfig,
    stock_a_initial_price: float,
    stock_b_initial_price: float,
) -> tuple[int, int, float, dict]:
    while True:
        stock_a_amount = int(random.uniform(0, config.max_initial_property / stock_a_initial_price))
        stock_b_amount = int(random.uniform(0, config.max_initial_property / stock_b_initial_price))
        cash = random.uniform(0, config.max_initial_property)
        debt_amount = random.uniform(0, config.max_initial_property)
        total_property = (
            stock_a_amount * stock_a_initial_price
            + stock_b_amount * stock_b_initial_price
            + cash
        )
        if (
            config.min_initial_property <= total_property <= config.max_initial_property
            and debt_amount <= total_property
        ):
            break

    initial_debt = {
        "loan": "yes",
        "amount": debt_amount,
        "loan_type": random.randint(0, len(config.loan_types) - 1),
        "repayment_date": random.choice(config.repayment_days),
    }
    return stock_a_amount, stock_b_amount, cash, initial_debt


class Agent:
    def __init__(
        self,
        order: int,
        stock_a_price: float,
        stock_b_price: float,
        secretary: Secretary,
        llm_client: LLMClient,
        config: SimulationConfig,
    ):
        self.order = order
        self.secretary = secretary
        self.llm_client = llm_client
        self.config = config
        self.character = random.choice([
            "Conservative",
            "Aggressive",
            "Balanced",
            "Growth-Oriented",
        ])

        (
            self.stock_a_amount,
            self.stock_b_amount,
            self.cash,
            initial_debt,
        ) = random_initial_state(config, stock_a_price, stock_b_price)

        self.initial_property = self.total_property(stock_a_price, stock_b_price)
        self.chat_history: list[dict[str, str]] = []
        self.loans = [initial_debt]
        self.is_bankrupt = False
        self.quit = False

    def reset_daily_chat(self) -> None:
        self.chat_history.clear()

    def total_property(self, stock_a_price: float, stock_b_price: float) -> float:
        return self.stock_a_amount * stock_a_price + self.stock_b_amount * stock_b_price + self.cash

    def position_values(self, stock_a_price: float, stock_b_price: float) -> tuple[float, float, float, float]:
        stock_a_value = self.stock_a_amount * stock_a_price
        stock_b_value = self.stock_b_amount * stock_b_price
        proper = stock_a_value + stock_b_value + self.cash
        return proper, self.cash, stock_a_value, stock_b_value

    def total_loan(self) -> float:
        return sum(loan["amount"] for loan in self.loans)

    def holding(self, stock_name: str) -> int:
        if stock_name == "A":
            return self.stock_a_amount
        if stock_name == "B":
            return self.stock_b_amount
        raise ValueError(f"Unknown stock name: {stock_name}")

    def can_buy(self, amount: int, price: float) -> bool:
        return not self.quit and amount > 0 and self.cash >= amount * price

    def can_sell(self, stock_name: str, amount: int) -> bool:
        return not self.quit and amount > 0 and self.holding(stock_name) >= amount

    def buy_stock(self, stock_name: str, amount: int, price: float) -> bool:
        if not self.can_buy(amount, price) or stock_name not in {"A", "B"}:
            log.logger.warning("ILLEGAL STOCK BUY BEHAVIOR: agent=%s cash=%s", self.order, self.cash)
            return False

        self.cash -= amount * price
        if stock_name == "A":
            self.stock_a_amount += amount
        else:
            self.stock_b_amount += amount
        return True

    def sell_stock(self, stock_name: str, amount: int, price: float) -> bool:
        if not self.can_sell(stock_name, amount):
            log.logger.warning(
                "ILLEGAL STOCK SELL BEHAVIOR: agent=%s stock=%s holding=%s amount=%s",
                self.order,
                stock_name,
                self.holding(stock_name),
                amount,
            )
            return False

        if stock_name == "A":
            self.stock_a_amount -= amount
        else:
            self.stock_b_amount -= amount
        self.cash += amount * price
        return True

    def plan_loan(
        self,
        date: int,
        stock_a_price: float,
        stock_b_price: float,
        last_day_forum_message: list[dict],
        loan_rates: list[float],
    ) -> dict:
        if self.quit:
            return DEFAULT_NO_LOAN.copy()

        max_loan = self.initial_property - self.total_loan()
        if max_loan <= 0:
            return DEFAULT_NO_LOAN.copy()

        prompt = render_loan_prompt(
            date=date,
            character=self.character,
            stock_a_amount=self.stock_a_amount,
            stock_b_amount=self.stock_b_amount,
            cash=self.cash,
            loans=self.loans,
            max_loan=max_loan,
            loan_rates=loan_rates,
            stock_a_price=stock_a_price,
            stock_b_price=stock_b_price,
            last_day_forum_message=last_day_forum_message,
        )
        resp = self._ask(prompt)
        if not resp:
            return DEFAULT_NO_LOAN.copy()

        format_check, fail_response, loan = self.secretary.check_loan(resp, max_loan)
        retry_count = 0
        while not format_check:
            retry_count += 1
            if retry_count > 3:
                log.logger.warning("Loan JSON retry limit exceeded. Agent %s skips loan.", self.order)
                return DEFAULT_NO_LOAN.copy()
            resp = self._ask(render_loan_retry_prompt(fail_response))
            if not resp:
                return DEFAULT_NO_LOAN.copy()
            format_check, fail_response, loan = self.secretary.check_loan(resp, max_loan)

        if loan["loan"] == "yes":
            loan["repayment_date"] = date + self.config.loan_type_days[loan["loan_type"]]
            self.loans.append(loan)
            self.cash += loan["amount"]
            log.logger.info("INFO: Agent %s decides to loan: %s", self.order, loan)
        else:
            log.logger.info("INFO: Agent %s decides not to loan", self.order)
        return loan

    def plan_stock(
        self,
        date: int,
        session: int,
        stock_a: Stock,
        stock_b: Stock,
        stock_a_deals: dict,
        stock_b_deals: dict,
    ) -> dict:
        if self.quit:
            return DEFAULT_NO_ACTION.copy()

        stock_a_report = None
        stock_b_report = None
        if date in self.config.season_report_days and session == 1:
            report_index = self.config.season_report_days.index(date)
            stock_a_report = stock_a.financial_report(self.config, report_index)
            stock_b_report = stock_b.financial_report(self.config, report_index)

        prompt = render_stock_prompt(
            date=date,
            session=session,
            stock_a_amount=self.stock_a_amount,
            stock_b_amount=self.stock_b_amount,
            stock_a_price=stock_a.price,
            stock_b_price=stock_b.price,
            stock_a_deals=stock_a_deals,
            stock_b_deals=stock_b_deals,
            cash=self.cash,
            stock_a_report=stock_a_report,
            stock_b_report=stock_b_report,
            include_background=session == 1,
        )
        resp = self._ask(prompt)
        if not resp:
            return DEFAULT_NO_ACTION.copy()

        format_check, fail_response, action = self.secretary.check_action(
            resp,
            self.cash,
            self.stock_a_amount,
            self.stock_b_amount,
            stock_a.price,
            stock_b.price,
        )
        retry_count = 0
        while not format_check:
            retry_count += 1
            if retry_count > 3:
                log.logger.warning("Action JSON retry limit exceeded. Agent %s skips action.", self.order)
                return DEFAULT_NO_ACTION.copy()
            resp = self._ask(render_stock_retry_prompt(fail_response))
            if not resp:
                return DEFAULT_NO_ACTION.copy()
            format_check, fail_response, action = self.secretary.check_action(
                resp,
                self.cash,
                self.stock_a_amount,
                self.stock_b_amount,
                stock_a.price,
                stock_b.price,
            )

        log.logger.info("INFO: Agent %s decides action: %s", self.order, action)
        return action

    def loan_repayment(self, date: int, loan_rates: list[float]) -> None:
        if self.quit:
            return

        for loan in self.loans[:]:
            if loan["repayment_date"] == date:
                self.cash -= loan["amount"] * (1 + loan_rates[loan["loan_type"]])
                self.loans.remove(loan)
        if self.cash < 0:
            self.is_bankrupt = True

    def interest_payment(self, loan_rates: list[float]) -> None:
        if self.quit:
            return

        for loan in self.loans:
            self.cash -= loan["amount"] * loan_rates[loan["loan_type"]] / 12
        if self.cash < 0:
            self.is_bankrupt = True

    def bankrupt_process(self, stock_a_price: float, stock_b_price: float) -> bool:
        if self.quit:
            return False

        total_value = self.stock_a_amount * stock_a_price + self.stock_b_amount * stock_b_price + self.cash
        if total_value < 0:
            log.logger.warning("Agent %s bankrupt and leaves market.", self.order)
            return True

        needed_cash = -self.cash
        if needed_cash <= 0:
            self.is_bankrupt = False
            return False

        sell_a = min(self.stock_a_amount, math.ceil(needed_cash / stock_a_price))
        self.stock_a_amount -= sell_a
        self.cash += sell_a * stock_a_price

        if self.cash < 0:
            needed_cash = -self.cash
            sell_b = min(self.stock_b_amount, math.ceil(needed_cash / stock_b_price))
            self.stock_b_amount -= sell_b
            self.cash += sell_b * stock_b_price

        self.is_bankrupt = self.cash < 0
        return self.is_bankrupt

    def post_message(self) -> str:
        if self.quit:
            return ""
        return self._ask(render_post_message_prompt())

    def next_day_estimate(self) -> dict:
        if self.quit:
            return DEFAULT_NO_ESTIMATE.copy()

        resp = self._ask(render_next_day_estimate_prompt())
        if not resp:
            return DEFAULT_NO_ESTIMATE.copy()

        format_check, fail_response, estimate = self.secretary.check_estimate(resp)
        retry_count = 0
        while not format_check:
            retry_count += 1
            if retry_count > 3:
                log.logger.warning("Estimate JSON retry limit exceeded. Agent %s uses no-action estimate.", self.order)
                return DEFAULT_NO_ESTIMATE.copy()
            resp = self._ask(render_next_day_estimate_retry_prompt(fail_response))
            if not resp:
                return DEFAULT_NO_ESTIMATE.copy()
            format_check, fail_response, estimate = self.secretary.check_estimate(resp)
        return estimate

    def _ask(self, prompt: str, temperature: float = 1.0) -> str:
        response = self.llm_client.complete(self.chat_history, prompt, temperature=temperature)
        if response:
            self.chat_history.append({"role": "user", "content": prompt})
            self.chat_history.append({"role": "assistant", "content": response})
        return response
