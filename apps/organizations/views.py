from django.db import transaction
from django.db.models import F
from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
    get_object_or_404,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.organizations.models import Membership, Organization
from apps.organizations.pagination import MembershipPagination, OrganizationPagination
from apps.organizations.permissions import IsOrganizationOwnerOrReadOnly
from apps.organizations.serializers import MembershipSerializer, OrganizationSerializer
from apps.organizations.services import delete_membership


class OrganizationAccessMixin:
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationOwnerOrReadOnly]

    def get_organization_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .annotate(my_role=F("memberships__role"))
            .order_by("name", "id")
        )

    def get_queryset(self):
        return self.get_organization_queryset()


class OrganizationListCreateView(OrganizationAccessMixin, ListCreateAPIView):
    pagination_class = OrganizationPagination


class OrganizationDetailView(OrganizationAccessMixin, RetrieveUpdateAPIView):
    lookup_url_kwarg = "organization_id"
    http_method_names = ["get", "patch", "head", "options"]


class MembershipAccessMixin(OrganizationAccessMixin):
    serializer_class = MembershipSerializer

    def get_organization(self, *, for_update=False):
        organization_id = self.kwargs["organization_id"]
        if for_update:
            # Lock first, then read membership/role in a fresh query after any wait.
            get_object_or_404(
                Organization.objects.select_for_update(), pk=organization_id
            )
        organization = get_object_or_404(
            self.get_organization_queryset(), pk=organization_id
        )
        self.check_object_permissions(self.request, organization)
        return organization

    def get_queryset(self):
        return (
            Membership.objects.filter(organization=self.organization)
            .select_related("user")
            .order_by("created_at", "id")
        )

    def get_object(self):
        # Access is checked on the parent organization before the scoped lookup.
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["membership_id"])


class MembershipListCreateView(MembershipAccessMixin, ListCreateAPIView):
    pagination_class = MembershipPagination

    def list(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            self.organization = self.get_organization(for_update=True)
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(organization=self.organization)


class MembershipDetailView(MembershipAccessMixin, GenericAPIView):
    http_method_names = ["patch", "delete", "options"]

    def patch(self, request, *args, **kwargs):
        with transaction.atomic():
            self.organization = self.get_organization(for_update=True)
            membership = self.get_object()
            serializer = self.get_serializer(
                membership, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        with transaction.atomic():
            self.organization = self.get_organization(for_update=True)
            delete_membership(self.get_object())
            return Response(status=status.HTTP_204_NO_CONTENT)
