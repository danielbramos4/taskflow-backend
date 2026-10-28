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


def update_task_in_separate_connection(token, url, backend_ids, payload):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SET lock_timeout = '10s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend_ids.put(cursor.fetchone()[0])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client.patch(url, payload, format="json").status_code
    finally:
        connections.close_all()


@pytest.mark.parametrize("revocation", ["demote", "remove"])
@pytest.mark.parametrize(
    "payload,initial_status",
    [
        ({"title": "Pending edit"}, "todo"),
        ({"status": "in_progress"}, "todo"),
        ({"status": "done"}, "in_progress"),
        ({"status": "todo"}, "done"),
    ],
)
def test_edit_rechecks_access_after_organization_lock(
    organization, project, owner, outsider, revocation, payload, initial_status
):
    task = Task.objects.create(
        project=project,
        title="Original",
        description="Scope",
        created_by=owner,
        status=initial_status,
    )
    original_updated_at = task.updated_at
    url = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization.pk,
            "project_id": project.pk,
            "task_id": task.pk,
        },
    )
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    actor = Membership.objects.get(organization=organization, user=owner)
    token = str(AccessToken.for_user(owner))
    backend_ids = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=organization.pk)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                blocker_id = cursor.fetchone()[0]
            future = pool.submit(
                update_task_in_separate_connection, token, url, backend_ids, payload
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
                assert not future.done(), "Write bypassed the organization row lock"
                assert monotonic() < deadline, "Write did not reach the row lock"
                sleep(0.01)
            if revocation == "demote":
                Membership.objects.filter(pk=actor.pk).update(role="member")
            else:
                actor.delete()
        assert future.result(timeout=15) == (403 if revocation == "demote" else 404)
    task.refresh_from_db()
    assert task.title == "Original" and task.description == "Scope"
    assert task.status == initial_status and task.created_by_id == owner.pk
    assert task.project_id == project.pk and task.updated_at == original_updated_at
    assert Task.objects.count() == 1
    assert Membership.objects.filter(
        organization=organization, user=outsider, role="owner"
    ).exists()


@pytest.mark.parametrize(
    "payload", [{"title": "Rejected at commit"}, {"status": "done"}]
)
def test_deferred_edit_failure_rolls_back_at_commit(
    api_client, project, owner, organization, payload
):
    task = Task.objects.create(
        project=project, title="Original", description="Scope", created_by=owner
    )
    original_updated_at = task.updated_at
    url = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization.pk,
            "project_id": project.pk,
            "task_id": task.pk,
        },
    )
    save_task = Task.save

    def save_with_missing_author(instance, *args, **kwargs):
        instance.created_by_id = -1
        kwargs["update_fields"] = [*kwargs["update_fields"], "created_by"]
        return save_task(instance, *args, **kwargs)

    with patch("apps.tasks.serializers.Task.save", new=save_with_missing_author):
        response = api_client.patch(url, payload, format="json")
    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível atualizar a tarefa."
    task.refresh_from_db()
    assert task.title == "Original" and task.description == "Scope"
    assert task.created_by_id == owner.pk and task.project_id == project.pk
    assert task.status == "todo" and task.updated_at == original_updated_at
    assert Task.objects.count() == 1
