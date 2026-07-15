import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from risk.models import Portfolio, Position, PriceHistory, VarRun, VarResult


class PortfolioTests(TestCase):
    def test_create(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        self.assertIsNotNone(p.created_at)


class PositionUniqueConstraintTests(TestCase):
    def test_duplicate_ticker_per_portfolio_rejected(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        Position.objects.create(portfolio=p, ticker="AAPL", quantity=Decimal("10"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Position.objects.create(portfolio=p, ticker="AAPL", quantity=Decimal("5"))

    def test_same_ticker_different_portfolios_allowed(self):
        p1 = Portfolio.objects.create(name="P1", base_currency="USD")
        p2 = Portfolio.objects.create(name="P2", base_currency="USD")
        Position.objects.create(portfolio=p1, ticker="AAPL", quantity=Decimal("10"))
        Position.objects.create(portfolio=p2, ticker="AAPL", quantity=Decimal("10"))
        self.assertEqual(Position.objects.filter(ticker="AAPL").count(), 2)


class PriceHistoryUniqueConstraintTests(TestCase):
    def test_duplicate_ticker_date_rejected(self):
        PriceHistory.objects.create(
            ticker="AAPL", date=datetime.date(2026, 7, 10), close=Decimal("150.25")
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PriceHistory.objects.create(
                ticker="AAPL", date=datetime.date(2026, 7, 10), close=Decimal("999")
            )


class VarRunUniqueConstraintTests(TestCase):
    def test_duplicate_input_hash_rejected(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        VarRun.objects.create(
            portfolio=p,
            method="historical",
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="abc123",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            VarRun.objects.create(
                portfolio=p,
                method="historical",
                confidence=0.99,
                lookback_days=250,
                as_of_date=datetime.date(2026, 7, 14),
                input_hash="abc123",
            )

    def test_defaults(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        run = VarRun.objects.create(
            portfolio=p,
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="def456",
        )
        self.assertEqual(run.status, VarRun.Status.PENDING)
        self.assertEqual(run.method, VarRun.Method.HISTORICAL)
        self.assertIsNone(run.completed_at)


class CascadeDeleteTests(TestCase):
    def test_deleting_portfolio_cascades_to_positions_and_var_runs(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        Position.objects.create(portfolio=p, ticker="AAPL", quantity=Decimal("10"))
        VarRun.objects.create(
            portfolio=p,
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="abc123",
        )
        p.delete()
        self.assertEqual(Position.objects.count(), 0)
        self.assertEqual(VarRun.objects.count(), 0)

    def test_deleting_var_run_cascades_to_var_results(self):
        p = Portfolio.objects.create(name="Test", base_currency="USD")
        run = VarRun.objects.create(
            portfolio=p,
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="abc123",
        )
        VarResult.objects.create(
            var_run=run,
            var_value=Decimal("1234.5"),
            expected_shortfall=Decimal("1500.0"),
            breach_count=3,
            kupiec_pvalue=0.42,
        )
        run.delete()
        self.assertEqual(VarResult.objects.count(), 0)
