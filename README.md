# StockBro

StockBro is an LLM-powered trading simulation lab. It models a small market where autonomous
trader agents borrow cash, place limit orders, react to company reports and policy events, and
leave public forum messages that influence the next trading day.

The project is designed for experiments, not live trading. It gives you a controllable sandbox for
studying how different model choices, prompts, market rules, and external events change simulated
investor behavior.

## Features

- Multi-agent trader simulation with configurable agent count, trading days, and sessions per day.
- OpenAI, Gemini, and deterministic `mock` model adapters.
- Limit-order books for two simulated stocks, including best bid/ask, spread, and depth snapshots.
- Matching engine with partial fills, crossed-limit execution, slippage, fees, daily price limits,
  market-depth caps, and order expiration.
- Loan decisions, interest payments, repayment dates, and bankruptcy handling.
- Synthetic financial reports and policy-rate events.
- Forum-style daily messages that become next-day context.
- Structured LLM responses for loan, trading, estimate, and forum-message decisions.
- Spreadsheet/CSV records plus JSONL traces for replaying prompts, responses, orders, and trades.
- Core tests for JSON validation, market matching, order expiration, fees, and accounting invariants.

## Project Layout

```text
main.py                 # simulation entrypoint and day/session loop
web_app.py              # local web console backend
frontend/               # browser UI for running and inspecting simulations
agent.py                # trader state and LLM decision methods
config.py               # simulation parameters, reports, special events
llm_client.py           # OpenAI/Gemini/mock model adapter
market.py               # order book and matching engine
accounting.py           # trade-level accounting invariants
schemas.py              # structured-output schemas for LLM decisions
secretary.py            # JSON extraction and validation
stock.py                # stock state and price updates
record.py               # in-memory records flushed to files
prompt/agent_prompt.py  # prompt rendering functions
log/custom_logger.py    # console + file logger
tests/test_core.py      # core unit tests
```

## Setup

```bash
conda create --name stockbro python=3.9
conda activate stockbro
pip install -r requirements.txt
```

For OpenAI models:

```bash
export OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

For Gemini models:

```bash
export GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
```

## Quick Start

Open the local console:

```bash
python3 web_app.py
```

Then visit:

```text
http://127.0.0.1:8765
```

Run a no-cost smoke test with the deterministic mock model:

```bash
python3 main.py --model mock --agents 2 --days 1 --sessions 1 --output-dir res_mock
```

Run a small real-model simulation:

```bash
python3 main.py --model gpt-4o-mini --agents 5 --days 3 --sessions 2 --output-dir res
```

Run with Gemini:

```bash
python3 main.py --model gemini-pro --agents 5 --days 3 --sessions 2 --output-dir res
```

## Runtime Options

```bash
python3 main.py \
  --model mock \
  --agents 10 \
  --days 5 \
  --sessions 2 \
  --seed 42 \
  --output-dir res \
  --log-level INFO \
  --fee-rate 0.001 \
  --slippage-rate 0.0005 \
  --daily-limit-pct 0.10 \
  --max-fill-per-level 10000 \
  --order-ttl-sessions 3
```

Common flags:

- `--model`: `mock`, an OpenAI model name, or a Gemini model name.
- `--agents`: number of trader agents.
- `--days`: number of simulated trading days.
- `--sessions`: number of trading sessions per day.
- `--seed`: random seed for reproducible initialization and trading order.
- `--output-dir`: directory for generated records.
- `--log-level`: `DEBUG`, `INFO`, `WARNING`, or `ERROR`.
- `--fee-rate`: transaction fee charged to each non-admin side of a trade.
- `--slippage-rate`: price movement applied when aggressive orders consume liquidity.
- `--daily-limit-pct`: daily up/down price limit from the day's opening reference price.
- `--max-fill-per-level`: maximum shares filled from one price level per match.
- `--order-ttl-sessions`: number of sessions before unfilled orders expire.

## Outputs

When `pandas` and `openpyxl` are installed, StockBro writes Excel files:

- `trades.xlsx`
- `stocks.xlsx`
- `agent_day_record.xlsx`
- `agent_session_record.xlsx`
- `trace.jsonl`

If the spreadsheet dependencies are missing, StockBro falls back to CSV files with the same stems.
`trace.jsonl` is always written as newline-delimited JSON and contains replayable events such as:

- LLM prompts and responses;
- order additions, rejections, and expirations;
- executed trades with fees and slippage;
- day-start reference prices.

The web console writes browser-launched runs under `web_runs/`, which is ignored by git.

## How The Simulation Works

1. StockBro initializes two stocks and a configurable population of trader agents.
2. Each day starts with loan repayments, interest payments, bankruptcy checks, and policy events.
3. Each agent decides whether to borrow money.
4. During every trading session, expired orders are removed and agents submit one buy, sell, or
   no-op order.
5. The matching engine executes compatible limit orders using price limits, depth caps, slippage,
   and transaction fees.
6. Trade-level accounting invariants verify cash, fees, and holdings after every execution.
7. Stock prices move to the latest traded price.
8. Agents estimate tomorrow's likely actions and post structured forum messages for the next day.
9. Spreadsheet/CSV records and JSONL traces are flushed to the output directory at the end of the run.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
python3 -m py_compile \
  main.py agent.py accounting.py config.py llm_client.py market.py schemas.py \
  secretary.py stock.py record.py util.py prompt/agent_prompt.py \
  log/custom_logger.py tests/test_core.py
```

Use `mock` mode when changing core mechanics. It avoids API cost and makes fast regression checks
possible before running expensive model experiments.

## Configuration

Most experiment parameters live in `config.py`, including:

- initial stock prices;
- agent count and simulation length defaults;
- market fees, slippage, price limits, depth caps, and order TTL;
- loan durations, rates, and repayment days;
- financial reports;
- special policy events.

CLI arguments override the common runtime settings without editing source code.

## Roadmap

- Add a real experiment runner that can sweep models, prompts, seeds, and market settings.
- Add market metrics such as volume, volatility, spreads, and agent-level returns.
- Split prompt variants into named experiment profiles.
- Add a trace viewer for debugging individual agent decisions.
