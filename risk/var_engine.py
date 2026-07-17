import math

from risk.models import PriceHistory


def _load_price_window(ticker, as_of_date, lookback_days):
    """`lookback_days + 1` closes for `ticker` ending at as_of_date, oldest
    first (need one extra close to produce lookback_days returns)."""
    required = lookback_days + 1
    prices = list(
        PriceHistory.objects.filter(ticker=ticker, date__lte=as_of_date)
        .order_by("-date")[:required]
        .values_list("close", flat=True)
    )
    prices.reverse()

    if len(prices) < required:
        raise ValueError(
            f"Insufficient price history for {ticker}: need {required} "
            f"closes ending {as_of_date}, found {len(prices)}"
        )
    return [float(p) for p in prices]


def load_returns(ticker, as_of_date, lookback_days):
    """Daily returns for `ticker` over the lookback window, oldest first."""
    closes = _load_price_window(ticker, as_of_date, lookback_days)
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]


def compute_portfolio_returns(portfolio, as_of_date, lookback_days):
    """Value-weighted daily portfolio returns over the lookback window.

    Weights are fixed at each position's as_of_date market value (today's
    holdings applied across the historical window) -- the standard
    historical-simulation assumption that portfolio composition was held
    constant throughout the lookback period. Also assumes every position's
    ticker shares the same trading calendar (true for US equities); a
    ticker with a gap the others don't have would misalign the series.
    """
    positions = list(portfolio.positions.all())
    if not positions:
        raise ValueError(f"Portfolio {portfolio.id} has no positions")

    ticker_returns = {}
    ticker_value = {}
    for position in positions:
        closes = _load_price_window(position.ticker, as_of_date, lookback_days)
        ticker_returns[position.ticker] = [
            closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
        ]
        ticker_value[position.ticker] = float(position.quantity) * closes[-1]

    total_value = sum(ticker_value.values())
    if total_value == 0:
        raise ValueError(f"Portfolio {portfolio.id} has zero total value")

    weights = {ticker: value / total_value for ticker, value in ticker_value.items()}

    return [
        sum(weights[ticker] * ticker_returns[ticker][day] for ticker in weights)
        for day in range(lookback_days)
    ]


def _tail_index(n, confidence):
    """Index of the VaR-defining observation in a returns list sorted
    ascending. Rounded before truncating: confidence values like 0.95 don't
    have an exact float representation, so (1 - confidence) * n can land a
    hair below an integer (e.g. 0.9999999999999998 instead of 1.0) and
    truncate one short without the rounding step."""
    index = round((1 - confidence) * n, 8)
    return min(int(index), n - 1)


def historical_var(returns, confidence):
    """Historical-simulation VaR: the (1 - confidence) percentile of the
    return distribution, expressed as a positive loss magnitude."""
    if not returns:
        raise ValueError("Cannot compute VaR on an empty return series")
    sorted_returns = sorted(returns)
    index = _tail_index(len(sorted_returns), confidence)
    return -sorted_returns[index]


def expected_shortfall(returns, confidence):
    """Mean loss in the tail at/beyond the VaR threshold."""
    if not returns:
        raise ValueError("Cannot compute expected shortfall on an empty return series")
    sorted_returns = sorted(returns)
    index = _tail_index(len(sorted_returns), confidence)
    tail = sorted_returns[: index + 1]
    return -(sum(tail) / len(tail))


def count_breaches(returns, var_value):
    """Days where the realized loss strictly exceeded the VaR threshold."""
    return sum(1 for r in returns if -r > var_value)


def _chi2_sf_1df(x):
    """Survival function of a chi-squared distribution with 1 degree of
    freedom, via erfc (chi2_1 is the square of a standard normal, so
    P(X > x) = P(|Z| > sqrt(x)) = erfc(sqrt(x/2))). Avoids a scipy
    dependency for this one closed-form case."""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x) / math.sqrt(2))


def kupiec_pof_pvalue(breaches, n, confidence):
    """Kupiec proportion-of-failures likelihood-ratio test. p-value for
    H0: the observed breach rate equals the expected (1 - confidence).

    In-sample test: breaches are counted within the same lookback window
    used to estimate VaR, not a held-out forward window -- at run time
    (as_of_date is typically "now") there is no future price data yet to
    backtest against. A true out-of-sample backtest needs a separate job
    once time has passed.
    """
    if n <= 0:
        raise ValueError("n must be > 0")

    p = 1 - confidence
    x = breaches
    pi_hat = x / n

    def term(count, prob):
        # limit count * ln(prob) -> 0 as count -> 0, even when prob == 0
        return count * math.log(prob) if count > 0 else 0.0

    log_l_null = term(n - x, 1 - p) + term(x, p)
    log_l_alt = term(n - x, 1 - pi_hat) + term(x, pi_hat)
    lr_stat = -2 * (log_l_null - log_l_alt)
    return _chi2_sf_1df(lr_stat)


def compute_var_run(var_run):
    """Run the full historical VaR + Kupiec backtest for a VarRun. Read-only
    against the DB; the caller persists the result and the run's status."""
    returns = compute_portfolio_returns(
        var_run.portfolio, var_run.as_of_date, var_run.lookback_days
    )
    var_value = historical_var(returns, var_run.confidence)
    es = expected_shortfall(returns, var_run.confidence)
    breaches = count_breaches(returns, var_value)
    pvalue = kupiec_pof_pvalue(breaches, len(returns), var_run.confidence)

    return {
        "var_value": var_value,
        "expected_shortfall": es,
        "breach_count": breaches,
        "kupiec_pvalue": pvalue,
    }
