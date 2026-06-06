from __future__ import annotations

from textwrap import dedent
from typing import Optional


THREE_YEAR_FINANCIAL_REPORT = """
The following lists the financial data for the past three years, covering a total of twelve quarters.

Stock A:
Revenue million: 3696.19, 3578.00, 3595.49, 3215.64, 3973.40, 3810.57, 3840.70, 3433.02, 4344.52, 4095.22, 4114.16, 3717.96
Net profit million: 127.711441, 217.9586418, 360.756337, 358.08228, 650.8868033, 693.3022798, 433.2338757, 517.0593354, 712.7358875, 628.310145, 250.5046675, 325.5147258
Cash flow million: 30.0950631, 135.4141818, 344.3249477, 279.5563512, 564.624197, 642.8122273, 350.3899245, 493.4058465, 650.6526937, 579.0037013, 185.7066407, 273.1287018

Stock B:
Revenue million: 570.00, 774.00, 643.00, 995.00, 684.46, 934.37, 782.08, 1204.05, 788.29, 1100.32, 914.96, 1418.37
Net profit million: 85.9691, 142.086, 87.5419224, 135.7643678, 132.7973368, 169.6505746, 194.9436163, 272.1084953, 225.1707811, 356.7201332
Cash flow million: 68.97, 90.171, 82.1754, 124.773, 75.4954968, 123.5240842, 132.7191287, 153.7571212, 194.9436163, 261.1053212, 216.3871992, 345.6568448
"""

BACKGROUND = """
You are a stock trader, and next you will simulate interactions with other traders in the market.
There are two stocks in the market, A and B. B is a newly listed stock.

Company A has been listed for 10 years and is deeply rooted in the chemical industry. The company's
operations have encountered bottlenecks, with revenue declining over the past three years. Although
Company A's performance has declined over the past five years, the overall trend is stable. With the
recent CEO change and exploration of new business avenues, the future operational outlook is expected
to improve.

Company B is a technology company. It has just been listed for three years and is in a period of
business growth. Last year, its revenue declined due to the overall tech environment, but operations
remain robust. According to the latest corporate news, future revenue growth is expected to return to
over 20%. In the short term, the stock price is expected to continue rising. While Company B's
operations are good, there is a history of concealing critical data before its IPO, casting doubt on
the reliability of its revenue.

The last three years of financial data are listed below:
{three_year_report}
"""


def render_loan_prompt(
    *,
    date: int,
    character: str,
    stock_a_amount: int,
    stock_b_amount: int,
    cash: float,
    loans: list[dict],
    max_loan: float,
    loan_rates: list[float],
    stock_a_price: Optional[float] = None,
    stock_b_price: Optional[float] = None,
    last_day_forum_message: Optional[list[dict]] = None,
) -> str:
    market_context = ""
    if date > 1:
        market_context = f"""
        After the close of trading yesterday, the stock prices of Company A and Company B
        were {stock_a_price} dollars per share and {stock_b_price} dollars per share.
        Posts by other traders on the forum are as follows: {last_day_forum_message}
        """

    return _clean(
        f"""
        ## Background
        You are a stock trader, and next you will simulate interactions with other traders in the market.
        There are two stocks in the market, A and B. B is the newly listed stock.

        {_clean(market_context)}

        ## Loan Types
        0. 22 days, benchmark interest rate {loan_rates[0]}
        1. 44 days, benchmark interest rate {loan_rates[1]}
        2. 66 days, benchmark interest rate {loan_rates[2]}

        ## Instruction
        It is day {date}, and your current character is {character}.
        You hold {stock_a_amount} shares of Company A and {stock_b_amount} shares of Company B.
        You have {cash} dollars in cash. Your current loans are {loans}.
        Decide whether to continue the loan and the amount of the loan.
        The loan amount must not exceed {max_loan}.

        Return exactly one JSON object, for example:
        {{"loan": "yes", "loan_type": 2, "amount": 1000}}

        If no loan is required, return:
        {{"loan": "no"}}
        """
    )


def render_loan_retry_prompt(fail_response: str) -> str:
    return _clean(
        f"""
        The following problem appeared in your previous loan JSON: {fail_response}

        Return exactly one JSON object:
        {{"loan": "yes", "loan_type": 2, "amount": 1000}}

        If no loan is required, return:
        {{"loan": "no"}}
        """
    )


def render_stock_prompt(
    *,
    date: int,
    session: int,
    stock_a_amount: int,
    stock_b_amount: int,
    stock_a_price: float,
    stock_b_price: float,
    stock_a_deals: dict,
    stock_b_deals: dict,
    cash: float,
    stock_a_report: Optional[str] = None,
    stock_b_report: Optional[str] = None,
    include_background: bool = False,
) -> str:
    background = ""
    if include_background:
        background = BACKGROUND.format(three_year_report=_clean(THREE_YEAR_FINANCIAL_REPORT))

    seasonal_report = ""
    if stock_a_report and stock_b_report:
        seasonal_report = f"""
        ## Seasonal Financial Reports
        Stock A: {stock_a_report}
        Stock B: {stock_b_report}
        """

    return _clean(
        f"""
        {_clean(background)}

        {_clean(seasonal_report)}

        ## Market
        It is trading session {session} on day {date}.
        After the previous session, the stock price of Company A is {stock_a_price}
        and the stock price of Company B is {stock_b_price}.
        In the current session, stock A orders are {stock_a_deals}.
        Stock B orders are {stock_b_deals}.

        ## Your Position
        You hold {stock_a_amount} shares of Company A and {stock_b_amount} shares of Company B.
        You have {cash} dollars in cash.

        ## Instruction
        Decide whether to buy or sell shares of Company A or Company B, and how much to buy or sell
        at what limit price. You may reference the current price and current order book. The quantity
        must be a positive integer. You can only answer one JSON action.

        Return exactly one JSON object, for example:
        {{"action_type": "buy", "stock": "A", "amount": 100, "price": 30.1}}
        {{"action_type": "sell", "stock": "B", "amount": 10, "price": 40}}

        If neither buy nor sell, return:
        {{"action_type": "no"}}
        """
    )


def render_stock_retry_prompt(fail_response: str) -> str:
    return _clean(
        f"""
        The following problem appeared in your previous action JSON: {fail_response}

        Return exactly one JSON object, for example:
        {{"action_type": "buy", "stock": "A", "amount": 100, "price": 30.1}}

        If neither buy nor sell, return:
        {{"action_type": "no"}}
        """
    )


def render_post_message_prompt() -> str:
    return _clean(
        """
        The current trading day is over. Briefly post your trading thoughts on the forum.
        What you post will be publicly visible to all traders.
        Return only the forum post content.
        """
    )


def render_next_day_estimate_prompt() -> str:
    return _clean(
        """
        Based on the market information and forum information of the current trading day,
        estimate whether you will buy stock A, sell stock A, buy stock B, sell stock B,
        and whether you will choose a loan tomorrow.
        Mark expected actions as yes and other actions as no.

        Return exactly one JSON object:
        {"buy_A": "yes", "buy_B": "no", "sell_A": "yes", "sell_B": "no", "loan": "yes"}
        """
    )


def render_next_day_estimate_retry_prompt(fail_response: str) -> str:
    return _clean(
        f"""
        The following problem appeared in your previous estimate JSON: {fail_response}

        Return exactly one JSON object:
        {{"buy_A": "yes", "buy_B": "no", "sell_A": "yes", "sell_B": "no", "loan": "yes"}}
        """
    )


def _clean(text: str) -> str:
    return dedent(text).strip()
