from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from unittest.mock import patch

import pytest
from django.db import connection, connections, transaction
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization
from apps.tasks.models import Task

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Requires PostgreSQL row locks"
    ),
]


def assign_in_worker(token, path, method, payload, backend_ids):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SET lock_timeout = '10s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend_ids.put(cursor.fetchone()[0])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return getattr(client, method)(path, payload, format="json").status_code
    finally:
        connections.close_all()


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize(
    "change,expected",
    [("demote_actor", 403), ("remove_actor", 404), ("remove_target", 400)],
)
def test_assignment_rechecks_actor_and_target_after_lock(
    owner, outsider, organization, project, membership, url, method, change, expected
):
    task = Task.objects.create(project=project, title="Original", created_by=owner)
    original_updated_at = task.updated_at
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    actor = Membership.objects.get(organization=organization, user=owner)
    path = (
        url
        if method == "post"
        else reverse(
            "projects:tasks:task-detail",
            kwargs={
                "organization_id": organization.pk,
                "project_id": project.pk,
                "task_id": task.pk,
            },
        )
    )
    token = str(AccessToken.for_user(owner))
    payload = {"title": "Pending", "assignee_membership_id": membership.pk}
    backend_ids = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=organization.pk)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                blocker_id = cursor.fetchone()[0]
            future = pool.submit(
                assign_in_worker, token, path, method, payload, backend_ids
            )
            worker_id = backend_ids.get(timeout=10)
            deadline = monotonic() + 8
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT %s = ANY(pg_blocking_pids(%s))", [blocker_id, worker_id]
                    )
                    waiting = cursor.fetchone()[0]
                if waiting:
                    break
                assert not future.done(), "Assignment bypassed the organization lock"
                assert monotonic() < deadline, "Assignment did not reach the lock"
                sleep(0.01)
            if change == "demote_actor":
                Membership.objects.filter(pk=actor.pk).update(role="member")
            elif change == "remove_actor":
                actor.delete()
            else:
                membership.delete()
        assert future.result(timeout=15) == expected
    task.refresh_from_db()
    assert task.title == "Original" and task.assignee_id is None
    assert task.created_by_id == owner.pk and task.updated_at == original_updated_at
    assert Task.objects.count() == 1


@pytest.mark.parametrize("method", ["post", "patch"])
def test_deferred_assignment_foreign_key_failure_rolls_back(
    api_client, organization, project, owner, membership, url, method
):
    task = Task.objects.create(project=project, title="Original", created_by=owner)
    original_updated_at = task.updated_at
    path = (
        url
        if method == "post"
        else reverse(
            "projects:tasks:task-detail",
            kwargs={
                "organization_id": organization.pk,
                "project_id": project.pk,
                "task_id": task.pk,
            },
        )
    )
    save_task = Task.save

    def save_with_missing_assignee(instance, *args, **kwargs):
        instance.assignee_id = -1
        if kwargs.get("update_fields"):
            kwargs["update_fields"] = [*kwargs["update_fields"], "assignee"]
        return save_task(instance, *args, **kwargs)

    with patch("apps.tasks.serializers.Task.save", new=save_with_missing_assignee):
        response = getattr(api_client, method)(
            path,
            {"title": "Rejected", "assignee_membership_id": membership.pk},
            format="json",
        )
    assert response.status_code == 500
    assert str(response.data["detail"]) == (
        "Não foi possível criar a tarefa."
        if method == "post"
        else "Não foi possível atualizar a tarefa."
    )
    task.refresh_from_db()
    assert task.title == "Original" and task.assignee_id is None
    assert task.updated_at == original_updated_at and Task.objects.count() == 1
