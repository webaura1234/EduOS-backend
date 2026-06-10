"""
Queries — Branch reads and writes (all DB access for branches lives here).
"""

from apps.organizations.models import Branch


def list_branches(tenant_id):
    """All branches for a tenant, primary first then alphabetical."""
    return Branch.objects.filter(tenant_id=tenant_id).order_by("-is_primary", "name")


def get_branch(tenant_id, branch_id) -> Branch | None:
    """A single branch scoped to the tenant, or None."""
    try:
        return Branch.objects.get(tenant_id=tenant_id, pk=branch_id)
    except (Branch.DoesNotExist, ValueError, TypeError):
        return None


def branch_name_exists(tenant_id, name: str) -> bool:
    return Branch.objects.filter(tenant_id=tenant_id, name__iexact=name).exists()


def branch_code_exists(tenant_id, code: str) -> bool:
    return bool(code) and Branch.objects.filter(tenant_id=tenant_id, code__iexact=code).exists()


def create_branch(tenant_id, name: str, code: str = "", city: str = "") -> Branch:
    return Branch.objects.create(
        tenant_id=tenant_id, name=name, code=code or "", city=city or ""
    )


def set_branch_active(branch: Branch, is_active: bool) -> Branch:
    """Activate / deactivate a branch (BaseModel.is_active soft-state)."""
    branch.is_active = is_active
    branch.save(update_fields=["is_active"])
    return branch


def update_branch_settings(branch: Branch, fields: dict) -> Branch:
    """Update branch settings (geo-fence coordinates and radius)."""
    update_fields: list[str] = []
    mapping = {
        "latitude": "latitude",
        "longitude": "longitude",
        "geofenceRadiusM": "geofence_radius_m",
    }
    for key, attr in mapping.items():
        if key in fields:
            setattr(branch, attr, fields[key])
            update_fields.append(attr)
    if update_fields:
        branch.save(update_fields=update_fields)
    return branch
