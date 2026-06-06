from __future__ import annotations


LOAN_DECISION_SCHEMA = {
    "name": "loan_decision",
    "schema": {
        "type": "object",
        "properties": {
            "loan": {"type": "string", "enum": ["yes", "no"]},
            "loan_type": {"type": "integer", "enum": [0, 1, 2]},
            "amount": {"type": "number", "exclusiveMinimum": 0},
        },
        "required": ["loan"],
        "additionalProperties": False,
    },
}

STOCK_ACTION_SCHEMA = {
    "name": "stock_action",
    "schema": {
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "enum": ["buy", "sell", "no"]},
            "stock": {"type": "string", "enum": ["A", "B"]},
            "amount": {"type": "integer", "minimum": 1},
            "price": {"type": "number", "exclusiveMinimum": 0},
        },
        "required": ["action_type"],
        "additionalProperties": False,
    },
}

NEXT_DAY_ESTIMATE_SCHEMA = {
    "name": "next_day_estimate",
    "schema": {
        "type": "object",
        "properties": {
            "buy_A": {"type": "string", "enum": ["yes", "no"]},
            "buy_B": {"type": "string", "enum": ["yes", "no"]},
            "sell_A": {"type": "string", "enum": ["yes", "no"]},
            "sell_B": {"type": "string", "enum": ["yes", "no"]},
            "loan": {"type": "string", "enum": ["yes", "no"]},
        },
        "required": ["buy_A", "buy_B", "sell_A", "sell_B", "loan"],
        "additionalProperties": False,
    },
}

FORUM_MESSAGE_SCHEMA = {
    "name": "forum_message",
    "schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "minLength": 1},
        },
        "required": ["message"],
        "additionalProperties": False,
    },
}
