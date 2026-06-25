"""Study material folder CRUD and grouped student responses."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models.admin_extras import StudyMaterial, StudyMaterialFolder
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _post(env, body):
    return _client(env["admin"]).post(
        reverse("academics:admin-actions"), body, format="json",
    )


def _overview(env):
    resp = _client(env["admin"]).get(reverse("academics:admin-overview"))
    assert resp.status_code == 200, resp.content
    return _data(resp)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        phone="+919810000099", custom_login_id=None, must_change_password=False,
    )
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    return dict(tenant=tenant, branch=branch, admin=admin, batch=batch)


def test_create_folder_upload_and_list(env):
    resp = _post(env, {"action": "create_study_folder", "payload": {
        "classSectionId": str(env["batch"].id), "name": "Unit 1",
    }})
    assert resp.status_code == 201, resp.content
    folder_id = _data(resp)["id"]

    resp = _post(env, {"action": "upload_study_material", "payload": {
        "classSectionId": str(env["batch"].id),
        "folderId": folder_id,
        "fileName": "notes-ch3.pdf",
    }})
    assert resp.status_code == 201, resp.content

    overview = _overview(env)
    folders = overview["studyMaterialFolders"]
    assert any(f["id"] == folder_id and f["name"] == "Unit 1" and f["materialCount"] == 1 for f in folders)
    materials = overview["studyMaterials"]
    assert any(m["folderId"] == folder_id and m["folderName"] == "Unit 1" for m in materials)


def test_duplicate_folder_name_rejected(env):
    _post(env, {"action": "create_study_folder", "payload": {
        "classSectionId": str(env["batch"].id), "name": "Unit 1",
    }})
    resp = _post(env, {"action": "create_study_folder", "payload": {
        "classSectionId": str(env["batch"].id), "name": "unit 1",
    }})
    assert resp.status_code == 400, resp.content


def test_delete_non_empty_folder_rejected(env):
    folder = StudyMaterialFolder.objects.create(
        branch=env["branch"], batch=env["batch"], name="Exam prep",
    )
    StudyMaterial.objects.create(
        branch=env["branch"], batch=env["batch"], folder=folder, file_name="x.pdf",
    )
    resp = _post(env, {"action": "delete_study_folder", "folderId": str(folder.id)})
    assert resp.status_code == 400, resp.content


def test_delete_empty_folder(env):
    folder = StudyMaterialFolder.objects.create(
        branch=env["branch"], batch=env["batch"], name="Empty",
    )
    resp = _post(env, {"action": "delete_study_folder", "folderId": str(folder.id)})
    assert resp.status_code == 200, resp.content
    assert not StudyMaterialFolder.objects.filter(pk=folder.pk, is_active=True).exists()


def test_student_get_grouped_by_folder(env):
    folder = StudyMaterialFolder.objects.create(
        branch=env["branch"], batch=env["batch"], name="Unit 1",
    )
    StudyMaterial.objects.create(
        branch=env["branch"], batch=env["batch"], folder=folder, file_name="in-folder.pdf",
    )
    StudyMaterial.objects.create(
        branch=env["branch"], batch=env["batch"], file_name="general.pdf",
    )

    student = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id="STU-F1", must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student)
    StudentEnrollmentFactory(student_profile=profile, branch=env["branch"], batch=env["batch"])

    body = _data(_client(student).get(reverse("academics:student-materials")))
    assert len(body["folders"]) == 1
    assert body["folders"][0]["name"] == "Unit 1"
    assert body["folders"][0]["materials"][0]["fileName"] == "in-folder.pdf"
    assert len(body["general"]) == 1
    assert body["general"][0]["fileName"] == "general.pdf"
