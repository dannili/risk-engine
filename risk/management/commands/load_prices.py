import datetime

from django.core.management.base import BaseCommand, CommandError

from risk.models import PriceHistory
from risk.price_sources import fetch_prices


class Command(BaseCommand):
    help = "Fetch daily close prices and upsert them into price_history."

    def add_arguments(self, parser):
        parser.add_argument("tickers", nargs="+", type=str)
        parser.add_argument("--start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        start = self._parse_date(options["start"])
        end = self._parse_date(options["end"])
        tickers = [t.upper() for t in options["tickers"]]

        summary = {}
        for ticker in tickers:
            rows = fetch_prices(ticker, start, end)
            if not rows:
                self.stderr.write(
                    self.style.WARNING(f"No data for {ticker}; skipping.")
                )
                summary[ticker] = 0
                continue

            count = 0
            for price_date, close in rows:
                PriceHistory.objects.update_or_create(
                    ticker=ticker, date=price_date, defaults={"close": close}
                )
                count += 1
            summary[ticker] = count

        self.stdout.write("Rows loaded per ticker:")
        for ticker, count in summary.items():
            self.stdout.write(f"  {ticker}: {count}")

    @staticmethod
    def _parse_date(value):
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Invalid date '{value}', expected YYYY-MM-DD")
