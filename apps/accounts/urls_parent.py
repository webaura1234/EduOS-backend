"""Parent portal routes under /api/v1/parent/."""

from django.urls import path

from apps.accounts.views.parent_portal import ParentChildrenView, ParentPortalAccessView

app_name = "parent"

urlpatterns = [
    path("children/", ParentChildrenView.as_view(), name="children"),
    path("portal-access/", ParentPortalAccessView.as_view(), name="portal-access"),
]
