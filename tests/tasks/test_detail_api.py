import json
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task
from apps.tasks.serializers import TaskSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def task(project, owner):
    return Task.objects.create(
        project=project,
        created_by=owner,
        title="Original",
        description="Original description",
    )


def detail_path(task):
    return reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": task.project.organization_id,
            "project_id": task.project_id,
            "task_id": task.pk,
        },
    )


@pytest.fixture
def detail_url(task):
    return detail_path(task)


def snapshot(task):
    return (
        task.title,
        task.description,
        task.project_id,
        task.created_by_id,
        task.status,
        task.created_at,
        task.updated_at,
    )


def assert_unchanged(task):
    before = snapshot(task)
    task.refresh_from_db()
    assert snapshot(task) == before


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_detail_requires_valid_jwt(detail_url, task, method, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = getattr(client, method)(detail_url, {"title": "Attempt"}, format="json")
    assert response.status_code == 401
    assert_unchanged(task)


@pytest.mark.parametrize("role", ["owner", "member"])
@pytest.mark.parametrize("archived", [False, True])
def test_participants_read_task_in_active_or_archived_project(
    client_for, owner, member, membership, project, task, detail_url, role, archived
):
    project.is_archived = archived
    project.save(update_fields=["is_archived"])
    response = client_for(owner if role == "owner" else member).get(detail_url)
    assert response.status_code == 200
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
    assert response.data["id"] == task.pk and response.data["project_id"] == project.pk
    assert (
        response.data["title"] == "Original"
        and response.data["description"] == "Original description"
    )
    assert (
        response.data["created_by_id"] == owner.pk and response.data["status"] == "todo"
    )
    assert_unchanged(task)


def test_details_support_null_author(api_client, task, detail_url):
    Task.objects.filter(pk=task.pk).update(created_by=None)
    response = api_client.get(detail_url)
    assert response.status_code == 200 and response.data["created_by_id"] is None


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_cannot_distinguish_existing_and_missing_task(
    client_for, outsider, task, detail_url, method, superuser
):
    outsider.is_staff = outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    client = client_for(outsider)
    missing = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": task.project.organization_id,
            "project_id": task.project_id,
            "task_id": task.pk + 999,
        },
    )
    existing_response = getattr(client, method)(
        detail_url, {"title": "Attempt"}, format="json"
    )
    missing_response = getattr(client, method)(
        missing, {"title": "Attempt"}, format="json"
    )
    assert existing_response.status_code == missing_response.status_code == 404
    assert existing_response.data == missing_response.data
    assert_unchanged(task)


@pytest.mark.parametrize("method", ["get", "patch"])
def test_missing_ids_and_crossed_parents_are_404_even_for_owner_of_both(
    api_client, owner, organization, project, task, method
):
    second_project = Project.objects.create(organization=organization, name="Second")
    sibling = Task.objects.create(project=second_project, title="Sibling")
    other = Organization.objects.create(name="Other", slug="task-detail-other")
    Membership.objects.create(organization=other, user=owner, role="owner")
    other_project = Project.objects.create(organization=other, name="Other project")
    external = Task.objects.create(project=other_project, title="External")
    ids = [
        (organization.pk + other.pk + 999, project.pk, task.pk),
        (organization.pk, other_project.pk + second_project.pk + 999, task.pk),
        (organization.pk, project.pk, task.pk + sibling.pk + external.pk + 999),
        (organization.pk, project.pk, sibling.pk),
        (organization.pk, project.pk, external.pk),
        (organization.pk, other_project.pk, external.pk),
        (other.pk, project.pk, task.pk),
    ]
    for organization_id, project_id, task_id in ids:
        path = reverse(
            "projects:tasks:task-detail",
            kwargs={
                "organization_id": organization_id,
                "project_id": project_id,
                "task_id": task_id,
            },
        )
        assert (
            getattr(api_client, method)(
                path, {"title": "Forbidden"}, format="json"
            ).status_code
            == 404
        )
    assert api_client.get(detail_path(sibling)).status_code == 200
    assert api_client.get(detail_path(external)).status_code == 200
    for record in [task, sibling, external]:
        assert_unchanged(record)


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "  Renamed  "},
        {"description": "Changed"},
        {"description": ""},
        {"title": "Renamed", "description": "Changed"},
        {},
    ],
)
def test_owner_patch_preserves_unsupplied_and_controlled_fields(
    api_client, task, detail_url, payload
):
    original = snapshot(task)
    response = api_client.patch(detail_url, payload, format="json")
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.title == payload.get("title", "Original").strip()
    assert task.description == payload.get("description", "Original description")
    assert snapshot(task)[2:-1] == original[2:-1]
    if payload:
        assert task.updated_at > original[-1]
    else:
        assert task.updated_at == original[-1]
    assert (
        response.data["title"] == task.title
        and response.data["description"] == task.description
    )
    assert api_client.get(detail_url).data == response.data


