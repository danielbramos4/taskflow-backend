from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_collection_requires_valid_jwt(url, method, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = getattr(client, method)(url, {"title": "Attempt"}, format="json")
    assert response.status_code == 401
    assert not Task.objects.exists()


@pytest.mark.parametrize("description", [None, "Task description"])
def test_owner_creates_and_lists_task_with_server_identity(
    api_client, owner, project, url, description
):
    payload = {"title": "  First task  "}
    if description is not None:
        payload["description"] = description
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert set(response.data) == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "assignee_membership_id",
        "assignee_user_id",
        "created_by_id",
        "created_at",
        "updated_at",
    }
    task = Task.objects.get(pk=response.data["id"])
    assert task.project_id == project.pk and task.created_by_id == owner.pk
    assert task.title == "First task" and task.description == (description or "")
    assert response.data["status"] == task.status == "todo"
    assert response.data["created_by_id"] == owner.pk
    listing = api_client.get(url)
    assert listing.status_code == 200 and listing.data["results"] == [response.data]


def test_member_reads_but_cannot_create(
    api_client, membership, member, client_for, url
):
    created = api_client.post(url, {"title": "Visible"}, format="json")
    client = client_for(member)
    listing = client.get(url)
    assert listing.status_code == 200 and listing.data["results"] == [created.data]
    assert client.post(url, {"title": "Forbidden"}, format="json").status_code == 403
    assert Task.objects.count() == 1


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_and_unlinked_superuser_get_404(
    client_for, outsider, url, method, superuser
):
    outsider.is_staff = outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    response = getattr(client_for(outsider), method)(
        url, {"title": "Forbidden"}, format="json"
    )
    assert response.status_code == 404
    assert not Task.objects.exists()


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "title"),
        ({"title": ""}, "title"),
        ({"title": "  "}, "title"),
        ({"title": None}, "title"),
        ({"title": "x" * 151}, "title"),
        ({"title": "Valid", "description": None}, "description"),
        ({"title": "Valid", "description": "x" * 5001}, "description"),
    ],
)
def test_invalid_fields_do_not_create_task(api_client, url, payload, field):
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 400 and field in response.data
    assert not Task.objects.exists()


def test_field_limits(api_client, url):
    response = api_client.post(
        url, {"title": "x" * 150, "description": "x" * 5000}, format="json"
    )
    assert response.status_code == 201
    assert (
        len(response.data["title"]) == 150 and len(response.data["description"]) == 5000
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 999),
        ("project_id", 999),
        ("project", 999),
        ("organization_id", 999),
        ("organization", 999),
        ("created_by_id", 999),
        ("created_by", 999),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("updated_at", "2026-01-01T00:00:00Z"),
        ("status", "todo"),
        ("status", "done"),
        ("assignee_id", 999),
        ("unexpected", "value"),
    ],
)
def test_controlled_and_unknown_fields_are_rejected(api_client, url, field, value):
    response = api_client.post(url, {"title": "Rejected", field: value}, format="json")
    assert response.status_code == 400 and field in response.data
    assert not Task.objects.exists()


