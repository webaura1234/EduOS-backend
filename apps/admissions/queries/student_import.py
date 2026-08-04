"""Queries for student import jobs and saved mappings."""

from apps.admissions.models.student_import import StudentImportJob, StudentImportMapping


def create_job(**kwargs) -> StudentImportJob:
    return StudentImportJob.objects.create(**kwargs)


def get_job(*, tenant_id, branch_id, job_id) -> StudentImportJob | None:
    try:
        return StudentImportJob.objects.select_related(
            "academic_year", "requested_by", "branch"
        ).get(pk=job_id, tenant_id=tenant_id, branch_id=branch_id, is_active=True)
    except (StudentImportJob.DoesNotExist, ValueError, TypeError):
        return None


def list_jobs(*, tenant_id, branch_id, limit=50):
    return list(
        StudentImportJob.objects.filter(
            tenant_id=tenant_id, branch_id=branch_id, is_active=True
        )
        .select_related("requested_by", "academic_year")
        .order_by("-created_at")[:limit]
    )


def update_job(job: StudentImportJob, fields: dict, user=None) -> StudentImportJob:
    for k, v in fields.items():
        setattr(job, k, v)
    if user is not None:
        job.updated_by = user
    job.save()
    return job


def list_mappings(*, tenant_id, branch_id):
    return list(
        StudentImportMapping.objects.filter(
            tenant_id=tenant_id, branch_id=branch_id, is_active=True
        ).order_by("name")
    )


def get_mapping(*, tenant_id, branch_id, mapping_id) -> StudentImportMapping | None:
    try:
        return StudentImportMapping.objects.get(
            pk=mapping_id, tenant_id=tenant_id, branch_id=branch_id, is_active=True
        )
    except (StudentImportMapping.DoesNotExist, ValueError, TypeError):
        return None


def upsert_mapping(*, tenant, branch, name, mapping, user=None) -> StudentImportMapping:
    obj = StudentImportMapping.objects.filter(
        tenant=tenant, branch=branch, name__iexact=name.strip(), is_active=True
    ).first()
    if obj:
        obj.mapping = mapping
        obj.updated_by = user
        if user:
            obj.updated_by = user
        obj.save()
        return obj
    return StudentImportMapping.objects.create(
        tenant=tenant,
        branch=branch,
        name=name.strip(),
        mapping=mapping,
        updated_by=user,
        created_by=user,
    )


def soft_delete_mapping(mapping: StudentImportMapping, user=None) -> None:
    mapping.soft_delete(user=user)
