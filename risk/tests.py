import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from risk.models import Portfolio, Position, PriceHistory, VarRun, VarResult
from risk.services import compute_input_hash
from risk.tasks import run_var_run
from risk.var_engine import (
    count_breaches,
    expected_shortfall,
    historical_var,
    kupiec_pof_pvalue,
)


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


class LoadPricesCommandTests(TestCase):
    @patch("risk.management.commands.load_prices.fetch_prices")
    def test_loads_prices_and_prints_summary(self, mock_fetch):
        mock_fetch.return_value = [
            (datetime.date(2026, 1, 2), Decimal("100.00")),
            (datetime.date(2026, 1, 3), Decimal("101.50")),
        ]
        out = StringIO()
        call_command(
            "load_prices", "aapl", "--start", "2026-01-01", "--end", "2026-01-05",
            stdout=out,
        )

        self.assertEqual(PriceHistory.objects.filter(ticker="AAPL").count(), 2)
        self.assertIn("AAPL: 2", out.getvalue())

    @patch("risk.management.commands.load_prices.fetch_prices")
    def test_rerunning_upserts_without_violating_unique_constraint(self, mock_fetch):
        mock_fetch.return_value = [(datetime.date(2026, 1, 2), Decimal("100.00"))]
        call_command("load_prices", "AAPL", "--start", "2026-01-01", "--end", "2026-01-05")
        mock_fetch.return_value = [(datetime.date(2026, 1, 2), Decimal("105.00"))]
        call_command("load_prices", "AAPL", "--start", "2026-01-01", "--end", "2026-01-05")

        self.assertEqual(PriceHistory.objects.filter(ticker="AAPL").count(), 1)
        self.assertEqual(
            PriceHistory.objects.get(ticker="AAPL", date=datetime.date(2026, 1, 2)).close,
            Decimal("105.00"),
        )

    @patch("risk.management.commands.load_prices.fetch_prices")
    def test_ticker_with_no_data_warns_and_continues(self, mock_fetch):
        mock_fetch.return_value = []
        out, err = StringIO(), StringIO()
        call_command(
            "load_prices", "BADTICKER", "--start", "2026-01-01", "--end", "2026-01-05",
            stdout=out, stderr=err,
        )

        self.assertIn("No data for BADTICKER", err.getvalue())
        self.assertIn("BADTICKER: 0", out.getvalue())
        self.assertEqual(PriceHistory.objects.filter(ticker="BADTICKER").count(), 0)

    @patch("risk.management.commands.load_prices.fetch_prices")
    def test_one_bad_ticker_does_not_stop_the_others(self, mock_fetch):
        def side_effect(ticker, start, end):
            if ticker == "GOOD":
                return [(datetime.date(2026, 1, 2), Decimal("50.00"))]
            return []

        mock_fetch.side_effect = side_effect
        out = StringIO()
        call_command(
            "load_prices", "GOOD", "BAD", "--start", "2026-01-01", "--end", "2026-01-05",
            stdout=out, stderr=StringIO(),
        )

        self.assertEqual(PriceHistory.objects.filter(ticker="GOOD").count(), 1)
        self.assertEqual(PriceHistory.objects.filter(ticker="BAD").count(), 0)


class HistoricalVarMathTests(TestCase):
    # sorted ascending: -.04 -.03 -.02 -.01 -.005 .01 .01 .015 .02 .03
    # confidence=0.90, n=10 -> index = floor(0.10*10) = 1 -> sorted[1] = -.03
    RETURNS = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.015, -0.005, 0.01, -0.04]

    def test_historical_var_known_series(self):
        self.assertAlmostEqual(historical_var(self.RETURNS, confidence=0.90), 0.03)

    def test_expected_shortfall_known_series(self):
        # tail = sorted[:2] = [-.04, -.03] -> mean -.035 -> ES = .035
        self.assertAlmostEqual(
            expected_shortfall(self.RETURNS, confidence=0.90), 0.035
        )

    def test_empty_series_raises(self):
        with self.assertRaises(ValueError):
            historical_var([], confidence=0.90)


class CountBreachesTests(TestCase):
    def test_breach_counting_on_constructed_series(self):
        # losses: .10 .06 .02 -.01 -.05 ; only .10 and .06 exceed .05
        returns = [-0.10, -0.06, -0.02, 0.01, 0.05]
        self.assertEqual(count_breaches(returns, var_value=0.05), 2)

    def test_loss_equal_to_threshold_is_not_a_breach(self):
        self.assertEqual(count_breaches([-0.05], var_value=0.05), 0)


class KupiecPofTests(TestCase):
    def test_pvalue_is_one_when_breach_rate_matches_expected_exactly(self):
        # x/n = 5/100 = 0.05 = 1 - confidence -> LR statistic is exactly 0
        pvalue = kupiec_pof_pvalue(breaches=5, n=100, confidence=0.95)
        self.assertAlmostEqual(pvalue, 1.0, places=9)

    def test_pvalue_is_tiny_when_breach_rate_is_wildly_off(self):
        pvalue = kupiec_pof_pvalue(breaches=50, n=100, confidence=0.95)
        self.assertLess(pvalue, 1e-10)


class VarComputationTaskTests(TestCase):
    def setUp(self):
        self.portfolio = Portfolio.objects.create(name="Test", base_currency="USD")
        Position.objects.create(portfolio=self.portfolio, ticker="AAPL", quantity=Decimal("10"))

    @staticmethod
    def _load_prices(ticker, closes, start_date):
        for i, close in enumerate(closes):
            PriceHistory.objects.create(
                ticker=ticker,
                date=start_date + datetime.timedelta(days=i),
                close=Decimal(str(close)),
            )

    def test_successful_run_writes_result_and_completes(self):
        closes = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 95]  # 11 closes -> 10 returns
        start = datetime.date(2026, 1, 1)
        self._load_prices("AAPL", closes, start)
        as_of_date = start + datetime.timedelta(days=len(closes) - 1)

        run = VarRun.objects.create(
            portfolio=self.portfolio,
            confidence=0.90,
            lookback_days=10,
            as_of_date=as_of_date,
            input_hash="hash-success",
        )
        run_var_run(run.id)  # call the task function directly, no broker needed

        run.refresh_from_db()
        self.assertEqual(run.status, VarRun.Status.COMPLETE)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.error)

        result = run.results.get()
        self.assertGreater(result.var_value, 0)
        self.assertGreaterEqual(result.expected_shortfall, result.var_value)
        self.assertGreaterEqual(result.breach_count, 0)
        self.assertTrue(0 <= result.kupiec_pvalue <= 1)

    def test_insufficient_data_sets_status_failed_with_error(self):
        self._load_prices("AAPL", [100, 101, 99], datetime.date(2026, 1, 1))  # only 3, need 11

        run = VarRun.objects.create(
            portfolio=self.portfolio,
            confidence=0.90,
            lookback_days=10,
            as_of_date=datetime.date(2026, 1, 3),
            input_hash="hash-insufficient",
        )
        run_var_run(run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, VarRun.Status.FAILED)
        self.assertIsNotNone(run.completed_at)
        self.assertIn("Insufficient price history", run.error)
        self.assertEqual(run.results.count(), 0)

    def test_portfolio_with_no_positions_fails(self):
        empty_portfolio = Portfolio.objects.create(name="Empty", base_currency="USD")
        run = VarRun.objects.create(
            portfolio=empty_portfolio,
            confidence=0.90,
            lookback_days=10,
            as_of_date=datetime.date(2026, 1, 1),
            input_hash="hash-empty",
        )
        run_var_run(run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, VarRun.Status.FAILED)
        self.assertIn("no positions", run.error)
