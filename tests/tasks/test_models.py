import pytest
from django.db.models.deletion import ProtectedError

from apps.organizations.models import Membership
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


def test_task_defaults_and_relations(project, owner):
    task = Task.objects.create(project=project, title="First task", created_by=owner)
    assert task.description == ""
    assert task.status == Task.Status.TODO
    assert task.updated_at >= task.created_at
    assert list(project.tasks.all()) == [task]
    assert list(owner.created_tasks.all()) == [task]
    assert str(task) == "First task"


def test_project_deletion_is_protected(project):
    task = Task.objects.create(project=project, title="Preserved")
    with pytest.raises(ProtectedError):
        project.delete()
    assert Task.objects.filter(pk=task.pk, project=project).exists()


def test_author_deletion_preserves_task(project, owner, outsider):
    Membership.objects.create(
        organization=project.organization, user=outsider, role="owner"
    )
    task = Task.objects.create(project=project, title="Preserved", created_by=owner)
    owner.delete()
    task.refresh_from_db()
    assert task.created_by_id is None
    assert task.project_id == project.pk and task.title == "Preserved"
    assert Membership.objects.filter(user=outsider, role="owner").exists()


def test_duplicate_titles_are_allowed_and_order_is_stable(project):
    first, second = [
        Task.objects.create(project=project, title="Repeated") for _ in range(2)
    ]
    Task.objects.filter(pk=second.pk).update(created_at=first.created_at)
    assert list(Task.objects.values_list("id", flat=True)) == [first.pk, second.pk]