def test_owner_edits_task_of_archived_project_without_changing_state(
    api_client, task, project, detail_url
):
    project.is_archived = True
    project.save(update_fields=["is_archived"])
    Task.objects.filter(pk=task.pk).update(status="done")
    response = api_client.patch(
        detail_url, {"description": "Edited history"}, format="json"
    )
    assert response.status_code == 200 and response.data["status"] == "done"
    task.refresh_from_db()
    project.refresh_from_db()
    assert task.description == "Edited history" and task.status == "done"
    assert project.is_archived is True


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": None}, "title"),
        ({"title": "x" * 151}, "title"),
        ({"description": None}, "description"),
        ({"description": "x" * 5001}, "description"),
        ({"title": "Valid", "description": "x" * 5001}, "description"),
    ],
)
def test_invalid_patch_is_atomic(api_client, task, detail_url, payload, field):
    response = api_client.patch(detail_url, payload, format="json")
    assert response.status_code == 400 and field in response.data
    assert_unchanged(task)


def test_patch_accepts_title_and_description_limits(api_client, detail_url):
    response = api_client.patch(
        detail_url, {"title": "x" * 150, "description": "x" * 5000}, format="json"
    )
    assert response.status_code == 200
    assert (
        len(response.data["title"]) == 150 and len(response.data["description"]) == 5000
    )


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "project",
        "project_id",
        "organization",
        "organization_id",
        "created_by",
        "created_by_id",
        "created_at",
        "updated_at",
        "owner",
        "my_role",
        "assignee_id",
        "is_archived",
        "unexpected",
    ],
)
def test_patch_rejects_controlled_and_unknown_fields(
    api_client, task, detail_url, field
):
    response = api_client.patch(
        detail_url, {"title": "Attempt", field: 999}, format="json"
    )
    assert response.status_code == 400 and field in response.data
    assert_unchanged(task)


@pytest.mark.parametrize("state", ["todo", "in_progress", "done"])
def test_owner_patches_title_and_valid_status_together(
    api_client, task, detail_url, state
):
    response = api_client.patch(
        detail_url, {"title": "Attempt", "status": state}, format="json"
    )
    assert response.status_code == 200
    before = snapshot(task)
    task.refresh_from_db()
    assert task.title == "Attempt" and task.status == state
    assert task.description == before[1]
    assert task.project_id == before[2] and task.created_by_id == before[3]
    assert task.created_at == before[5]


