from django.urls import path

from apps.organizations.views import OrganizationListCreateView

app_name = "organizations"

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organization-list"),
]
