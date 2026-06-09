import datetime

import factory
from factory.django import DjangoModelFactory

from apps.organizations.models import (
    Branch,
    FeatureFlag,
    InstitutionStatus,
    InstitutionType,
    PlanSubscription,
    QuotaPeriod,
    QuotaResource,
    Tenant,
    TenantQuota,
    TenantSettings,
)


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


class TenantSettingsFactory(DjangoModelFactory):
    class Meta:
        model = TenantSettings

    tenant = factory.SubFactory(TenantFactory)


class PlanSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = PlanSubscription

    tenant = factory.SubFactory(TenantFactory)


class TenantQuotaFactory(DjangoModelFactory):
    class Meta:
        model = TenantQuota

    tenant = factory.SubFactory(TenantFactory)
    resource = QuotaResource.STUDENTS
    period = QuotaPeriod.MONTH
    period_start = factory.LazyFunction(lambda: datetime.date.today().replace(day=1))
    usage = 0
    soft_cap = 180
    hard_cap = 200


class FeatureFlagFactory(DjangoModelFactory):
    class Meta:
        model = FeatureFlag

    key = factory.Sequence(lambda n: f"flag-{n}")
    tenant = factory.SubFactory(TenantFactory)
    enabled = True
