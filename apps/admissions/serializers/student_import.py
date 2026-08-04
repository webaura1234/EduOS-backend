"""Serializers — student import API (camelCase)."""

from rest_framework import serializers

from apps.admissions.models.student_import import StudentImportMode


class StudentImportValidateSerializer(serializers.Serializer):
    uploadId = serializers.CharField()
    mapping = serializers.DictField(child=serializers.CharField(allow_blank=True))
    mode = serializers.ChoiceField(choices=StudentImportMode.values)
    academicYearId = serializers.UUIDField()


class StudentImportStartJobSerializer(serializers.Serializer):
    uploadId = serializers.CharField()
    mapping = serializers.DictField(child=serializers.CharField(allow_blank=True))
    mode = serializers.ChoiceField(choices=StudentImportMode.values)
    academicYearId = serializers.UUIDField()
    # Optional: validated rows from client (preferred) — otherwise re-validate server-side.
    rows = serializers.ListField(child=serializers.DictField(), required=False)


class StudentImportMappingWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    mapping = serializers.DictField(child=serializers.CharField(allow_blank=True))


def serialize_job(job) -> dict:
    return {
        "id": str(job.pk),
        "filename": job.filename,
        "mode": job.mode,
        "status": job.status,
        "totalRows": job.total_rows,
        "successCount": job.success_count,
        "failedCount": job.failed_count,
        "warningCount": job.warning_count,
        "processedCount": job.processed_count,
        "error": job.error,
        "hasErrorReport": bool(job.error_report_key),
        "academicYearId": str(job.academic_year_id) if job.academic_year_id else None,
        "academicYearName": job.academic_year.name if job.academic_year_id else None,
        "importedBy": (
            job.requested_by.full_name if job.requested_by_id else None
        ),
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }


def serialize_mapping(m) -> dict:
    return {
        "id": str(m.pk),
        "name": m.name,
        "mapping": m.mapping or {},
        "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
    }
