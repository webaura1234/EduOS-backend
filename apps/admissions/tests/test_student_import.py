"""Tests for student bulk import parse / validate / apply / job runner."""

import pytest
from django.test import override_settings

from apps.accounts.models.user import Role, User
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory, CourseFactory, DepartmentFactory
from apps.admissions.imports.apply import apply_row
from apps.admissions.imports.mapping import auto_map_columns, apply_mapping
from apps.admissions.imports.parse import build_csv_template, parse_csv_bytes, parse_upload
from apps.admissions.imports.runner import execute_import_job
from apps.admissions.imports.validate import validate_rows
from apps.admissions.models.student_import import (
    StudentImportJob,
    StudentImportMode,
    StudentImportStatus,
)
from apps.admissions.queries import student_import as job_q
from apps.organizations.tests.factories import BranchFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def school_ctx():
    branch = BranchFactory()
    year = AcademicYearFactory(branch=branch, is_current=True)
    dept = DepartmentFactory(branch=branch)
    course = CourseFactory(department=dept, name="Class 5")
    batch = BatchFactory(course=course, academic_year=year, name="A")
    return {"branch": branch, "year": year, "batch": batch, "tenant": branch.tenant}


def test_parse_csv_and_auto_map():
    content = build_csv_template()
    headers, rows = parse_csv_bytes(content)
    assert "admission_number" in headers
    assert len(rows) >= 2
    mapping = auto_map_columns(headers)
    assert mapping["admission_number"] == "admission_number"
    assert mapping["first_name"] == "first_name"
    projected = apply_mapping(rows[0], mapping)
    assert projected["admission_number"]


def test_auto_map_aliases():
    headers = ["Adm No", "First Name", "Class", "Section", "Parent Name", "Parent Mobile"]
    mapping = auto_map_columns(headers)
    assert mapping["admission_number"] == "Adm No"
    assert mapping["first_name"] == "First Name"
    assert mapping["class"] == "Class"


def test_validate_detects_duplicate_in_file(school_ctx):
    raw = [
        {
            "Adm No": "ADM-1",
            "First Name": "A",
            "Class": "Class 5",
            "Section": "A",
            "Parent Name": "P",
            "Parent Mobile": "+919876543210",
        },
        {
            "Adm No": "ADM-1",
            "First Name": "B",
            "Class": "Class 5",
            "Section": "A",
            "Parent Name": "P",
            "Parent Mobile": "+919876543211",
        },
    ]
    mapping = auto_map_columns(list(raw[0].keys()))
    result = validate_rows(
        raw_rows=raw,
        mapping=mapping,
        mode=StudentImportMode.CREATE,
        branch=school_ctx["branch"],
        academic_year=school_ctx["year"],
        tenant=school_ctx["tenant"],
    )
    assert result["errors"] >= 1
    assert any("Duplicate" in e for r in result["rows"] for e in r["errors"])


def test_validate_bad_class(school_ctx):
    raw = [
        {
            "admission_number": "ADM-9",
            "first_name": "A",
            "class": "Missing",
            "section": "Z",
            "parent_name": "P",
            "parent_mobile": "+919876543210",
        }
    ]
    mapping = auto_map_columns(list(raw[0].keys()))
    result = validate_rows(
        raw_rows=raw,
        mapping=mapping,
        mode=StudentImportMode.CREATE,
        branch=school_ctx["branch"],
        academic_year=school_ctx["year"],
        tenant=school_ctx["tenant"],
    )
    assert result["errors"] == 1


def test_create_and_update_row(school_ctx):
    data = {
        "admission_number": "ADM-100",
        "first_name": "Aarav",
        "last_name": "Test",
        "class": "Class 5",
        "section": "A",
        "parent_name": "Parent One",
        "parent_mobile": "+919811122233",
        "batchId": str(school_ctx["batch"].pk),
        "gender": "male",
    }
    created = apply_row(
        action="create",
        branch=school_ctx["branch"],
        academic_year=school_ctx["year"],
        data=data,
    )
    assert created["status"] == "completed"
    user = User.objects.get(custom_login_id="ADM-100", tenant=school_ctx["tenant"])
    assert user.role == Role.STUDENT

    data["first_name"] = "AaravUpdated"
    updated = apply_row(
        action="update",
        branch=school_ctx["branch"],
        academic_year=school_ctx["year"],
        data=data,
    )
    assert updated["status"] == "updated"
    user.refresh_from_db()
    assert user.first_name == "AaravUpdated"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_execute_import_job_writes_errors(school_ctx):
    rows = [
        {
            "rowNumber": 2,
            "severity": "valid",
            "action": "create",
            "errors": [],
            "warnings": [],
            "data": {
                "admission_number": "ADM-200",
                "first_name": "Ok",
                "last_name": "Student",
                "parent_name": "Parent",
                "parent_mobile": "+919800011122",
                "batchId": str(school_ctx["batch"].pk),
            },
        },
        {
            "rowNumber": 3,
            "severity": "error",
            "action": "skip",
            "errors": ["Class not found"],
            "warnings": [],
            "data": {"admission_number": "ADM-201", "first_name": "Bad"},
        },
    ]
    job = job_q.create_job(
        tenant=school_ctx["tenant"],
        branch=school_ctx["branch"],
        academic_year=school_ctx["year"],
        filename="t.csv",
        mode=StudentImportMode.CREATE,
        status=StudentImportStatus.QUEUED,
        total_rows=len(rows),
        mapping={},
        row_payload=rows,
    )
    execute_import_job(job_id=str(job.pk))
    job.refresh_from_db()
    assert job.status == StudentImportStatus.COMPLETED
    assert job.success_count == 1
    assert job.failed_count == 1
    assert job.error_report_key


def test_parse_upload_sniffs_csv():
    content = build_csv_template()
    headers, rows = parse_upload("roster.csv", content)
    assert headers
    assert rows
