import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def task(project, owner):
    return Task.objects.create(
        project=project, title="Original", description="Scope", created_by=owner
    )


@pytest.fixture
def detail_url(project, organization, task):
    return reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization.pk,
            "project_id": project.pk,
            "task_id": task.pk,
        },
    )


def snapshot(task):
    return (
        task.title,
        task.description,
        task.status,
        task.project_id,
        task.created_by_id,
        task.assignee_id,
        task.created_at,
        task.updated_at,
    )


def assert_unchanged(task):
    before = snapshot(task)
    task.refresh_from_db()
    assert snapshot(task) == before


@pytest.mark.parametrize("target_role", ["member", "owner"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_owner_assigns_active_participant_and_preserves_identity(
    api_client,
    owner,
    member,
    membership,
    project,
    url,
    task,
    detail_url,
    target_role,
    operation,
):
    membership.role = target_role
    membership.save(update_fields=["role"])
    if operation == "create":
        response = api_client.post(
            url,
            {"title": "New", "assignee_membership_id": membership.pk},
            format="json",
        )
    else:
        response = api_client.patch(
            detail_url, {"assignee_membership_id": membership.pk}, format="json"
        )
    assert response.status_code == (201 if operation == "create" else 200)
    assert response.data["assignee_membership_id"] == membership.pk
    assert response.data["assignee_user_id"] == member.pk
    stored = Task.objects.get(pk=response.data["id"])
    assert stored.assignee_id == membership.pk and stored.created_by_id == owner.pk
    assert stored.project_id == project.pk and stored.status == "todo"
    if operation == "update":
        assert (stored.title, stored.description, stored.created_at) == (
            task.title,
            task.description,
            task.created_at,
        )


@pytest.mark.parametrize("supplied", [False, True])
def test_create_can_leave_task_unassigned(api_client, url, supplied):
    payload = {"title": "Unassigned"}
    if supplied:
        payload["assignee_membership_id"] = None
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert (
        response.data["assignee_membership_id"] is None
        and response.data["assignee_user_id"] is None
    )
    assert Task.objects.get(pk=response.data["id"]).assignee_id is None


def test_reassign_clear_and_omitted_assignment(
    api_client, owner, organization, membership, task, detail_url
):
    assert (
        api_client.patch(
            detail_url, {"assignee_membership_id": membership.pk}, format="json"
        ).status_code
        == 200
    )
    own_link = Membership.objects.get(user=owner, organization=organization)
    reassigned = api_client.patch(
        detail_url,
        {"assignee_membership_id": own_link.pk, "status": "done"},
        format="json",
    )
    assert (
        reassigned.status_code == 200
        and reassigned.data["assignee_user_id"] == owner.pk
    )
    edited = api_client.patch(detail_url, {"description": "Edited"}, format="json")
    assert edited.data["assignee_membership_id"] == own_link.pk
    cleared = api_client.patch(
        detail_url, {"assignee_membership_id": None}, format="json"
    )
    assert cleared.status_code == 200
    assert (
        cleared.data["assignee_membership_id"] is None
        and cleared.data["assignee_user_id"] is None
    )
    task.refresh_from_db()
    assert (
        task.assignee_id is None
        and task.description == "Edited"
        and task.status == "done"
    )


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("invalid", [0, -1, 999999, "invalid", True, False, [], {}])
def test_invalid_assignee_is_rejected_atomically(
    api_client, task, url, detail_url, operation, invalid
):
    payload = {"title": "Attempt", "assignee_membership_id": invalid}
    response = (
        api_client.post(url, payload, format="json")
        if operation == "create"
        else api_client.patch(detail_url, payload, format="json")
    )
    assert response.status_code == 400 and "assignee_membership_id" in response.data
    assert Task.objects.count() == 1
    assert_unchanged(task)


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("kind", ["foreign_organization", "inactive", "removed"])
def test_ineligible_membership_is_rejected_without_disclosing_user_data(
    api_client, owner, member, membership, task, url, detail_url, operation, kind
):
    target_id = membership.pk
    if kind == "foreign_organization":
        other = Organization.objects.create(name="Other", slug="assignment-other")
        Membership.objects.create(organization=other, user=owner, role="owner")
        foreign = Membership.objects.create(
            organization=other, user=member, role="member"
        )
        target_id = foreign.pk
    elif kind == "inactive":
        member.is_active = False
        member.save(update_fields=["is_active"])
    else:
        membership.delete()
    payload = {"title": "Attempt", "assignee_membership_id": target_id}
    response = (
        api_client.post(url, payload, format="json")
        if operation == "create"
        else api_client.patch(detail_url, payload, format="json")
    )
    assert response.status_code == 400 and "assignee_membership_id" in response.data
    assert member.username not in str(response.data)
    assert Task.objects.count() == 1
    assert_unchanged(task)


@pytest.mark.parametrize(
    "payload",
    [
        {"assignee_user_id": 999},
        {"assignee": 999},
        {"assignee_id": 999},
        {"assignee_membership_id": None, "description": None},
        {"assignee_membership_id": None, "project_id": 999},
    ],
)
def test_forbidden_or_invalid_companion_fields_preserve_assignment(
    api_client, membership, task, detail_url, payload
):
    Task.objects.filter(pk=task.pk).update(assignee=membership)
    task.refresh_from_db()
    response = api_client.patch(detail_url, payload, format="json")
    assert response.status_code == 400
    assert_unchanged(task)


def test_assigned_member_reads_but_gains_no_write_permission(
    api_client, member, membership, client_for, task, url, detail_url
):
    assert (
        api_client.patch(
            detail_url, {"assignee_membership_id": membership.pk}, format="json"
        ).status_code
        == 200
    )
    client = client_for(member)
    detail = client.get(detail_url)
    assert detail.status_code == 200 and detail.data["assignee_user_id"] == member.pk
    assert client.get(url).data["results"] == [detail.data]
    for payload in [
        {"assignee_membership_id": None},
        {"status": "done"},
        {"title": "Forbidden"},
    ]:
        assert client.patch(detail_url, payload, format="json").status_code == 403
    assert (
        client.post(
            url,
            {"title": "Forbidden", "assignee_membership_id": membership.pk},
            format="json",
        ).status_code
        == 403
    )
    task.refresh_from_db()
    assert (
        task.assignee_id == membership.pk
        and task.title == "Original"
        and task.status == "todo"
    )


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_assignment_requires_authentication(task, membership, detail_url, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert (
        client.patch(
            detail_url, {"assignee_membership_id": membership.pk}, format="json"
        ).status_code
        == 401
    )
    assert_unchanged(task)


@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_cannot_assign_even_as_superuser(
    client_for, outsider, membership, task, detail_url, superuser
):
    outsider.is_staff = outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    assert (
        client_for(outsider)
        .patch(detail_url, {"assignee_membership_id": membership.pk}, format="json")
        .status_code
        == 404
    )
    assert_unchanged(task)


def test_crossed_task_parent_cannot_assign(
    api_client, organization, owner, membership, task, detail_url
):
    sibling_project = Project.objects.create(organization=organization, name="Sibling")
    foreign_task = Task.objects.create(project=sibling_project, title="Sibling task")
    path = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization.pk,
            "project_id": task.project_id,
            "task_id": foreign_task.pk,
        },
    )
    assert (
        api_client.patch(
            path, {"assignee_membership_id": membership.pk}, format="json"
        ).status_code
        == 404
    )
    assert_unchanged(foreign_task)
    assert_unchanged(task)


def test_membership_removal_clears_assignment_and_rejoin_does_not_restore_it(
    api_client, client_for, member, membership, project, task, detail_url, organization
):
    api_client.patch(
        detail_url, {"assignee_membership_id": membership.pk}, format="json"
    )
    task.refresh_from_db()
    before = snapshot(task)
    link_url = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    client = client_for(member)
    assert api_client.delete(link_url).status_code == 204
    task.refresh_from_db()
    assert task.assignee_id is None
    assert snapshot(task)[:5] == before[:5] and snapshot(task)[6:] == before[6:]
    assert client.get(detail_url).status_code == 404
    assert Task.objects.count() == 1 and Project.objects.filter(pk=project.pk).exists()
    assert type(member).objects.filter(pk=member.pk).exists()
    link_list = reverse(
        "organizations:membership-list", kwargs={"organization_id": organization.pk}
    )
    added = api_client.post(link_list, {"user_id": member.pk}, format="json")
    assert added.status_code == 201 and added.data["id"] != membership.pk
    assert api_client.get(detail_url).data["assignee_membership_id"] is None
    assert client.get(detail_url).status_code == 200


def test_deleting_assigned_user_preserves_task_and_creator(
    api_client, member, membership, task, detail_url, owner
):
    api_client.patch(
        detail_url, {"assignee_membership_id": membership.pk}, format="json"
    )
    member.delete()
    task.refresh_from_db()
    assert task.assignee_id is None and task.created_by_id == owner.pk
    assert task.title == "Original" and Task.objects.count() == 1


def test_archived_project_and_role_changes_preserve_assignment(
    api_client, client_for, member, membership, project, task, detail_url, organization
):
    project.is_archived = True
    project.save(update_fields=["is_archived"])
    response = api_client.patch(
        detail_url, {"assignee_membership_id": membership.pk}, format="json"
    )
    assert response.status_code == 200
    link = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    client = client_for(member)
    assert api_client.patch(link, {"role": "owner"}, format="json").status_code == 200
    assert (
        client.patch(detail_url, {"status": "done"}, format="json").status_code == 200
    )
    assert api_client.patch(link, {"role": "member"}, format="json").status_code == 200
    assert (
        client.patch(detail_url, {"status": "todo"}, format="json").status_code == 403
    )
    task.refresh_from_db()
    project.refresh_from_db()
    assert (
        task.assignee_id == membership.pk
        and task.status == "done"
        and project.is_archived
    )


def test_assignment_list_does_not_add_per_task_queries(
    api_client, membership, project, url
):
    Task.objects.create(project=project, title="First", assignee=membership)
    with CaptureQueriesContext(connection) as small:
        response = api_client.get(url)
    assert response.status_code == 200 and response.data["count"] == 1
    Task.objects.bulk_create(
        [
            Task(project=project, title=f"Task {index}", assignee=membership)
            for index in range(22)
        ]
    )
    with CaptureQueriesContext(connection) as large:
        response = api_client.get(url)
    assert response.status_code == 200 and len(response.data["results"]) == 20
    assert len(large) == len(small)


def test_assignment_options_do_not_require_a_parent_lookup(api_client, detail_url, url):
    assert api_client.options(url).status_code == 200
    assert api_client.options(detail_url).status_code == 200
