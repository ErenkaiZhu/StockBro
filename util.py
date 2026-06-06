from __future__ import annotations

from config import DEFAULT_CONFIG


# Backwards-compatible constants for older notebooks/scripts that imported util.py.
# New simulation code should use config.SimulationConfig instead.
AGENTS_NUM = DEFAULT_CONFIG.agents_num
TOTAL_DATE = DEFAULT_CONFIG.total_days
TOTAL_SESSION = DEFAULT_CONFIG.sessions_per_day

STOCK_A_INITIAL_PRICE = DEFAULT_CONFIG.stock_a_initial_price
STOCK_B_INITIAL_PRICE = DEFAULT_CONFIG.stock_b_initial_price

TRANSACTION_FEE_RATE = DEFAULT_CONFIG.market.transaction_fee_rate
SLIPPAGE_RATE = DEFAULT_CONFIG.market.slippage_rate
DAILY_PRICE_LIMIT_PCT = DEFAULT_CONFIG.market.daily_price_limit_pct
MAX_FILL_PER_PRICE_LEVEL = DEFAULT_CONFIG.market.max_fill_per_price_level
ORDER_TTL_SESSIONS = DEFAULT_CONFIG.market.order_ttl_sessions

MAX_INITIAL_PROPERTY = DEFAULT_CONFIG.max_initial_property
MIN_INITIAL_PROPERTY = DEFAULT_CONFIG.min_initial_property

LOAN_TYPE = list(DEFAULT_CONFIG.loan_types)
LOAN_TYPE_DATE = list(DEFAULT_CONFIG.loan_type_days)
LOAN_RATE = list(DEFAULT_CONFIG.initial_loan_rates)
REPAYMENT_DAYS = list(DEFAULT_CONFIG.repayment_days)

SEASONAL_DAYS = DEFAULT_CONFIG.seasonal_days
SEASON_REPORT_DAYS = list(DEFAULT_CONFIG.season_report_days)
FINANCIAL_REPORT_A = list(DEFAULT_CONFIG.financial_reports_a)
FINANCIAL_REPORT_B = list(DEFAULT_CONFIG.financial_reports_b)

EVENT_1_DAY = DEFAULT_CONFIG.special_events[0].day
EVENT_1_MESSAGE = DEFAULT_CONFIG.special_events[0].message
EVENT_1_LOAN_RATE = list(DEFAULT_CONFIG.special_events[0].loan_rates)

EVENT_2_DAY = DEFAULT_CONFIG.special_events[1].day
EVENT_2_MESSAGE = DEFAULT_CONFIG.special_events[1].message
EVENT_2_LOAN_RATE = list(DEFAULT_CONFIG.special_events[1].loan_rates)
