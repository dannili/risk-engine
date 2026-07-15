from django.db import models


class Portfolio(models.Model):
    name = models.CharField(max_length=255)
    base_currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "portfolios"

    def __str__(self):
        return self.name


class Position(models.Model):
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="positions"
    )
    ticker = models.CharField(max_length=32)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        db_table = "positions"
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "ticker"], name="uq_position_portfolio_ticker"
            )
        ]

    def __str__(self):
        return f"{self.portfolio_id}:{self.ticker}"


class PriceHistory(models.Model):
    ticker = models.CharField(max_length=32)
    date = models.DateField()
    close = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        db_table = "price_history"
        constraints = [
            models.UniqueConstraint(
                fields=["ticker", "date"], name="uq_price_history_ticker_date"
            )
        ]
        indexes = [
            models.Index(fields=["ticker", "-date"], name="idx_price_history_ticker_date"),
        ]

    def __str__(self):
        return f"{self.ticker}@{self.date}"


class VarRun(models.Model):
    class Method(models.TextChoices):
        HISTORICAL = "historical", "Historical"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="var_runs"
    )
    method = models.CharField(
        max_length=32, choices=Method.choices, default=Method.HISTORICAL
    )
    confidence = models.FloatField()
    lookback_days = models.PositiveIntegerField()
    as_of_date = models.DateField()
    input_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "var_runs"

    def __str__(self):
        return f"VarRun({self.id}, {self.status})"


class VarResult(models.Model):
    var_run = models.ForeignKey(
        VarRun, on_delete=models.CASCADE, related_name="results"
    )
    var_value = models.DecimalField(max_digits=20, decimal_places=8)
    expected_shortfall = models.DecimalField(max_digits=20, decimal_places=8)
    breach_count = models.PositiveIntegerField()
    kupiec_pvalue = models.FloatField()
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "var_results"

    def __str__(self):
        return f"VarResult(run={self.var_run_id})"
