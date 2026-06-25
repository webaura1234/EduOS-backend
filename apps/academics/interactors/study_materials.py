"""Shared serializers/helpers for study materials (folder grouping)."""

from apps.academics.helpers import batch_display_label


def material_dict(m, *, include_units=False) -> dict:
    row = {
        "id": str(m.id),
        "classSectionId": str(m.batch_id),
        "classLabel": batch_display_label(m.batch),
        "folderId": str(m.folder_id) if m.folder_id else None,
        "folderName": m.folder.name if m.folder_id else None,
        "fileName": m.file_name,
        "s3Key": m.s3_key,
        "url": m.url,
        "uploadedAt": m.created_at.isoformat(),
        "uploadedByUserId": str(m.uploaded_by_id) if m.uploaded_by_id else "",
    }
    if include_units:
        row["unitTitles"] = []
    return row


def folder_summary(f, material_count: int) -> dict:
    return {
        "id": str(f.id),
        "classSectionId": str(f.batch_id),
        "name": f.name,
        "sortOrder": f.sort_order,
        "materialCount": material_count,
    }


def group_materials(materials) -> dict:
    """Group material rows into folders + general (no folder)."""
    folders_map: dict[str, dict] = {}
    general = []
    for m in materials:
        row = material_dict(m, include_units=True)
        if m.folder_id:
            fid = str(m.folder_id)
            entry = folders_map.setdefault(fid, {
                "id": fid,
                "name": m.folder.name,
                "materials": [],
            })
            entry["materials"].append(row)
        else:
            general.append(row)
    folders = sorted(folders_map.values(), key=lambda f: f["name"].lower())
    return {"folders": folders, "general": general}
