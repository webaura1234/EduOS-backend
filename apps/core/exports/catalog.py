"""Build report catalog metadata from the global registry."""

from apps.accounts.models.user import Role
from apps.core.exports.base import ExportDefinition
from apps.core.exports.params import filter_specs_to_dict
from apps.core.exports.registry import all_definitions
from apps.core.exports.year import academic_years_for_catalog


def _roles_for_user(user) -> set:
    role = getattr(user, "role", None)
    if role == Role.SUPER_ADMIN:
        return {Role.ADMIN, Role.SUPER_ADMIN, Role.FACULTY, Role.STUDENT}
    return {role} if role else set()


def _visible_to_user(definition: ExportDefinition, user) -> bool:
    if not definition.catalog_visible:
        return False
    if not definition.allowed_roles:
        return True
    return bool(_roles_for_user(user) & set(definition.allowed_roles))


def definition_to_catalog_entry(definition: ExportDefinition) -> dict:
    return {
        "id": definition.report_type,
        "module": definition.module,
        "name": definition.title,
        "description": definition.description,
        "filters": filter_specs_to_dict(definition.filters),
        "supportsPreview": definition.supports_preview,
        "supportsSearch": definition.supports_search,
        "defaultSort": {"key": definition.default_sort[0], "dir": definition.default_sort[1]},
        "estimatedRuntime": definition.estimated_runtime,
        "syncThreshold": definition.sync_threshold,
        "formats": list(definition.formats),
    }


def catalog_for_user(user, *, branch=None) -> dict:
    """Return catalog payload visible to the requesting user.

    Includes ``academicYears`` for the branch so the FE can default
    ``academicYearId`` without an extra round-trip. Super-admins also get
    ``branches`` for per-export branch selection.
    """
    entries = []
    for definition in all_definitions().values():
        if _visible_to_user(definition, user):
            entries.append(definition_to_catalog_entry(definition))
    entries.sort(key=lambda e: (e["module"], e["name"]))
    payload = {
        "reports": entries,
        "academicYears": academic_years_for_catalog(branch),
        "branches": [],
    }
    if getattr(user, "role", None) == Role.SUPER_ADMIN and getattr(user, "tenant_id", None):
        from apps.organizations.queries.branch import list_branches
        payload["branches"] = [
            {"id": str(b.pk), "name": b.name, "isPrimary": bool(b.is_primary)}
            for b in list_branches(user.tenant_id)
            if getattr(b, "is_active", True)
        ]
    return payload