@pytest.mark.parametrize("payload", [[], "text", 12, None])
def test_non_object_payload_returns_400(api_client, url, payload):
    # APIClient replaces falsey data with an empty object; send raw JSON instead.
    import json

    response = api_client.generic(
        "POST", url, json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert not Task.objects.exists()


@pytest.mark.parametrize("method", ["get", "post"])
def test_missing_or_wrong_parent_cannot_expose_project(
    api_client, organization, owner, project, url, method
):
    other = Organization.objects.create(name="Other", slug="other-task-team")
    Membership.objects.create(organization=other, user=owner, role="owner")
    external = Project.objects.create(organization=other, name="Other project")
    foreign_task = Task.objects.create(project=external, title="Private")
    for organization_id, project_id in [
        (organization.pk, external.pk),
        (other.pk, project.pk),
        (organization.pk, project.pk + external.pk + 999),
        (999999, project.pk),
    ]:
        path = reverse(
            "projects:tasks:task-list",
            kwargs={"organization_id": organization_id, "project_id": project_id},
        )
        assert (
            getattr(api_client, method)(
                path, {"title": "Forbidden"}, format="json"
            ).status_code
            == 404
        )
    assert list(Task.objects.all()) == [foreign_task]
    assert api_client.get(url).data["results"] == []


def test_list_is_paginated_and_ignores_foreign_query_ids(
    api_client, project, organization, url
):
    tasks = [
        Task.objects.create(project=project, title=f"Task {index}")
        for index in range(23)
    ]
    Task.objects.filter(project=project).update(created_at=tasks[0].created_at)
    other = Project.objects.create(organization=organization, name="Other project")
    Task.objects.create(project=other, title="Not in collection")
    first = api_client.get(
        url, {"project_id": other.pk, "organization_id": 999, "page_size": 100}
    )
    assert first.status_code == 200 and first.data["count"] == 23
    assert [row["id"] for row in first.data["results"]] == [
        task.pk for task in tasks[:20]
    ]
    assert first.data["next"] and first.data["previous"] is None
    second = api_client.get(url, {"page": 2})
    assert [row["id"] for row in second.data["results"]] == [
        task.pk for task in tasks[20:]
    ]
    assert second.data["next"] is None and second.data["previous"]
    assert api_client.get(url, {"page": 3}).status_code == 404


def test_roles_are_scoped_to_each_organization(api_client, owner, url):
    other = Organization.objects.create(name="Other", slug="other-role-team")
    Membership.objects.create(organization=other, user=owner, role="member")
    other_project = Project.objects.create(organization=other, name="Other")
    path = reverse(
        "projects:tasks:task-list",
        kwargs={"organization_id": other.pk, "project_id": other_project.pk},
    )
    assert api_client.post(url, {"title": "Owned"}, format="json").status_code == 201
    assert api_client.get(path).status_code == 200
    assert (
        api_client.post(path, {"title": "Forbidden"}, format="json").status_code == 403
    )
    assert Task.objects.count() == 1


def test_promotion_demotion_and_removal_take_effect_with_same_jwt(
    api_client, owner, organization, project, url
):
    created = api_client.post(url, {"title": "Preserved"}, format="json")
    assert created.status_code == 201
    membership = Membership.objects.get(organization=organization, user=owner)
    membership.role = "member"
    membership.save(update_fields=["role"])
    assert api_client.get(url).status_code == 200
    assert (
        api_client.post(url, {"title": "Forbidden"}, format="json").status_code == 403
    )
    membership.role = "owner"
    membership.save(update_fields=["role"])
    assert api_client.post(url, {"title": "Allowed"}, format="json").status_code == 201
    membership.delete()
    assert api_client.get(url).status_code == 404
    assert (
        api_client.post(url, {"title": "Forbidden"}, format="json").status_code == 404
    )
    assert Task.objects.count() == 2 and Project.objects.filter(pk=project.pk).exists()
    assert Task.objects.get(pk=created.data["id"]).created_by_id == owner.pk


def test_archived_project_remains_accessible(
    api_client, membership, member, client_for, project, url
):
    project.is_archived = True
    project.save(update_fields=["is_archived"])
    response = api_client.post(url, {"title": "Archive task"}, format="json")
    assert response.status_code == 201
    assert client_for(member).get(url).data["results"] == [response.data]
    assert (
        client_for(member).post(url, {"title": "Forbidden"}, format="json").status_code
        == 403
    )


def test_null_author_is_serialized_without_exposing_user_data(api_client, project, url):
    task = Task.objects.create(project=project, title="No author")
    row = api_client.get(url).data["results"][0]
    assert row["id"] == task.pk and row["created_by_id"] is None
    assert set(row) == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "assignee_membership_id",
        "assignee_user_id",
        "created_by_id",
        "created_at",
        "updated_at",
    }


def test_integrity_failure_returns_generic_error(api_client, url):
    with patch(
        "apps.tasks.serializers.Task.objects.create",
        side_effect=IntegrityError("private database detail"),
    ):
        response = api_client.post(url, {"title": "Failed"}, format="json")
    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível criar a tarefa."
    assert not Task.objects.exists()


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_collection_unsupported_methods(api_client, url, method):
    assert getattr(api_client, method)(url, {}, format="json").status_code == 405
