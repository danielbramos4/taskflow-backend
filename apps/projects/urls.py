from django.urls import path

from apps.projects.views import ProjectListCreateView

app_name = "projects"

urlpatterns = [path("", ProjectListCreateView.as_view(), name="project-list")]
