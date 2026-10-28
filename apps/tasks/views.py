from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException
from rest_framework.generics import GenericAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.response import Response

from apps.organizations.views import OrganizationAccessMixin
from apps.projects.models import Project
from apps.tasks.models import Task
from apps.tasks.pagination import TaskPagination
from apps.tasks.serializers import TaskSerializer, TaskUpdateSerializer


class TaskAccessMixin(OrganizationAccessMixin):
    serializer_class = TaskSerializer

    def get_project(self):
        return get_object_or_404(
            Project.objects.filter(organization=self.organization),
            pk=self.kwargs["project_id"],
        )

    def get_queryset(self):
        return Task.objects.filter(project=self.project).order_by("created_at", "id")

    def get_object(self):
        # Both parents are checked before task lookup.
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["task_id"])


class TaskListCreateView(TaskAccessMixin, ListCreateAPIView):
    pagination_class = TaskPagination

    def list(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        self.project = self.get_project()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                self.organization = self.get_organization(for_update=True)
                self.project = self.get_project()
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            raise APIException("Não foi possível criar a tarefa.") from None

    def perform_create(self, serializer):
        serializer.save(project=self.project, created_by=self.request.user)


class TaskDetailView(TaskAccessMixin, GenericAPIView):
    serializer_class = TaskUpdateSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request, *args, **kwargs):
        self.organization = self.get_organization()
        self.project = self.get_project()
        return Response(self.get_serializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                self.organization = self.get_organization(for_update=True)
                self.project = self.get_project()
                serializer = self.get_serializer(
                    self.get_object(), data=request.data, partial=True
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return Response(serializer.data)
        except IntegrityError:
            raise APIException("Não foi possível atualizar a tarefa.") from None
