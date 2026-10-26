from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep

import pytest
from django.db import connection, connections, transaction
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Requires PostgreSQL row locks"
    ),
]


@pytest.fixture
def team(django_user_model):
    owners = [
        django_user_model.objects.create_user(username=f"concurrent-owner-{i}")
        for i in range(2)
    ]
    organization = Organization.objects.create(
        name="Concurrent team", slug="concurrent-team"
    )
    memberships = [
        Membership.objects.create(organization=organization, user=user, role="owner")
        for user in owners
    ]
    return organization, owners, memberships


def member_url(membership):
    return reverse(
        "organizations:membership-detail",
        kwargs={
            "organization_id": membership.organization_id,
            "membership_id": membership.pk,
        },
    )


def request_in_separate_connection(token, method, url, data, backend_ids):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SET lock_timeout = '10s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend_ids.put(cursor.fetchone()[0])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = getattr(client, method)(url, data, format="json")
        return response.status_code, response.data
    finally:
        connections.close_all()


def run_waiting_requests(organization, requests, change_while_locked=None):
    """Prove every request waits for the same real PostgreSQL row lock."""
    backend_ids = Queue()
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=organization.pk)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                blocker_id = cursor.fetchone()[0]
            futures = [
                pool.submit(request_in_separate_connection, *request, backend_ids)
                for request in requests
            ]
            worker_ids = [backend_ids.get(timeout=10) for _ in requests]
            deadline = monotonic() + 8
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT worker.pid, pg_blocking_pids(worker.pid) "
                        "FROM unnest(%s::int[]) AS worker(pid)",
                        [worker_ids],
                    )
                    blockers = dict(cursor.fetchall())
                # PostgreSQL may queue a waiter behind another blocked waiter.
                blocked = {blocker_id}
                for _ in worker_ids:
                    blocked.update(
                        pid
                        for pid, parents in blockers.items()
                        if any(parent in blocked for parent in parents)
                    )
                if all(pid in blocked for pid in worker_ids):
                    break
                assert not any(future.done() for future in futures), (
                    "Mutation bypassed the organization lock"
                )
                assert monotonic() < deadline, (
                    "Requests did not reach the organization row lock"
                )
                sleep(0.01)
            if change_while_locked:
                change_while_locked()
        return [future.result(timeout=15) for future in futures]


@pytest.mark.parametrize(
    "methods", [("patch", "patch"), ("delete", "delete"), ("patch", "delete")]
)
def test_concurrent_owner_departures_keep_one_active_owner(team, methods):
    organization, owners, memberships = team
    requests = [
        (
            str(AccessToken.for_user(user)),
            method,
            member_url(membership),
            {"role": "member"},
        )
        for user, membership, method in zip(owners, memberships, methods, strict=True)
    ]

    results = run_waiting_requests(organization, requests)

    assert sorted(code for code, _ in results) in ([200, 400], [204, 400])
    assert (
        Membership.objects.filter(
            organization=organization, role="owner", user__is_active=True
        ).count()
        == 1
    )
    assert owners[0].__class__.objects.count() == 2
    assert Organization.objects.filter(pk=organization.pk).exists()


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
@pytest.mark.parametrize("revocation", ["demote", "remove"])
def test_mutation_rechecks_actor_access_after_waiting_for_lock(
    team, django_user_model, method, revocation
):
    organization, owners, memberships = team
    candidate = django_user_model.objects.create_user(username="concurrent-candidate")
    token = str(AccessToken.for_user(owners[0]))
    url = (
        reverse(
            "organizations:membership-list", kwargs={"organization_id": organization.pk}
        )
        if method == "post"
        else member_url(memberships[1])
    )
    payload = {"user_id": candidate.pk} if method == "post" else {"role": "member"}

    def revoke():
        actor = Membership.objects.filter(pk=memberships[0].pk)
        if revocation == "demote":
            actor.update(role="member")
        else:
            actor.delete()

    results = run_waiting_requests(
        organization, [(token, method, url, payload)], revoke
    )

    assert results[0][0] == (403 if revocation == "demote" else 404)
    memberships[1].refresh_from_db()
    assert memberships[1].role == Membership.Role.OWNER
    assert not Membership.objects.filter(user=candidate).exists()


def test_concurrent_duplicate_additions_create_exactly_one_membership(
    team, django_user_model
):
    organization, owners, _ = team
    candidate = django_user_model.objects.create_user(username="duplicate-candidate")
    url = reverse(
        "organizations:membership-list", kwargs={"organization_id": organization.pk}
    )
    requests = [
        (str(AccessToken.for_user(user)), "post", url, {"user_id": candidate.pk})
        for user in owners
    ]

    results = run_waiting_requests(organization, requests)

    assert sorted(code for code, _ in results) == [201, 400]
    assert (
        Membership.objects.filter(
            organization=organization, user=candidate, role="member"
        ).count()
        == 1
    )
