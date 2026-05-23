from django.db import models


class TenantScopedMixin(models.Model):
    """
    Mixin for models that belong to a specific Tenant (Institution).
    """

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_list"
    )

    class Meta:
        abstract = True


class BranchScopedMixin(models.Model):
    """
    Mixin for models that belong to a specific Branch within a Tenant.
    """

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_list"
    )

    class Meta:
        abstract = True
