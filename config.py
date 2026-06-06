from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SpecialEvent:
    day: int
    message: str
    loan_rates: tuple[float, float, float]


@dataclass(frozen=True)
class MarketConfig:
    transaction_fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    daily_price_limit_pct: float = 0.10
    max_fill_per_price_level: int = 10_000
    order_ttl_sessions: int = 3
    order_book_depth_levels: int = 5


@dataclass(frozen=True)
class SimulationConfig:
    model_name: str = "gemini-pro"
    agents_num: int = 50
    total_days: int = 264
    sessions_per_day: int = 3
    output_dir: Path = Path("res")
    seed: Optional[int] = None

    stock_a_initial_price: float = 30.0
    stock_b_initial_price: float = 40.0
    market: MarketConfig = field(default_factory=MarketConfig)

    max_initial_property: float = 5_000_000.0
    min_initial_property: float = 100_000.0

    loan_types: tuple[str, str, str] = ("one-month", "two-month", "three-month")
    loan_type_days: tuple[int, int, int] = (22, 44, 66)
    initial_loan_rates: tuple[float, float, float] = (0.027, 0.03, 0.033)
    repayment_days: tuple[int, ...] = (
        22, 44, 66, 88, 110, 132, 154, 176, 198, 220, 242, 264
    )

    seasonal_days: int = 66
    season_report_days: tuple[int, int, int, int] = (12, 78, 144, 210)

    financial_reports_a: tuple[str, ...] = field(default_factory=lambda: (
        "Last quarter's financial report of Company A. Revenue growth rate (YoY): 9.49%, "
        "Revenue million: 4483.99, Gross margin: 41.05%, Income Tax as a percentage of Revenue: "
        "11.31%, Selling Expense Rate:6.83%, Management Expense Rate: 3.83%, Net profit million: "
        "856.6705, Depreciation and Amortization: 0.91%, Capital Expenditures: 2.30%, "
        "Changes in working capital: 0.82%, Cash Flow(million): 756.7537",
        "Last quarter's financial report of Company A. Revenue growth rate (YoY): 7.38%, "
        "Revenue million: 4417.79, Gross margin: 35.68%, Income Tax as a percentage of Revenue: "
        "11.75%, Selling Expense Rate:8.13%, Management Expense Rate: 4.62%, Net profit million: "
        "493.9451, Depreciation and Amortization: 1.34%, Capital Expenditures: 2.68%, "
        "Changes in working capital: 0.86%, Cash Flow(million): 396.5329",
        "Last quarter's financial report of Company A. Revenue growth rate (YoY): 8.70%, "
        "Revenue million: 4041.30, Gross margin: 37.45%, Income Tax as a percentage of Revenue: "
        "9.34%, Selling Expense Rate:6.79%, Management Expense Rate: 3.41%, Net profit million: "
        "724.3648, Depreciation and Amortization: 1.27%, Capital Expenditures: 2.44%, "
        "Changes in working capital: 0.94%, Cash Flow(million): 639.5329",
        "Last quarter's financial report of Company A. Revenue growth rate (YoY): 7.75%, "
        "Revenue million: 5024.04, Gross margin: 42.47%, Income Tax as a percentage of Revenue: "
        "10.67%, Selling Expense Rate:6.56%, Management Expense Rate: 4.72%, Net profit million: "
        "1031.214, Depreciation and Amortization: 1.08%, Capital Expenditures: 2.71%, "
        "Changes in working capital: 0.08%, Cash Flow(million): 945.5034",
    ))
    financial_reports_b: tuple[str, ...] = field(default_factory=lambda: (
        "Last quarter's financial report of Company B. Revenue growth rate (YoY): 19.96%, "
        "Revenue million: 1319.94, Gross margin: 31.21%, Income Tax as a percentage of Revenue: "
        "0.70%, Selling Expense Rate:4.69%, Management Expense Rate: 8.78%, Net profit million: "
        "224.9179, Depreciation and Amortization: 1.13%, Capital Expenditures: 1.77%, "
        "Changes in working capital: 0.59%, Cash Flow(million): 208.7266",
        "Last quarter's financial report of Company B. Revenue growth rate (YoY): 19.86%, "
        "Revenue million: 1096.70, Gross margin: 31.26%, Income Tax as a percentage of Revenue: "
        "0.71%, Selling Expense Rate:3.62%, Management Expense Rate: 9.90%, Net profit million: "
        "186.7678, Depreciation and Amortization: 0.67%, Capital Expenditures: 1.44%, "
        "Changes in working capital: -0.31%, Cash Flow(million): 181.6862",
        "Last quarter's financial report of Company B. Revenue growth rate (YoY): 18.21%, "
        "Revenue million: 1676.70, Gross margin: 31.58%, Income Tax as a percentage of Revenue: "
        "0.92%, Selling Expense Rate:3.78%, Management Expense Rate: 10.27%, Net profit million: "
        "278.3327, Depreciation and Amortization: 0.77%, Capital Expenditures: 1.56%, "
        "Changes in working capital: -0.06%, Cash Flow(million): 266.1486",
        "Last quarter's financial report of Company B. Revenue growth rate (YoY): 15.98%, "
        "Revenue million: 1075.13, Gross margin: 32.41%, Income Tax as a percentage of Revenue: "
        "1.08%, Selling Expense Rate:3.79%, Management Expense Rate: 10.70%, Net profit million: "
        "181.1602, Depreciation and Amortization: 1.09%, Capital Expenditures: 2.28%, "
        "Changes in working capital: 0.67%, Cash Flow(million): 161.1985",
    ))
    special_events: tuple[SpecialEvent, ...] = field(default_factory=lambda: (
        SpecialEvent(
            day=78,
            message=(
                "The government has announced a reduction in the reserve requirement ratio. "
                "The lending interest rates have been lowered."
            ),
            loan_rates=(0.024, 0.027, 0.030),
        ),
        SpecialEvent(
            day=144,
            message="The government has announced an increase in interest rates.",
            loan_rates=(0.0255, 0.0285, 0.0315),
        ),
    ))

    def with_runtime_overrides(
        self,
        *,
        model_name: str,
        agents_num: int,
        total_days: int,
        sessions_per_day: int,
        output_dir: Path,
        seed: Optional[int],
    ) -> "SimulationConfig":
        return replace(
            self,
            model_name=model_name,
            agents_num=agents_num,
            total_days=total_days,
            sessions_per_day=sessions_per_day,
            output_dir=output_dir,
            seed=seed,
        )


DEFAULT_CONFIG = SimulationConfig()
