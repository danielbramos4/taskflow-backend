from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "A fazer"
        IN_PROGRESS = "in_progress", "Em andamento"
        DONE = "done", "Concluída"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="tasks"
    )
    title = models.CharField(max_length=150)
    description = models.TextField(max_length=5000, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasks"
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.title
