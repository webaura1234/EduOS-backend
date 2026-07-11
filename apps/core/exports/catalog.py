"""Build report catalog metadata from the global registry."""

from apps.accounts.models.user import Role
from apps.core.exports.base import ExportDefinition
from apps.core.exports.params import filter_specs_to_dict
from apps.core.exports.registry import all_definitions


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


def catalog_for_user(user) -> list[dict]:
    """Return catalog entries visible to the requesting user."""
    entries = []
    for definition in all_definitions().values():
        if _visible_to_user(definition, user):
            entries.append(definition_to_catalog_entry(definition))
    entries.sort(key=lambda e: (e["module"], e["name"]))
    return entries
