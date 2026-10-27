from django.urls import path

from apps.tasks.views import TaskDetailView, TaskListCreateView

app_name = "tasks"

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list"),
    path("<int:task_id>/", TaskDetailView.as_view(), name="task-detail"),
]