@pytest.mark.parametrize("payload", [[], "invalid", 123, None])
def test_patch_requires_object_json(api_client, task, detail_url, payload):
    response = api_client.generic(
        "PATCH", detail_url, json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert_unchanged(task)


def test_member_cannot_spoof_owner_with_body_or_query(
    client_for, member, membership, owner, task, detail_url
):
    client = client_for(member)
    response = client.patch(
        detail_url + f"?user_id={owner.pk}&my_role=owner",
        {"title": "Attempt", "created_by_id": owner.pk, "my_role": "owner"},
        format="json",
    )
    assert response.status_code == 403
    assert_unchanged(task)
    membership.refresh_from_db()
    assert membership.role == "member"


def test_query_ids_cannot_switch_target_or_identity(
    api_client, owner, outsider, task, detail_url
):
    other = Organization.objects.create(name="Other", slug="task-detail-query-other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    other_project = Project.objects.create(organization=other, name="Other")
    external = Task.objects.create(
        project=other_project, title="External", created_by=outsider
    )
    response = api_client.patch(
        detail_url
        + f"?organization_id={other.pk}&project_id={other_project.pk}&task_id={external.pk}&user_id={outsider.pk}",
        {"title": "Renamed"},
        format="json",
    )
    assert response.status_code == 200
    assert (
        response.data["id"] == task.pk
        and response.data["project_id"] == task.project_id
    )
    assert response.data["created_by_id"] == owner.pk
    assert_unchanged(external)


def test_owner_in_a_cannot_edit_b_as_member_even_as_task_author(
    api_client, owner, outsider, detail_url
):
    other = Organization.objects.create(name="Other", slug="task-detail-role-other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    Membership.objects.create(organization=other, user=owner, role="member")
    other_project = Project.objects.create(organization=other, name="Other")
    external = Task.objects.create(
        project=other_project, title="Historical", created_by=owner
    )
    path = detail_path(external)
    assert (
        api_client.patch(
            detail_url, {"title": "Owned update"}, format="json"
        ).status_code
        == 200
    )
    assert api_client.get(path).status_code == 200
    assert (
        api_client.patch(path, {"title": "Forbidden"}, format="json").status_code == 403
    )
    assert_unchanged(external)


def test_author_loses_access_with_same_jwt_after_role_and_link_revocation(
    api_client, client_for, owner, outsider, organization, task, detail_url
):
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    manager = client_for(outsider)
    link = Membership.objects.get(organization=organization, user=owner)
    membership_url = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": link.pk},
    )
    assert (
        manager.patch(membership_url, {"role": "member"}, format="json").status_code
        == 200
    )
    assert api_client.get(detail_url).status_code == 200
    assert (
        api_client.patch(detail_url, {"title": "Forbidden"}, format="json").status_code
        == 403
    )
    assert manager.delete(membership_url).status_code == 204
    assert api_client.get(detail_url).status_code == 404
    assert (
        api_client.patch(detail_url, {"title": "Forbidden"}, format="json").status_code
        == 404
    )
    assert_unchanged(task)
    assert task.created_by_id == owner.pk


def test_promoted_member_edits_using_original_jwt(
    api_client, client_for, member, membership, organization, task, detail_url
):
    client = client_for(member)
    assert (
        client.patch(detail_url, {"title": "Forbidden"}, format="json").status_code
        == 403
    )
    path = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    assert api_client.patch(path, {"role": "owner"}, format="json").status_code == 200
    response = client.patch(detail_url, {"title": "Promoted editor"}, format="json")
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.title == "Promoted editor"


def test_partial_save_preserves_concurrent_change_to_omitted_field(task):
    serializer = TaskSerializer(task, data={"description": "Edited"}, partial=True)
    assert serializer.is_valid(), serializer.errors
    Task.objects.filter(pk=task.pk).update(title="Concurrent title")
    serializer.save()
    task.refresh_from_db()
    assert task.title == "Concurrent title" and task.description == "Edited"


def test_integrity_failure_is_generic_and_rolls_back(api_client, task, detail_url):
    with patch(
        "apps.tasks.serializers.Task.save",
        side_effect=IntegrityError("private SQL failure"),
    ):
        response = api_client.patch(detail_url, {"title": "Attempt"}, format="json")
    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível atualizar a tarefa."
    assert "private SQL failure" not in response.content.decode()
    assert_unchanged(task)


@pytest.mark.parametrize("method", ["put", "post", "delete"])
def test_detail_does_not_offer_other_write_methods(
    api_client, task, detail_url, method
):
    response = getattr(api_client, method)(
        detail_url, {"title": "Attempt"}, format="json"
    )
    assert response.status_code == 405
    assert_unchanged(task)
