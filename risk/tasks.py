import logging
import time
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from risk.models import VarResult, VarRun
from risk.var_engine import compute_var_run

logger = logging.getLogger(__name__)


@shared_task
def run_var_run(run_id):
    run = VarRun.objects.get(pk=run_id)
    logger.info(
        "task received",
        extra={"run_id": run_id, "portfolio_id": run.portfolio_id},
    )

    VarRun.objects.filter(pk=run_id).update(status=VarRun.Status.RUNNING)
    position_count = run.portfolio.positions.count()
    logger.info(
        "computation started",
        extra={
            "run_id": run_id,
            "lookback_days": run.lookback_days,
            "position_count": position_count,
        },
    )

    started_at = time.monotonic()
    try:
        result = compute_var_run(run)
    except Exception as exc:
        # Never leave a run stuck in "running": any failure in the
        # computation terminates the run with the error persisted.
        logger.error(
            "computation failed",
            extra={"run_id": run_id, "error": str(exc)},
        )
        VarRun.objects.filter(pk=run_id).update(
            status=VarRun.Status.FAILED,
            error=str(exc),
            completed_at=timezone.now(),
        )
        return

    duration_ms = round((time.monotonic() - started_at) * 1000, 2)

    VarResult.objects.create(
        var_run=run,
        var_value=Decimal(str(result["var_value"])),
        expected_shortfall=Decimal(str(result["expected_shortfall"])),
        breach_count=result["breach_count"],
        kupiec_pvalue=result["kupiec_pvalue"],
    )
    VarRun.objects.filter(pk=run_id).update(
        status=VarRun.Status.COMPLETE, completed_at=timezone.now()
    )
    logger.info(
        "computation completed",
        extra={
            "run_id": run_id,
            "var_value": result["var_value"],
            "breach_count": result["breach_count"],
            "duration_ms": duration_ms,
        },
    )
