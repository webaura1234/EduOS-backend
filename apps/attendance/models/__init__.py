"""
Attendance models.

  AttendanceSession → a class-period for which attendance is taken
  AttendanceRecord  → one student's mark in a session
  LeaveRequest      → student/staff leave application
  AttendanceAudit   → immutable trail (corrections, late marks, geo failures)

Enums live in apps.attendance.enums.
"""

from apps.attendance.enums import (
    AttendanceStatus,
    AuditType,
    LeaveApplicantRole,
    LeaveStatus,
    SessionStatus,
)

from .audit import AttendanceAudit
from .leave import LeaveRequest
from .record import AttendanceRecord
from .session import AttendanceSession

__all__ = [
    "AttendanceSession",
    "AttendanceRecord",
    "LeaveRequest",
    "AttendanceAudit",
    "SessionStatus",
    "AttendanceStatus",
    "LeaveApplicantRole",
    "LeaveStatus",
    "AuditType",
]
