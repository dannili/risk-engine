# risk-engine

Async portfolio risk service. Computes historical Value-at-Risk and
backtests for multi-asset portfolios.

## Stack (do not add to this)
- Django + Django REST Framework
- PostgreSQL
- Celery + Redis (broker)
- Docker / Docker Compose (local), ECS Fargate (deploy)
- Public daily price data via Stooq or yfinance

## Explicit non-goals
- No frontend. DRF browsable API only.
- No MongoDB or second datastore.
- No ORM-bypassing raw SQL unless there's a measured reason.
- No Kubernetes.

## Why async
A VaR run over a multi-asset portfolio with a 500+ day lookback plus a
rolling backtest takes seconds to minutes. It cannot run inside an HTTP
request. The API accepts the job, returns 202 with a run ID, and the
client polls. This is the core design constraint.

## Schema
portfolios(id, name, base_currency, created_at)
positions(id, portfolio_id FK, ticker, quantity) UNIQUE(portfolio_id, ticker)
price_history(id, ticker, date, close) UNIQUE(ticker, date), INDEX(ticker, date DESC)
var_runs(id, portfolio_id FK, method, confidence, lookback_days, as_of_date,
         input_hash, status, created_at, completed_at) UNIQUE(input_hash)
var_results(id, var_run_id FK, var_value, expected_shortfall,
            breach_count, kupiec_pvalue, computed_at)

status enum: pending | running | complete | failed

## API
GET  /api/portfolios/
POST /api/portfolios/
POST /api/portfolios/{id}/positions/
POST /api/portfolios/{id}/var-runs/   202 -> {run_id, status}
                                      200 -> cached run (idempotent hit)
GET  /api/var-runs/{run_id}/
GET  /api/portfolios/{id}/var-runs/

## Idempotency
input_hash = hash(portfolio_id, method, confidence, lookback_days, as_of_date).
Same inputs must not recompute. Return the existing run with 200.

## Worker task
Load lookback window from price_history -> daily returns -> position-weighted
portfolio returns -> historical VaR at confidence -> expected shortfall ->
breach count over the following window -> Kupiec test p-value.
Write var_results, set var_runs.status.

Task must be idempotent. Retry with exponential backoff. On terminal failure,
set status=failed and persist the error. Never fail silently.

## Conventions
- Structured JSON logging (goes to CloudWatch in deploy).
- Migrations checked in.
- Tests for the VaR math and the idempotency path at minimum.

## Working agreement
Build in stages. Do not scaffold the whole system in one pass.
Explain non-obvious choices (index design, retry policy, task boundaries)
in comments or commit messages so they can be defended later.