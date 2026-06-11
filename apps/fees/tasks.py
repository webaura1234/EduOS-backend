"""Celery tasks for the fees app."""

import logging
from celery import shared_task

from apps.fees.interactors.reconciliation import ReconcilePendingPaymentInteractor

logger = logging.getLogger(__name__)


@shared_task
def reconcile_pending_payments(branch_id):
    """Reconciles payment attempts that are stuck in PENDING status."""
    logger.info("Starting pending payments reconciliation for branch %s", branch_id)
    try:
        interactor = ReconcilePendingPaymentInteractor(branch_id=branch_id)
        count = interactor.execute()
        logger.info("Reconciliation complete. Reconciled %d payments.", count)
        return count
    except Exception as exc:
        logger.exception("Reconciliation task failed for branch %s: %s", branch_id, exc)
        raise


@shared_task
def export_ledger_to_csv(branch_id, user_id):
    """Asynchronously generates a CSV file of the ledger and stores it (mocked stub)."""
    logger.info("Starting ledger export to CSV for branch %s by user %s", branch_id, user_id)
    # Simulate processing delay and write
    # In a real system, this would write to a CSV file and upload to AWS S3.
    # For Phase 1, we log success and return a mock S3 key.
    mock_s3_key = f"exports/branch_{branch_id}/ledger_export.csv"
    logger.info("Ledger export complete. S3 Key: %s", mock_s3_key)
    return mock_s3_key
