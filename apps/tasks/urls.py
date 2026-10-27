from django.urls import path

from apps.tasks.views import TaskListCreateView

app_name = "tasks"

urlpatterns = [path("", TaskListCreateView.as_view(), name="task-list")]
