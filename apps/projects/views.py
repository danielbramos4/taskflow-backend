from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException
from rest_framework.generics import GenericAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.response import Response

from apps.organizations.views import OrganizationAccessMixin
from apps.projects.models import Project
from apps.projects.pagination import ProjectPagination
from apps.projects.serializers import ProjectSerializer


class ProjectAccessMixin(OrganizationAccessMixin):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(organization=self.organization).order_by(
            "name", "id"
        )

    def get_object(self):
        # Parent access is checked before looking up a project inside that parent.
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["project_id"])


class ProjectListCreateView(ProjectAccessMixin, ListCreateAPIView):
    pagination_class = ProjectPagination

    def list(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                self.organization = self.get_organization(for_update=True)
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            # Deferred foreign-key checks can fail when the transaction commits.
            raise APIException("Não foi possível criar o projeto.") from None

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user)


class ProjectDetailView(ProjectAccessMixin, GenericAPIView):
    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        return Response(self.get_serializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                self.organization = self.get_organization(for_update=True)
                serializer = self.get_serializer(
                    self.get_object(), data=request.data, partial=True
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return Response(serializer.data)
        except IntegrityError:
            raise APIException("Não foi possível atualizar o projeto.") from None
