import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.tests.factories import TenantFactory
from apps.organizations.models import TenantSettings


@pytest.fixture
def api_client():
    return APIClient()


def test_tenant_config_view_success(api_client):
    tenant = TenantFactory(subdomain="horizon-college", name="Horizon College")
    TenantSettings.objects.create(
        tenant=tenant,
        student_id_label="Admission Number",
        faculty_id_label="Staff Code",
    )

    url = reverse("organizations:tenant-config")
    response = api_client.get(url, {"subdomain": "horizon-college"})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["tenant_id"] == str(tenant.id)
    assert response.data["institution_name"] == "Horizon College"
    assert response.data["subdomain"] == "horizon-college"
    assert response.data["student_id_label"] == "Admission Number"
    assert response.data["faculty_id_label"] == "Staff Code"


def test_tenant_config_view_missing_subdomain(api_client):
    url = reverse("organizations:tenant-config")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "subdomain query parameter is required" in response.data["error"]


def test_tenant_config_view_not_found(api_client):
    url = reverse("organizations:tenant-config")
    response = api_client.get(url, {"subdomain": "non-existent"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found or inactive" in response.data["error"]
