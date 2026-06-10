import datetime

import factory
from factory.django import DjangoModelFactory

from apps.attendance.enums import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceRecord, AttendanceSession, LeaveRequest


class AttendanceSessionFactory(DjangoModelFactory):
    class Meta:
        model = AttendanceSession

    date = factory.LazyFunction(datetime.date.today)
    status = SessionStatus.COMPLETED
    mode = "session"


class AttendanceRecordFactory(DjangoModelFactory):
    class Meta:
        model = AttendanceRecord

    status = AttendanceStatus.PRESENT
    marked_at = factory.LazyFunction(datetime.datetime.now)
    idempotency_key = factory.Sequence(lambda n: f"key-{n}")


class LeaveRequestFactory(DjangoModelFactory):
    class Meta:
        model = LeaveRequest

    from_date = factory.LazyFunction(datetime.date.today)
    to_date = factory.LazyFunction(datetime.date.today)
