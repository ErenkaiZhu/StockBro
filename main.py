from __future__ import annotations

import argparse
import random
from dataclasses import replace
from pathlib import Path

from agent import Agent
from config import DEFAULT_CONFIG, SimulationConfig
from llm_client import LLMClient
from log.custom_logger import log
from market import MatchingEngine, OrderBook
from record import SimulationRecorder
from secretary import Secretary
from stock import Stock


def simulation(config: SimulationConfig) -> None:
    if config.seed is not None:
        random.seed(config.seed)

    llm_client = LLMClient(config.model_name)
    llm_client.ensure_ready()

    secretary = Secretary()
    recorder = SimulationRecorder(config.output_dir)
    matching_engine = MatchingEngine(
        recorder.record_trade,
        market_config=config.market,
        trace_recorder=recorder.record_trace,
        sessions_per_day=config.sessions_per_day,
    )

    stock_a = Stock("A", config.stock_a_initial_price)
    stock_b = Stock("B", config.stock_b_initial_price)
    stock_books = {
        "A": OrderBook(),
        "B": OrderBook(),
    }
    stocks = {
        "A": stock_a,
        "B": stock_b,
    }

    agents = [
        Agent(
            order=i,
            stock_a_price=stock_a.price,
            stock_b_price=stock_b.price,
            secretary=secretary,
            llm_client=llm_client,
            config=config,
            trace_recorder=recorder.record_trace,
        )
        for i in range(config.agents_num)
    ]

    current_loan_rates = list(config.initial_loan_rates)
    events_by_day = {event.day: event for event in config.special_events}
    last_day_forum_message: list[dict] = []

    log.logger.debug("--------Simulation Start!--------")
    try:
        for date in range(1, config.total_days + 1):
            log.logger.debug("--------DAY %s---------", date)
            stock_a.start_day()
            stock_b.start_day()
            recorder.record_trace(
                "day_started",
                {
                    "date": date,
                    "stock_a_open": stock_a.price,
                    "stock_b_open": stock_b.price,
                },
            )

            for agent in agents[:]:
                agent.reset_daily_chat()
                agent.loan_repayment(date, current_loan_rates)

            if date in config.repayment_days:
                for agent in agents[:]:
                    agent.interest_payment(current_loan_rates)

            agents = _handle_bankrupt_agents(agents, stock_a.price, stock_b.price)

            if date in events_by_day:
                event = events_by_day[date]
                current_loan_rates = list(event.loan_rates)
                last_day_forum_message.append({"name": -1, "message": event.message})

            daily_loans: dict[int, dict] = {}
            for agent in agents:
                daily_loans[agent.order] = agent.plan_loan(
                    date,
                    stock_a.price,
                    stock_b.price,
                    last_day_forum_message,
                    current_loan_rates,
                )

            for session in range(1, config.sessions_per_day + 1):
                log.logger.debug("SESSION %s", session)
                for stock_name, order_book in stock_books.items():
                    matching_engine.expire_orders(order_book, date=date, session=session, stock_name=stock_name)

                session_agents = agents[:]
                random.shuffle(session_agents)

                for agent in session_agents:
                    action = agent.plan_stock(
                        date,
                        session,
                        stock_a,
                        stock_b,
                        stock_books["A"].snapshot(config.market.order_book_depth_levels),
                        stock_books["B"].snapshot(config.market.order_book_depth_levels),
                    )
                    proper, cash, value_a, value_b = agent.position_values(stock_a.price, stock_b.price)
                    recorder.record_agent_session(
                        agent=agent.order,
                        date=date,
                        session=session,
                        proper=proper,
                        cash=cash,
                        stock_a_value=value_a,
                        stock_b_value=value_b,
                        action_json=action,
                    )

                    if action["action_type"] == "no":
                        continue

                    submitted_action = action.copy()
                    submitted_action["agent"] = agent.order
                    submitted_action["date"] = date
                    stock_name = submitted_action["stock"]
                    agents_by_id = {current_agent.order: current_agent for current_agent in agents}
                    matching_engine.submit(
                        submitted_action,
                        stock_books[stock_name],
                        agents_by_id,
                        stocks[stock_name],
                        date=date,
                        session=session,
                    )

                stock_a.update_price(date)
                stock_b.update_price(date)
                recorder.record_stock(date, session, stock_a.price, stock_b.price)

            for agent in agents:
                estimation = agent.next_day_estimate()
                log.logger.info("Agent %s tomorrow estimation: %s", agent.order, estimation)
                recorder.record_agent_day(
                    agent=agent.order,
                    date=date,
                    loan_json=daily_loans.get(agent.order, {"loan": "no"}),
                    estimate_json=estimation,
                )

            last_day_forum_message = _collect_forum_messages(agents)
    finally:
        recorder.flush()
        log.logger.debug("--------Simulation finished!--------")


def _handle_bankrupt_agents(
    agents: list[Agent],
    stock_a_price: float,
    stock_b_price: float,
) -> list[Agent]:
    active_agents = []
    for agent in agents:
        if agent.is_bankrupt and agent.bankrupt_process(stock_a_price, stock_b_price):
            agent.quit = True
            continue
        active_agents.append(agent)
    return active_agents


def _collect_forum_messages(agents: list[Agent]) -> list[dict]:
    forum_messages = []
    log.logger.debug("Display forum messages...")
    for agent in agents:
        message = agent.post_message()
        log.logger.info("Agent %s says: %s", agent.order, message)
        forum_messages.append({"name": agent.order, "message": message})
    return forum_messages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default=DEFAULT_CONFIG.model_name, help="LLM model name")
    parser.add_argument("--agents", type=int, default=DEFAULT_CONFIG.agents_num, help="number of agents")
    parser.add_argument("--days", type=int, default=DEFAULT_CONFIG.total_days, help="simulation days")
    parser.add_argument(
        "--sessions",
        type=int,
        default=DEFAULT_CONFIG.sessions_per_day,
        help="trading sessions per day",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_CONFIG.output_dir,
        help="directory for xlsx outputs",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_CONFIG.seed, help="random seed")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="console and file log level",
    )
    parser.add_argument("--fee-rate", type=float, default=DEFAULT_CONFIG.market.transaction_fee_rate)
    parser.add_argument("--slippage-rate", type=float, default=DEFAULT_CONFIG.market.slippage_rate)
    parser.add_argument("--daily-limit-pct", type=float, default=DEFAULT_CONFIG.market.daily_price_limit_pct)
    parser.add_argument("--max-fill-per-level", type=int, default=DEFAULT_CONFIG.market.max_fill_per_price_level)
    parser.add_argument("--order-ttl-sessions", type=int, default=DEFAULT_CONFIG.market.order_ttl_sessions)
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> SimulationConfig:
    config = DEFAULT_CONFIG.with_runtime_overrides(
        model_name=args.model,
        agents_num=args.agents,
        total_days=args.days,
        sessions_per_day=args.sessions,
        output_dir=args.output_dir,
        seed=args.seed,
    )
    return replace(
        config,
        market=replace(
            config.market,
            transaction_fee_rate=args.fee_rate,
            slippage_rate=args.slippage_rate,
            daily_price_limit_pct=args.daily_limit_pct,
            max_fill_per_price_level=args.max_fill_per_level,
            order_ttl_sessions=args.order_ttl_sessions,
        ),
    )


if __name__ == "__main__":
    parsed_args = parse_args()
    log.set_level(parsed_args.log_level)
    simulation(config_from_args(parsed_args))
