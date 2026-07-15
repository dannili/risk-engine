import hashlib
from decimal import Decimal


def compute_input_hash(portfolio_id, method, confidence, lookback_days, as_of_date):
    """Deterministic idempotency key for a VaR run request.

    Confidence is quantized to 4 decimal places so that equivalent values
    submitted with different precision (0.95 vs 0.950) hash identically.
    """
    normalized_confidence = f"{Decimal(str(confidence)):.4f}"
    as_of_date_str = (
        as_of_date if isinstance(as_of_date, str) else as_of_date.isoformat()
    )
    raw = f"{portfolio_id}|{method}|{normalized_confidence}|{lookback_days}|{as_of_date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()
