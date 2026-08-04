"""Views — student bulk import wizard API."""

from __future__ import annotations

import json
import uuid

from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.rollover import get_academic_year
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.imports.columns import CANONICAL_COLUMNS
from apps.admissions.imports.mapping import auto_map_columns
from apps.admissions.imports.parse import (
    ParseError,
    build_csv_template,
    build_xlsx_template,
    parse_upload,
)
from apps.admissions.imports.validate import validate_rows
from apps.admissions.models.student_import import StudentImportStatus
from apps.admissions.queries import student_import as job_q
from apps.admissions.serializers.student_import import (
    StudentImportMappingWriteSerializer,
    StudentImportStartJobSerializer,
    StudentImportValidateSerializer,
    serialize_job,
    serialize_mapping,
)
from apps.integrations.adapters.s3 import S3NotFoundError, get_s3_adapter

# In-process upload cache for sandbox / same-worker validate+start.
# Production stores bytes on S3 under file_key; cache speeds local validate.
_UPLOAD_CACHE: dict[str, dict] = {}


def _cache_put(upload_id: str, payload: dict) -> None:
    _UPLOAD_CACHE[upload_id] = payload
    # Keep cache bounded.
    if len(_UPLOAD_CACHE) > 64:
        oldest = next(iter(_UPLOAD_CACHE))
        _UPLOAD_CACHE.pop(oldest, None)


def _cache_get(upload_id: str) -> dict | None:
    return _UPLOAD_CACHE.get(upload_id)


def _load_upload(upload_id: str, tenant_id) -> dict:
    cached = _cache_get(upload_id)
    if cached and str(cached.get("tenant_id")) == str(tenant_id):
        return cached
    # Fall back to S3 JSON sidecar written at upload time.
    key = f"imports/{tenant_id}/uploads/{upload_id}.json"
    try:
        raw = get_s3_adapter().download(key=key)
    except S3NotFoundError as exc:
        raise FileNotFoundError("Upload expired or not found. Please re-upload the file.") from exc
    data = json.loads(raw.decode("utf-8"))
    _cache_put(upload_id, data)
    return data


class StudentImportTemplateCsvView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        content = build_csv_template()
        resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="student-import-template.csv"'
        return resp


class StudentImportTemplateXlsxView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        content = build_xlsx_template()
        resp = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="student-import-template.xlsx"'
        return resp


class StudentImportColumnsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        return Response(
            {
                "columns": [
                    {
                        "key": c["key"],
                        "label": c["label"],
                        "requiredCreate": c["required_create"],
                        "requiredUpdate": c["required_update"],
                    }
                    for c in CANONICAL_COLUMNS
                ]
            }
        )


