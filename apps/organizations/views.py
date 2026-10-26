from django.db.models import F
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated

from apps.organizations.models import Organization
from apps.organizations.pagination import OrganizationPagination
from apps.organizations.serializers import OrganizationSerializer


class OrganizationListCreateView(ListCreateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = OrganizationPagination

    def get_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .annotate(my_role=F("memberships__role"))
            .order_by("name", "id")
        )
