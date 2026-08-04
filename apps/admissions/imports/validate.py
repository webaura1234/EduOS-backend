"""Validate mapped student-import rows."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from apps.admissions.imports.columns import CANONICAL_COLUMNS
from apps.admissions.imports.mapping import apply_mapping
from apps.admissions.models.student_import import StudentImportMode
from apps.admissions.queries import provisioning as prov_q
from apps.academics.models.structure import Batch
from apps.fees.models.structure import FeeStructure

GENDER_VALUES = {"male", "female", "other", "m", "f", "boy", "girl"}
MAX_VALIDATE_ROWS = 5000


def _parse_dob(value: str):
    if not value:
        return None, None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date(), None
        except ValueError:
            continue
    return None, f"Invalid date of birth '{value}' (use YYYY-MM-DD)."


def _normalize_gender(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    if v in {"m", "male", "boy"}:
        return "male"
    if v in {"f", "female", "girl"}:
        return "female"
    if v == "other":
        return "other"
    return v


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return 10 <= len(digits) <= 15


def resolve_batch(*, branch_id, academic_year_id, class_name: str, section_name: str) -> Batch | None:
    if not class_name or not section_name:
        return None
    return (
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            academic_year_id=academic_year_id,
            is_active=True,
            course__is_active=True,
            course__name__iexact=class_name.strip(),
            name__iexact=section_name.strip(),
        )
        .select_related("course", "academic_year")
        .first()
    )


def resolve_fee_structure(*, branch_id, name: str) -> FeeStructure | None:
    if not name:
        return None
    return FeeStructure.objects.filter(
        branch_id=branch_id, is_active=True, name__iexact=name.strip()
    ).first()


def validate_rows(
    *,
    raw_rows: list[dict[str, str]],
    mapping: dict[str, str],
    mode: str,
    branch,
    academic_year,
    tenant,
) -> dict[str, Any]:
    if len(raw_rows) > MAX_VALIDATE_ROWS:
        raise ValueError(f"File has too many rows (max {MAX_VALIDATE_ROWS} for validation).")

    required_keys = [
        c["key"]
        for c in CANONICAL_COLUMNS
        if (mode == StudentImportMode.UPDATE and c["required_update"])
        or (mode != StudentImportMode.UPDATE and c["required_create"])
    ]

    seen_admissions: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    valid = warnings = errors = 0

    for idx, raw in enumerate(raw_rows, start=2):  # 1-based spreadsheet row (header=1)
        mapped = apply_mapping(raw, mapping)
        row_errors: list[str] = []
        row_warnings: list[str] = []

        for key in required_keys:
            if not mapped.get(key):
                label = next((c["label"] for c in CANONICAL_COLUMNS if c["key"] == key), key)
                row_errors.append(f"{label} is required.")

        adm = (mapped.get("admission_number") or "").strip()
        if adm:
            if adm in seen_admissions:
                row_errors.append(
                    f"Duplicate admission number in file (also on row {seen_admissions[adm]})."
                )
            else:
                seen_admissions[adm] = idx

        dob, dob_err = _parse_dob(mapped.get("date_of_birth") or "")
        if dob_err:
            row_errors.append(dob_err)

        gender_raw = mapped.get("gender") or ""
        gender = _normalize_gender(gender_raw)
        if gender_raw and gender not in {"male", "female", "other"}:
            row_errors.append(f"Invalid gender '{gender_raw}'.")

        for phone_key in ("student_mobile", "parent_mobile"):
            phone = mapped.get(phone_key) or ""
            if phone and not _looks_like_phone(phone):
                row_errors.append(f"Invalid phone format for {phone_key}.")

        batch = None
        class_name = mapped.get("class") or ""
        section_name = mapped.get("section") or ""
        if class_name or section_name:
            batch = resolve_batch(
                branch_id=branch.pk,
                academic_year_id=academic_year.pk,
                class_name=class_name,
                section_name=section_name,
            )
            if not batch and (mode != StudentImportMode.UPDATE or class_name or section_name):
                if mode == StudentImportMode.UPDATE and not class_name and not section_name:
                    pass
                elif class_name and section_name:
                    row_errors.append(
                        f"Class '{class_name}' section '{section_name}' not found for this academic year."
                    )

        fee = None
        fee_name = mapped.get("fee_structure") or ""
        if fee_name:
            fee = resolve_fee_structure(branch_id=branch.pk, name=fee_name)
            if not fee:
                row_warnings.append(f"Fee structure '{fee_name}' not found — will skip fee assignment.")
        elif mode != StudentImportMode.UPDATE:
            row_warnings.append("No fee structure specified.")

        exists = bool(adm) and prov_q.custom_login_id_taken(tenant.pk, adm)
        action = "skip"
        if mode == StudentImportMode.CREATE:
            if exists:
                row_errors.append("Student with this admission number already exists.")
            else:
                action = "create"
        elif mode == StudentImportMode.UPDATE:
            if not exists:
                row_errors.append("No existing student with this admission number.")
            else:
                action = "update"
        else:  # upsert
            if exists:
                action = "update"
                row_warnings.append("Admission number exists — will update.")
            else:
                action = "create"

        severity = "valid"
        if row_errors:
            severity = "error"
            errors += 1
        elif row_warnings:
            severity = "warning"
            warnings += 1
            valid += 1
        else:
            valid += 1

        results.append(
            {
                "rowNumber": idx,
                "severity": severity,
                "action": action,
                "errors": row_errors,
                "warnings": row_warnings,
                "data": {
                    **mapped,
                    "date_of_birth": dob.isoformat() if dob else (mapped.get("date_of_birth") or ""),
                    "gender": gender,
                    "batchId": str(batch.pk) if batch else "",
                    "feeStructureId": str(fee.pk) if fee else "",
                },
            }
        )

    return {
        "valid": valid,
        "warnings": warnings,
        "errors": errors,
        "total": len(results),
        "rows": results,
    }
