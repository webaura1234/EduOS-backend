import datetime, pytest
from django.urls import reverse
from rest_framework.test import APIClient
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory
pytestmark = pytest.mark.django_db
def test_probe():
    t=TenantFactory(institution_type="school"); b=BranchFactory(tenant=t)
    a=UserFactory(role=Role.ADMIN,tenant=t,branch=b,phone="+919810000001",custom_login_id=None,must_change_password=False)
    c=APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(a)}")
    r=c.post(reverse("hr:payroll-run"),{"periodMonth":"2024-09-01"},format="json")
    print("BODY:", r.status_code, r.content.decode())
