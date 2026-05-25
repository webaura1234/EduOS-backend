import factory
from factory.django import DjangoModelFactory

from apps.organizations.models.tenant import Tenant, Branch, InstitutionType, InstitutionStatus


class TenantFactory(DjangoModelFactory):
    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"Tenant {n}")
    subdomain = factory.Sequence(lambda n: f"tenant-{n}")
    institution_type = InstitutionType.SCHOOL
    status = InstitutionStatus.ACTIVE


class BranchFactory(DjangoModelFactory):
    class Meta:
        model = Branch

    tenant = factory.SubFactory(TenantFactory)
    name = factory.Sequence(lambda n: f"Branch {n}")
    code = factory.Sequence(lambda n: f"B{n}")
