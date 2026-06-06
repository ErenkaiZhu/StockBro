# StockAgent

Refactored implementation of the StockAgent trading simulation from:

> When AI Meets Finance (StockAgent): Large Language Model-based Stock Trading in Simulated Real-world Environments

Paper: https://arxiv.org/pdf/2407.18957

![workflow](fig/workflow.png)
![schematic](fig/schematic.png)

## What It Simulates

StockAgent is a multi-agent market simulator. Each agent is an LLM-powered trader that can:

- decide whether to borrow money;
- submit one buy, sell, or no-op order per trading session;
- read current order books, prices, financial reports, policy events, and forum messages;
- post a short forum message after the trading day;
- estimate tomorrow's likely actions.

The market is intentionally simplified: two stocks, limit orders, a small matching engine, synthetic financial reports,
interest-rate events, repayment days, bankruptcy handling, and Excel output records.

## Project Layout

```text
main.py                 # simulation entrypoint and day/session loop
agent.py                # trader state and LLM decision methods
config.py               # simulation parameters, reports, special events
llm_client.py           # OpenAI/Gemini/mock model adapter
market.py               # order book and matching engine
secretary.py            # JSON extraction and validation
stock.py                # stock state and price updates
record.py               # in-memory records flushed to xlsx
prompt/agent_prompt.py  # plain prompt rendering functions
log/custom_logger.py    # colored console + file logger
```

## Setup

```bash
conda create --name stockagent python=3.9
conda activate stockagent
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

## Run

Small no-cost smoke run with a deterministic mock model:

```bash
python3 main.py --model mock --agents 2 --days 1 --sessions 1 --output-dir res_mock
```

Real LLM simulation:

```bash
python3 main.py --model gemini-pro
python3 main.py --model gpt-4o-mini
```

Useful runtime flags:

```bash
python3 main.py \
  --model mock \
  --agents 10 \
  --days 5 \
  --sessions 2 \
  --seed 42 \
  --output-dir res
```

Outputs are written to:

- `trades.xlsx`
- `stocks.xlsx`
- `agent_day_record.xlsx`
- `agent_session_record.xlsx`

## Citation

```bibtex
@article{zhang2024ai,
  title={When AI Meets Finance (StockAgent): Large Language Model-based Stock Trading in Simulated Real-world Environments},
  author={Zhang, Chong and Liu, Xinyi and Jin, Mingyu and Zhang, Zhongmou and Li, Lingyao and Wang, Zhengting and Hua, Wenyue and Shu, Dong and Zhu, Suiyuan and Jin, Xiaobo and others},
  journal={arXiv preprint arXiv:2407.18957},
  year={2024}
}
```
