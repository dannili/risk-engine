# risk-engine

Async portfolio risk service. Computes historical Value-at-Risk and
backtests for multi-asset portfolios.

## Architecture

Client submits a portfolio and parameters. The API validates, enqueues,
and returns 202 immediately. A Celery worker pulls price history from
Postgres, computes VaR and the backtest, and writes results. The client
polls for status.

## Why async
A VaR run over a 500-day lookback plus a rolling backtest takes seconds
to minutes. That can't live inside an HTTP request...

## Design decisions
- Why the (ticker, date DESC) index
- Why idempotency via input_hash
- What happens when a worker dies mid-task
- Why Postgres and not a time-series store

## Running locally
docker compose up ...

## Deployment
ECS Fargate, RDS, ElastiCache, CloudWatch...

## API
