import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.organizations.tests.factories import TenantFactory, BranchFactory
from apps.accounts.models.user import Role


@pytest.fixture
def api_client():
    """Rest framework test API client."""
    return APIClient()


@pytest.fixture
def tenant():
    """A standard tenant institution."""
    return TenantFactory()


@pytest.fixture
def branch(tenant):
    """A branch under the standard tenant."""
    return BranchFactory(tenant=tenant)


@pytest.fixture
def student_user(tenant, branch):
    """A standard student user with must_change_password=True by default."""
    return UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-001",
        must_change_password=True,
    )


@pytest.fixture
def faculty_user(tenant, branch):
    """A faculty user with must_change_password=True by default."""
    return UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-001",
        must_change_password=True,
    )


@pytest.fixture
def admin_user(tenant, branch):
    """An admin user with must_change_password=False for easier authenticated requests."""
    return UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919876543210",
        must_change_password=False,
    )


@pytest.fixture
def super_admin_user(tenant, branch):
    """A super admin user with must_change_password=False."""
    return UserFactory(
        role=Role.SUPER_ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919876543211",
        must_change_password=False,
    )


@pytest.fixture
def auth_client(api_client, student_user):
    """An API client authenticated as the student_user (who has must_change_password=True)."""
    from apps.accounts.tokens import generate_access_token
    token = generate_access_token(student_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def admin_auth_client(api_client, admin_user):
    """An API client authenticated as the admin_user."""
    from apps.accounts.tokens import generate_access_token
    token = generate_access_token(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client
