from django.urls import include, path

from apps.projects.views import ProjectDetailView, ProjectListCreateView

app_name = "projects"

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list"),
    path("<int:project_id>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:project_id>/tasks/", include("apps.tasks.urls")),
]
