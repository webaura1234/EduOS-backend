"""Celery tasks — daily notification scans."""

from celery import shared_task


@shared_task
def run_daily_notification_scans():
    from apps.communications.interactors.triggers.attendance import run_attendance_shortage_scan
    from apps.communications.interactors.triggers.fees import run_fee_notification_scan

    fee_count = run_fee_notification_scan()
    att_count = run_attendance_shortage_scan()
    return {"feeNotifications": fee_count, "attendanceNotifications": att_count}
