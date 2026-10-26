from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from unittest.mock import patch

import pytest
from django.db import connection, connections, transaction
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Requires PostgreSQL row locks"
    ),
]


def create_project_in_separate_connection(token, url, backend_ids):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SET lock_timeout = '10s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend_ids.put(cursor.fetchone()[0])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client.post(url, {"name": "Pending project"}, format="json").status_code
    finally:
        connections.close_all()


@pytest.mark.parametrize("revocation", ["demote", "remove"])
def test_creation_rechecks_access_after_waiting_for_organization_lock(
    organization, owner, outsider, url, revocation
):
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
                create_project_in_separate_connection, token, url, backend_ids
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
                assert not future.done(), "Creation bypassed the organization row lock"
                assert monotonic() < deadline, "Creation did not reach the row lock"
                sleep(0.01)
            if revocation == "demote":
                Membership.objects.filter(pk=actor.pk).update(role="member")
            else:
                actor.delete()

        assert future.result(timeout=15) == (403 if revocation == "demote" else 404)
    assert not Project.objects.exists()
    assert Membership.objects.filter(
        organization=organization, user=outsider, role="owner"
    ).exists()


def test_deferred_foreign_key_failure_returns_generic_error_and_rolls_back(
    api_client, url
):
    create_project = Project.objects.create

    def create_with_missing_author(**kwargs):
        kwargs.pop("created_by")
        return create_project(**kwargs, created_by_id=-1)

    with patch(
        "apps.projects.serializers.Project.objects.create",
        side_effect=create_with_missing_author,
    ):
        response = api_client.post(url, {"name": "Rejected at commit"}, format="json")

    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível criar o projeto."
    assert not Project.objects.exists()
