from __future__ import annotations

from pathlib import Path
from typing import Union
import csv
import json

try:
    import pandas as pd
except ImportError:
    pd = None


class SimulationRecorder:
    trade_columns = [
        "交易日",
        "交易阶段",
        "股票类型",
        "买入交易员",
        "卖出交易员",
        "交易数量",
        "交易价格",
        "成交额",
        "买方手续费",
        "卖方手续费",
        "滑点",
    ]
    stock_columns = ["交易日", "第几个交易阶段", "阶段结束后股票A价格", "阶段结束后股票B价格"]
    agent_day_columns = [
        "交易员",
        "交易日",
        "是否贷款",
        "贷款类型",
        "贷款数量",
        "明日是否贷款",
        "明日是否买入A",
        "明日是否卖出A",
        "明日是否买入B",
        "明日是否卖出B",
    ]
    agent_session_columns = [
        "交易员",
        "交易日",
        "交易阶段",
        "交易前资产总额",
        "交易前持有现金",
        "交易前持有的A股价值",
        "交易前持有的B股价值",
        "挂单类型",
        "挂单股票类别",
        "挂单数量",
        "挂单价格",
    ]

    def __init__(self, output_dir: Union[str, Path] = "res"):
        self.output_dir = Path(output_dir)
        self.trade_rows: list[list] = []
        self.stock_rows: list[list] = []
        self.agent_day_rows: list[list] = []
        self.agent_session_rows: list[list] = []
        self.trace_events: list[dict] = []

    def record_trade(
        self,
        date: int,
        session: int,
        stock: str,
        buyer: int,
        seller: int,
        amount: int,
        price: float,
        gross_value: float = 0.0,
        buyer_fee: float = 0.0,
        seller_fee: float = 0.0,
        slippage: float = 0.0,
    ) -> None:
        self.trade_rows.append([
            date,
            session,
            stock,
            buyer,
            seller,
            amount,
            price,
            gross_value,
            buyer_fee,
            seller_fee,
            slippage,
        ])

    def record_stock(
        self,
        date: int,
        session: int,
        stock_a_price: float,
        stock_b_price: float,
    ) -> None:
        self.stock_rows.append([date, session, stock_a_price, stock_b_price])

    def record_agent_day(
        self,
        *,
        agent: int,
        date: int,
        loan_json: dict,
        estimate_json: dict,
    ) -> None:
        loan_type = 0
        loan_amount = 0
        if loan_json["loan"] == "yes":
            loan_type = loan_json["loan_type"]
            loan_amount = loan_json["amount"]

        self.agent_day_rows.append([
            agent,
            date,
            loan_json["loan"],
            loan_type,
            loan_amount,
            estimate_json["loan"],
            estimate_json["buy_A"],
            estimate_json["sell_A"],
            estimate_json["buy_B"],
            estimate_json["sell_B"],
        ])

    def record_agent_session(
        self,
        *,
        agent: int,
        date: int,
        session: int,
        proper: float,
        cash: float,
        stock_a_value: float,
        stock_b_value: float,
        action_json: dict,
    ) -> None:
        action_stock = "-"
        amount = 0
        price = 0
        action_type = action_json["action_type"]
        if action_type != "no":
            action_stock = action_json["stock"]
            amount = action_json["amount"]
            price = action_json["price"]

        self.agent_session_rows.append([
            agent,
            date,
            session,
            proper,
            cash,
            stock_a_value,
            stock_b_value,
            action_type,
            action_stock,
            amount,
            price,
        ])

    def record_trace(self, event_type: str, payload: dict) -> None:
        event = {
            "sequence": len(self.trace_events) + 1,
            "event_type": event_type,
        }
        event.update(payload)
        self.trace_events.append(event)

    def flush(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_table("trades", self.trade_columns, self.trade_rows)
        self._write_table("stocks", self.stock_columns, self.stock_rows)
        self._write_table("agent_day_record", self.agent_day_columns, self.agent_day_rows)
        self._write_table(
            "agent_session_record",
            self.agent_session_columns,
            self.agent_session_rows,
        )
        self._write_jsonl("trace.jsonl", self.trace_events)

    def _write_table(self, stem: str, columns: list[str], rows: list[list]) -> None:
        if pd is not None:
            dataframe = pd.DataFrame(rows, columns=columns)
            dataframe.to_excel(self.output_dir / f"{stem}.xlsx", index=False)
            return

        with (self.output_dir / f"{stem}.csv").open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(columns)
            writer.writerows(rows)

    def _write_jsonl(self, filename: str, events: list[dict]) -> None:
        with (self.output_dir / filename).open("w", encoding="utf-8") as jsonl_file:
            for event in events:
                jsonl_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
