from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from risk.models import VarResult, VarRun
from risk.var_engine import compute_var_run


@shared_task
def run_var_run(run_id):
    run = VarRun.objects.get(pk=run_id)
    VarRun.objects.filter(pk=run_id).update(status=VarRun.Status.RUNNING)

    try:
        result = compute_var_run(run)
    except Exception as exc:
        # Never leave a run stuck in "running": any failure in the
        # computation terminates the run with the error persisted.
        VarRun.objects.filter(pk=run_id).update(
            status=VarRun.Status.FAILED,
            error=str(exc),
            completed_at=timezone.now(),
        )
        return

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
