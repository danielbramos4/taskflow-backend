from django.conf import settings
from django.db import models


class Project(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="projects"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(max_length=5000, blank=True, default="")
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects"
        ordering = ["name", "id"]

    def __str__(self):
        return self.name
