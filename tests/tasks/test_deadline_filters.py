from datetime import date

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def task(project):
    return Task.objects.create(project=project, title="Existing")


def task_detail(organization, project, task_id):
    return reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization.pk,
            "project_id": project.pk,
            "task_id": task_id,
        },
    )


@pytest.fixture
def detail_url(organization, project, task):
    return task_detail(organization, project, task.pk)


@pytest.mark.parametrize("value", [None, "2000-02-29", "2099-12-31"])
def test_create_with_optional_date(api_client, url, value):
    response = api_client.post(url, {"title": "New", "due_date": value}, format="json")
    assert response.status_code == 201
    assert response.data["due_date"] == value and response.data["status"] == "todo"
    task = Task.objects.get(pk=response.data["id"])
    assert task.due_date == (date.fromisoformat(value) if value else None)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026-2-01",
        "2026-02-30",
        "20261112",
        "2026-W46-4",
        "2026-11-12T00:00:00Z",
        " 2026-11-12",
        20261112,
        True,
        [],
        {},
    ],
)
@pytest.mark.parametrize("operation", ["create", "update"])
def test_invalid_dates_reject_entire_write(
    api_client, task, detail_url, url, value, operation
):
    payload = {"title": "Attempt", "due_date": value}
    if operation == "create":
        response = api_client.post(url, payload, format="json")
    else:
        response = api_client.patch(detail_url, payload, format="json")
    assert response.status_code == 400 and "due_date" in response.data
    assert Task.objects.count() == 1
    task.refresh_from_db()
    assert task.title == "Existing" and task.due_date is None


def test_update_clear_and_omit_deadline_preserve_other_fields(
    api_client, detail_url, membership, task
):
    task.assignee = membership
    task.status = "in_progress"
    task.save(update_fields=["assignee", "status"])
    for value in ("2099-11-12", "2000-11-12"):
        response = api_client.patch(detail_url, {"due_date": value}, format="json")
        assert response.status_code == 200 and response.data["due_date"] == value
        assert response.data["status"] == "in_progress"
        assert response.data["assignee_membership_id"] == membership.pk
    assert (
        api_client.patch(detail_url, {"title": "Renamed"}, format="json").data[
            "due_date"
        ]
        == "2000-11-12"
    )
    response = api_client.patch(detail_url, {"due_date": None}, format="json")
    assert response.status_code == 200 and response.data["due_date"] is None
    task.refresh_from_db()
    assert task.due_date is None and task.title == "Renamed"
    assert task.status == "in_progress" and task.assignee_id == membership.pk


def test_invalid_assignee_rejects_valid_date(api_client, detail_url, task):
    response = api_client.patch(
        detail_url,
        {"due_date": "2026-11-12", "assignee_membership_id": -1},
        format="json",
    )
    assert response.status_code == 400
    task.refresh_from_db()
    assert task.due_date is None


@pytest.mark.parametrize(
    "query",
    [
        "due_from=bad",
        "due_to=",
        "due_from=2026-11-13&due_to=2026-11-12",
        "due_from=2026-11-12&due_from=2026-11-13",
        "assignee_membership_id=0",
        "assignee_membership_id=9223372036854775808",
        "assignee_membership_id=unassigned&assignee_membership_id=1",
    ],
)
def test_invalid_filters_return_400_only_after_authorization(
    api_client, client_for, outsider, url, query
):
    path = f"{url}?{query}"
    assert APIClient().get(path).status_code == 401
    assert client_for(outsider).get(path).status_code == 404
    assert api_client.get(path).status_code == 400


def test_filters_combine_inclusive_dates_and_assignee_with_project_scope(
    api_client, project, organization, membership, outsider, url
):
    wanted = Task.objects.create(
        project=project, title="Match", due_date="2026-11-12", assignee=membership
    )
    Task.objects.create(
        project=project, title="Before", due_date="2026-11-11", assignee=membership
    )
    Task.objects.create(
        project=project, title="After", due_date="2026-11-13", assignee=membership
    )
    Task.objects.create(project=project, title="No deadline", assignee=membership)
    unassigned = Task.objects.create(
        project=project, title="No assignee", due_date="2026-11-12"
    )
    sibling = Project.objects.create(organization=organization, name="Sibling")
    Task.objects.create(
        project=sibling, title="Sibling", due_date="2026-11-12", assignee=membership
    )
    other = Organization.objects.create(name="Other", slug="deadline-other")
    foreign_member = Membership.objects.create(
        organization=other, user=outsider, role="owner"
    )
    foreign_project = Project.objects.create(organization=other, name="Foreign")
    Task.objects.create(
        project=foreign_project,
        title="Foreign",
        due_date="2026-11-12",
        assignee=foreign_member,
    )
    bounds = {"due_from": "2026-11-12", "due_to": "2026-11-12"}
    for value, ids in [
        (membership.pk, [wanted.pk]),
        ("unassigned", [unassigned.pk]),
        (foreign_member.pk, []),
    ]:
        response = api_client.get(url, {**bounds, "assignee_membership_id": value})
        assert response.status_code == 200
        assert [item["id"] for item in response.data["results"]] == ids
    assert api_client.get(url, {"due_from": "2026-11-12"}).data["count"] == 3
    assert api_client.get(url, {"due_to": "2026-11-12"}).data["count"] == 3


def test_filters_keep_order_and_pagination(api_client, project, url):
    ids = [
        Task.objects.create(
            project=project, title=f"Match {i}", due_date="2026-11-12"
        ).pk
        for i in range(21)
    ]
    Task.objects.create(project=project, title="Without date")
    first = api_client.get(url, {"due_from": "2026-11-12"}).data
    assert first["count"] == 21
    assert [item["id"] for item in first["results"]] == ids[:20]
    second = api_client.get(first["next"]).data
    assert [item["id"] for item in second["results"]] == ids[20:]
    assert second["next"] is None


def test_final_backend_flow_with_real_jwt(
    owner, member, membership, organization, project, url
):
    def login(user):
        password = "local-integration-test-password"
        user.set_password(password)
        user.save(update_fields=["password"])
        client = APIClient()
        response = client.post(
            "/api/v1/auth/token/",
            {"username": user.username, "password": password},
            format="json",
        )
        assert response.status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    manager, assignee = login(owner), login(member)
    created = manager.post(
        url,
        {
            "title": "Review",
            "assignee_membership_id": membership.pk,
            "due_date": "2026-11-12",
        },
        format="json",
    )
    assert created.status_code == 201
    path = task_detail(organization, project, created.data["id"])
    response = assignee.get(
        url, {"assignee_membership_id": membership.pk, "due_to": "2026-11-12"}
    )
    assert response.status_code == 200 and response.data["count"] == 1
    assert response.data["results"][0]["id"] == created.data["id"]
    assert assignee.patch(path, {"due_date": None}, format="json").status_code == 403
    done = manager.patch(path, {"status": "done"}, format="json")
    assert done.status_code == 200 and done.data["due_date"] == "2026-11-12"
    link = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    assert manager.delete(link).status_code == 204
    assert assignee.get(path).status_code == 404
    members = reverse(
        "organizations:membership-list", kwargs={"organization_id": organization.pk}
    )
    assert (
        manager.post(members, {"user_id": member.pk}, format="json").status_code == 201
    )
    read = assignee.get(path)
    assert read.status_code == 200 and read.data["assignee_membership_id"] is None
    assert read.data["due_date"] == "2026-11-12" and read.data["status"] == "done"
    assert (
        manager.get(
            url, {"assignee_membership_id": "unassigned", "due_from": "2026-11-12"}
        ).data["count"]
        == 1
    )