class StudentImportUploadView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        branch = resolve_branch(request)
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        filename = upload.name or "students.csv"
        content = upload.read()
        if not content:
            return Response({"error": "File is empty"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            headers, rows = parse_upload(filename, content)
        except ParseError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        upload_id = str(uuid.uuid4())
        mapping = auto_map_columns(headers)
        payload = {
            "tenant_id": str(branch.tenant_id),
            "branch_id": str(branch.pk),
            "filename": filename,
            "headers": headers,
            "rows": rows,
            "mapping": mapping,
        }
        _cache_put(upload_id, payload)
        s3 = get_s3_adapter()
        s3.upload(
            key=f"imports/{branch.tenant_id}/uploads/{upload_id}.json",
            content=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        # Also keep original file for audit.
        s3.upload(
            key=f"imports/{branch.tenant_id}/uploads/{upload_id}/source",
            content=content,
            content_type=upload.content_type or "application/octet-stream",
        )
        return Response(
            {
                "uploadId": upload_id,
                "filename": filename,
                "headers": headers,
                "rowCount": len(rows),
                "suggestedMapping": mapping,
                "previewRows": rows[:5],
            },
            status=status.HTTP_201_CREATED,
        )


class StudentImportValidateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        ser = StudentImportValidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        academic_year = get_academic_year(data["academicYearId"])
        if not academic_year:
            return Response({"error": "Academic year not found."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            upload = _load_upload(data["uploadId"], branch.tenant_id)
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = validate_rows(
                raw_rows=upload["rows"],
                mapping=data["mapping"],
                mode=data["mode"],
                branch=branch,
                academic_year=academic_year,
                tenant=branch.tenant,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


class StudentImportJobListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        jobs = job_q.list_jobs(tenant_id=branch.tenant_id, branch_id=branch.pk)
        return Response({"jobs": [serialize_job(j) for j in jobs]})

    def post(self, request):
        branch = resolve_branch(request)
        ser = StudentImportStartJobSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        academic_year = get_academic_year(data["academicYearId"])
        if not academic_year:
            return Response({"error": "Academic year not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            upload = _load_upload(data["uploadId"], branch.tenant_id)
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        rows = data.get("rows")
        if not rows:
            try:
                validated = validate_rows(
                    raw_rows=upload["rows"],
                    mapping=data["mapping"],
                    mode=data["mode"],
                    branch=branch,
                    academic_year=academic_year,
                    tenant=branch.tenant,
                )
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            if validated["errors"] > 0:
                return Response(
                    {
                        "error": "Fix validation errors before importing.",
                        "valid": validated["valid"],
                        "warnings": validated["warnings"],
                        "errors": validated["errors"],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows = validated["rows"]
        else:
            # Client-supplied validated rows — refuse if any error severity remains.
            if any(r.get("severity") == "error" for r in rows):
                return Response(
                    {"error": "Fix validation errors before importing."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        job = job_q.create_job(
            tenant=branch.tenant,
            branch=branch,
            academic_year=academic_year,
            filename=upload.get("filename") or "students.csv",
            mode=data["mode"],
            status=StudentImportStatus.QUEUED,
            total_rows=len(rows),
            mapping=data["mapping"],
            row_payload=rows,
            file_key=f"imports/{branch.tenant_id}/uploads/{data['uploadId']}/source",
            requested_by=request.user,
            created_by=request.user,
        )

        from apps.admissions.tasks import run_student_import_job

        async_result = run_student_import_job.delay(str(job.pk))
        job.refresh_from_db()
        job_q.update_job(job, {"celery_task_id": getattr(async_result, "id", "") or ""})
        job.refresh_from_db()

        return Response({"job": serialize_job(job)}, status=status.HTTP_201_CREATED)


class StudentImportJobDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, job_id):
        branch = resolve_branch(request)
        job = job_q.get_job(tenant_id=branch.tenant_id, branch_id=branch.pk, job_id=job_id)
        if not job:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"job": serialize_job(job)})


class StudentImportJobErrorsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, job_id):
        branch = resolve_branch(request)
        job = job_q.get_job(tenant_id=branch.tenant_id, branch_id=branch.pk, job_id=job_id)
        if not job or not job.error_report_key:
            return Response({"error": "Error report not available"}, status=status.HTTP_404_NOT_FOUND)
        try:
            content = get_s3_adapter().download(key=job.error_report_key)
        except S3NotFoundError:
            return Response({"error": "Error report file missing"}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="import-errors-{job.pk}.csv"'
        return resp


class StudentImportMappingListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        mappings = job_q.list_mappings(tenant_id=branch.tenant_id, branch_id=branch.pk)
        return Response({"mappings": [serialize_mapping(m) for m in mappings]})

    def post(self, request):
        branch = resolve_branch(request)
        ser = StudentImportMappingWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        obj = job_q.upsert_mapping(
            tenant=branch.tenant,
            branch=branch,
            name=data["name"],
            mapping=data["mapping"],
            user=request.user,
        )
        return Response({"mapping": serialize_mapping(obj)}, status=status.HTTP_201_CREATED)


class StudentImportMappingDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def delete(self, request, mapping_id):
        branch = resolve_branch(request)
        obj = job_q.get_mapping(
            tenant_id=branch.tenant_id, branch_id=branch.pk, mapping_id=mapping_id
        )
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        job_q.soft_delete_mapping(obj, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
