from .calendar import AcademicPeriod, AcademicYear, Holiday, HolidayType, PeriodType
from .rollover import AcademicRolloverRun, RolloverRunStatus
from .curriculum import BatchFaculty, BatchFacultyRole, BatchSubject, Subject, SubjectType
from .structure import Batch, Course, Department, DepartmentType
from .timetable import (
    DayOfWeek,
    PeriodSlot,
    Room,
    Timetable,
    TimetableEntry,
    TimetableEntryStatus,
)

Grade = Course
Section = Batch

__all__ = [
    "AcademicYear",
    "AcademicPeriod",
    "PeriodType",
    "Holiday",
    "HolidayType",
    "Department",
    "DepartmentType",
    "Course",
    "Grade",
    "Batch",
    "Section",
    "Subject",
    "SubjectType",
    "BatchSubject",
    "BatchFaculty",
    "BatchFacultyRole",
    "PeriodSlot",
    "Room",
    "Timetable",
    "TimetableEntry",
    "DayOfWeek",
    "TimetableEntryStatus",
    "AcademicRolloverRun",
    "RolloverRunStatus",
]
