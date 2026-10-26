from django.db import transaction
from rest_framework.generics import ListCreateAPIView

from apps.organizations.views import OrganizationAccessMixin
from apps.projects.models import Project
from apps.projects.pagination import ProjectPagination
from apps.projects.serializers import ProjectSerializer


class ProjectListCreateView(OrganizationAccessMixin, ListCreateAPIView):
    serializer_class = ProjectSerializer
    pagination_class = ProjectPagination

    def get_queryset(self):
        return Project.objects.filter(organization=self.organization).order_by(
            "name", "id"
        )

    def list(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            self.organization = self.get_organization(for_update=True)
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user)
