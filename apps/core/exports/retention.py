"""Report export file retention helpers."""

from django.conf import settings
from django.utils.timezone import now, timedelta


def export_expires_at():
    """Return expires_at for a newly finalized READY export."""
    days = int(getattr(settings, "REPORT_EXPORT_RETENTION_DAYS", 90))
    return now() + timedelta(days=days)
