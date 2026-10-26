from django.urls import path

from apps.organizations.views import (
    MembershipDetailView,
    MembershipListCreateView,
    OrganizationDetailView,
    OrganizationListCreateView,
)

app_name = "organizations"

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organization-list"),
    path(
        "<int:organization_id>/",
        OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
    path(
        "<int:organization_id>/memberships/",
        MembershipListCreateView.as_view(),
        name="membership-list",
    ),
    path(
        "<int:organization_id>/memberships/<int:membership_id>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
]
