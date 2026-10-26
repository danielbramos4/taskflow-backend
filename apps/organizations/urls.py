from django.urls import path

from apps.organizations.views import OrganizationDetailView, OrganizationListCreateView

app_name = "organizations"

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organization-list"),
    path(
        "<int:organization_id>/",
        OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
]
