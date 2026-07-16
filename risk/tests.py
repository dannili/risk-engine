import datetime
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from risk.models import Portfolio, Position, PriceHistory, VarRun, VarResult
from risk.services import compute_input_hash


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


class ComputeInputHashTests(TestCase):
    def test_normalizes_confidence_precision(self):
        common = dict(
            portfolio_id=1,
            method="historical",
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
        )
        self.assertEqual(
            compute_input_hash(confidence=Decimal("0.95"), **common),
            compute_input_hash(confidence=Decimal("0.950"), **common),
        )

    def test_different_inputs_produce_different_hashes(self):
        common = dict(
            portfolio_id=1,
            method="historical",
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
        )
        self.assertNotEqual(
            compute_input_hash(**{**common, "lookback_days": 250}),
            compute_input_hash(**common),
        )


class PortfolioApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_portfolio(self):
        response = self.client.post(
            "/api/portfolios/", {"name": "Test", "base_currency": "USD"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Portfolio.objects.count(), 1)


class PositionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.portfolio = Portfolio.objects.create(name="Test", base_currency="USD")

    def test_create_position(self):
        response = self.client.post(
            f"/api/portfolios/{self.portfolio.id}/positions/",
            {"ticker": "AAPL", "quantity": "10.5"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        position = self.portfolio.positions.get()
        self.assertEqual(position.ticker, "AAPL")


class VarRunSubmissionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.portfolio = Portfolio.objects.create(name="Test", base_currency="USD")
        self.url = f"/api/portfolios/{self.portfolio.id}/var-runs/"
        self.payload = {
            "method": "historical",
            "confidence": 0.95,
            "lookback_days": 500,
            "as_of_date": "2026-07-14",
        }

    def test_returns_202_on_new_run(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending")
        self.assertIn("run_id", response.data)
        self.assertEqual(VarRun.objects.count(), 1)

    def test_duplicate_submission_returns_200_with_same_run_id(self):
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["run_id"], first.data["run_id"])
        self.assertEqual(VarRun.objects.count(), 1)

    def test_confidence_precision_does_not_create_a_second_run(self):
        first = self.client.post(self.url, self.payload, format="json")
        second_payload = {**self.payload, "confidence": 0.950}
        second = self.client.post(self.url, second_payload, format="json")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["run_id"], first.data["run_id"])
        self.assertEqual(VarRun.objects.count(), 1)


class VarRunDetailApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.portfolio = Portfolio.objects.create(name="Test", base_currency="USD")

    def test_pending_run_has_null_result(self):
        run = VarRun.objects.create(
            portfolio=self.portfolio,
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="abc123",
        )
        response = self.client.get(f"/api/var-runs/{run.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending")
        self.assertIsNone(response.data["result"])

    def test_complete_run_includes_result(self):
        run = VarRun.objects.create(
            portfolio=self.portfolio,
            confidence=0.95,
            lookback_days=500,
            as_of_date=datetime.date(2026, 7, 14),
            input_hash="abc123",
            status=VarRun.Status.COMPLETE,
        )
        VarResult.objects.create(
            var_run=run,
            var_value=Decimal("1234.5"),
            expected_shortfall=Decimal("1500.0"),
            breach_count=3,
            kupiec_pvalue=0.42,
        )
        response = self.client.get(f"/api/var-runs/{run.id}/")
        self.assertIsNotNone(response.data["result"])
        self.assertEqual(response.data["result"]["breach_count"], 3)


class VarRunEnqueueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.portfolio = Portfolio.objects.create(name="Test", base_currency="USD")
        self.url = f"/api/portfolios/{self.portfolio.id}/var-runs/"
        self.payload = {
            "method": "historical",
            "confidence": 0.95,
            "lookback_days": 500,
            "as_of_date": "2026-07-14",
        }

    def test_new_run_enqueues_exactly_one_task(self):
        with patch("risk.views.run_var_run.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 202)
        mock_delay.assert_called_once_with(response.data["run_id"])

    def test_duplicate_submission_enqueues_no_task(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 202)

        with patch("risk.views.run_var_run.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                second = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["run_id"], first.data["run_id"])
        mock_delay.assert_not_called()
