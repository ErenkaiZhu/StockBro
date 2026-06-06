from __future__ import annotations

import json
from typing import Any, Optional

from log.custom_logger import log


class Secretary:
    def check_loan(self, resp: str, max_loan: float) -> tuple[bool, str, Optional[dict]]:
        parsed_json, fail_response = self._extract_json(resp)
        if parsed_json is None:
            return False, fail_response, None

        loan_value = self._lower_string(parsed_json.get("loan"))
        if loan_value not in {"yes", "no"}:
            return False, "Value of key 'loan' should be yes or no.", None
        parsed_json["loan"] = loan_value

        if loan_value == "no":
            if "loan_type" in parsed_json or "amount" in parsed_json:
                return (
                    False,
                    "Do not include loan_type or amount when value of key 'loan' is no.",
                    None,
                )
            return True, "", parsed_json

        loan_type = parsed_json.get("loan_type")
        amount = parsed_json.get("amount")
        if not self._is_int(loan_type) or loan_type not in {0, 1, 2}:
            return False, "Value of key 'loan_type' should be 0, 1 or 2.", None
        if not self._is_number(amount) or amount <= 0 or amount > max_loan:
            return (
                False,
                f"Value of key 'amount' should be positive and less than {max_loan}.",
                None,
            )
        return True, "", parsed_json

    def check_action(
        self,
        resp: str,
        cash: float,
        stock_a_amount: int,
        stock_b_amount: int,
        stock_a_price: float,
        stock_b_price: float,
    ) -> tuple[bool, str, Optional[dict]]:
        parsed_json, fail_response = self._extract_json(resp)
        if parsed_json is None:
            return False, fail_response, None

        action_type = self._lower_string(parsed_json.get("action_type"))
        if action_type not in {"buy", "sell", "no"}:
            return False, "Value of key 'action_type' should be buy, sell or no.", None
        parsed_json["action_type"] = action_type

        if action_type == "no":
            if {"stock", "amount", "price"} & parsed_json.keys():
                return (
                    False,
                    "Do not include stock, amount or price when action_type is no.",
                    None,
                )
            return True, "", parsed_json

        stock_name = parsed_json.get("stock")
        amount = parsed_json.get("amount")
        price = parsed_json.get("price")
        if stock_name not in {"A", "B"}:
            return False, "Value of key 'stock' should be A or B.", None
        if not self._is_int(amount) or amount <= 0:
            return False, "Value of key 'amount' should be a positive integer.", None
        if not self._is_number(price) or price <= 0:
            return False, "Value of key 'price' should be a positive number.", None

        if action_type == "buy" and amount * price > cash:
            return (
                False,
                f"The cash you have now is {cash}; amount * price should not exceed cash.",
                None,
            )

        holds = {"A": stock_a_amount, "B": stock_b_amount}
        if action_type == "sell" and amount > holds[stock_name]:
            return (
                False,
                f"The amount of stock {stock_name} you hold is {holds[stock_name]}; "
                "amount should not exceed holdings.",
                None,
            )

        parsed_json["price"] = float(price)
        return True, "", parsed_json

    def check_estimate(self, resp: str) -> tuple[bool, str, Optional[dict]]:
        parsed_json, fail_response = self._extract_json(resp)
        if parsed_json is None:
            return False, fail_response, None

        required_keys = {"buy_A", "buy_B", "sell_A", "sell_B", "loan"}
        if required_keys - parsed_json.keys():
            return (
                False,
                "Keys 'buy_A', 'buy_B', 'sell_A', 'sell_B' and 'loan' should be in response.",
                None,
            )

        for key in required_keys:
            value = self._lower_string(parsed_json.get(key))
            if value not in {"yes", "no"}:
                return False, "Value of all estimate keys should be yes or no.", None
            parsed_json[key] = value
        return True, "", parsed_json

    def check_message(self, resp: str) -> tuple[bool, str, Optional[dict]]:
        parsed_json, fail_response = self._extract_json(resp)
        if parsed_json is None:
            return False, fail_response, None

        message = parsed_json.get("message")
        if not isinstance(message, str) or not message.strip():
            return False, "Key 'message' should be a non-empty string.", None
        parsed_json["message"] = message.strip()
        return True, "", parsed_json

    @staticmethod
    def _extract_json(resp: str) -> tuple[Optional[dict[str, Any]], str]:
        if not isinstance(resp, str):
            return None, "Response should be a string containing one JSON object."
        start_idx = resp.find("{")
        if start_idx < 0:
            log.logger.debug("Wrong json content in response: %s", resp)
            return None, "Wrong JSON format: no object was found in response."

        decoder = json.JSONDecoder()
        try:
            parsed_json, _ = decoder.raw_decode(resp[start_idx:])
        except json.JSONDecodeError:
            log.logger.debug("Illegal json content in response: %s", resp)
            return None, "Illegal JSON format."

        if not isinstance(parsed_json, dict):
            return None, "Response JSON should be an object."
        return parsed_json, ""

    @staticmethod
    def _lower_string(value: object) -> str:
        return value.lower() if isinstance(value, str) else ""

    @staticmethod
    def _is_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @staticmethod
    def _is_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
