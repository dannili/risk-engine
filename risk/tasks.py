import time

from celery import shared_task
from django.utils import timezone

from risk.models import VarRun


@shared_task
def run_var_run(run_id):
    """STUB — stage 3b replaces this body with the real computation:
    load price_history, compute historical VaR / expected shortfall,
    run the Kupiec backtest, and write a VarResult. For now this only
    proves the pending -> running -> complete transition works end to end.
    """
    VarRun.objects.filter(pk=run_id).update(status=VarRun.Status.RUNNING)
    time.sleep(1)
    VarRun.objects.filter(pk=run_id).update(
        status=VarRun.Status.COMPLETE, completed_at=timezone.now()
    )
