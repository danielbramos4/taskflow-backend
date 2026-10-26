from django.db.models import F
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated

from apps.organizations.models import Organization
from apps.organizations.pagination import OrganizationPagination
from apps.organizations.permissions import IsOrganizationOwnerOrReadOnly
from apps.organizations.serializers import OrganizationSerializer


class OrganizationAccessMixin:
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationOwnerOrReadOnly]

    def get_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .annotate(my_role=F("memberships__role"))
            .order_by("name", "id")
        )


class OrganizationListCreateView(OrganizationAccessMixin, ListCreateAPIView):
    pagination_class = OrganizationPagination


class OrganizationDetailView(OrganizationAccessMixin, RetrieveUpdateAPIView):
    lookup_url_kwarg = "organization_id"
    http_method_names = ["get", "patch", "head", "options"]
