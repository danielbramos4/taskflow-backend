import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task
from apps.tasks.serializers import TaskUpdateSerializer

pytestmark = pytest.mark.django_db
STATES = ["todo", "in_progress", "done"]


@pytest.fixture
def task(project, owner):
    return Task.objects.create(
        project=project, created_by=owner, title="Original", description="Scope"
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
        task.created_at,
        task.updated_at,
    )


def assert_unchanged(task):
    original = snapshot(task)
    task.refresh_from_db()
    assert snapshot(task) == original


@pytest.mark.parametrize("initial", STATES)
@pytest.mark.parametrize("target", STATES)
def test_owner_can_transition_between_all_states_without_losing_records(
    api_client,
    task,
    owner,
    outsider,
    url,
    detail_url,
    initial,
    target,
    django_user_model,
):
    Task.objects.filter(pk=task.pk).update(status=initial)
    task.refresh_from_db()
    original = snapshot(task)
    other = Organization.objects.create(name="Other team", slug="status-other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    other_project = Project.objects.create(organization=other, name="Other project")
    private_task = Task.objects.create(
        project=other_project,
        title="Private",
        status="in_progress",
        created_by=outsider,
    )
    models = [Task, Project, Organization, Membership, django_user_model]
    before_counts = [model.objects.count() for model in models]

    response = api_client.patch(detail_url, {"status": target}, format="json")

    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == response.data["status"] == target
    assert snapshot(task)[:2] == original[:2] and snapshot(task)[3:-1] == original[3:-1]
    assert task.created_by_id == owner.pk and task.updated_at > original[-1]
    assert (
        response.data["id"] == task.pk
        and response.data["project_id"] == task.project_id
    )
    assert api_client.get(detail_url).data == response.data
    assert api_client.get(url).data["results"] == [response.data]
    assert [model.objects.count() for model in models] == before_counts
    assert_unchanged(private_task)


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "",
        "TODO",
        "to_do",
        "in progress",
        "complete",
        " done ",
        "DONE",
        0,
        1,
        True,
        False,
        [],
        {},
        ["done"],
    ],
)
def test_invalid_status_rejects_whole_patch(api_client, task, detail_url, invalid):
    response = api_client.patch(
        detail_url, {"title": "Attempt", "status": invalid}, format="json"
    )
    assert response.status_code == 400 and "status" in response.data
    assert_unchanged(task)


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"status": "done", "title": ""}, "title"),
        ({"status": "done", "description": None}, "description"),
        ({"status": "done", "description": "x" * 5001}, "description"),
        ({"status": "done", "project_id": 999}, "project_id"),
        ({"status": "done", "created_by_id": 999}, "created_by_id"),
        ({"status": "done", "updated_at": "2026-01-01T00:00:00Z"}, "updated_at"),
        ({"status": "done", "unexpected": "value"}, "unexpected"),
    ],
)
def test_bad_companion_field_prevents_status_change(
    api_client, task, detail_url, payload, field
):
    response = api_client.patch(detail_url, payload, format="json")
    assert response.status_code == 400 and field in response.data
    assert_unchanged(task)


def test_status_and_both_content_fields_can_change_together(
    api_client, task, detail_url
):
    response = api_client.patch(
        detail_url,
        {"title": "Reviewed", "description": "Accepted scope", "status": "done"},
        format="json",
    )
    assert response.status_code == 200
    task.refresh_from_db()
    assert (task.title, task.description, task.status) == (
        "Reviewed",
        "Accepted scope",
        "done",
    )


@pytest.mark.parametrize("state", STATES)
def test_post_does_not_accept_status_even_when_valid(api_client, url, state):
    response = api_client.post(
        url, {"title": "Attempt", "status": state}, format="json"
    )
    assert response.status_code == 400 and "status" in response.data
    assert not Task.objects.exists()


@pytest.mark.parametrize("state", STATES)
def test_members_read_but_cannot_change_status(
    api_client, client_for, membership, member, task, detail_url, state
):
    client = client_for(member)
    assert client.get(detail_url).data["status"] == "todo"
    assert client.patch(detail_url, {"status": state}, format="json").status_code == 403
    assert_unchanged(task)


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_status_change_requires_valid_jwt(task, detail_url, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert (
        client.patch(detail_url, {"status": "done"}, format="json").status_code == 401
    )
    assert_unchanged(task)


@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_cannot_change_status(
    client_for, outsider, task, detail_url, superuser
):
    outsider.is_staff = outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    assert (
        client_for(outsider)
        .patch(detail_url, {"status": "done"}, format="json")
        .status_code
        == 404
    )
    assert_unchanged(task)


def test_status_changes_cannot_cross_project_or_organization(
    api_client, owner, organization, project, task
):
    sibling_project = Project.objects.create(organization=organization, name="Sibling")
    other = Organization.objects.create(name="Other", slug="status-wrong-parent")
    Membership.objects.create(organization=other, user=owner, role="owner")
    other_project = Project.objects.create(organization=other, name="Other")
    foreign_task = Task.objects.create(
        project=other_project, title="Foreign", status="done"
    )
    for organization_id, project_id, task_id in [
        (organization.pk, sibling_project.pk, task.pk),
        (organization.pk, project.pk, foreign_task.pk),
        (organization.pk, other_project.pk, foreign_task.pk),
        (other.pk, project.pk, task.pk),
    ]:
        path = reverse(
            "projects:tasks:task-detail",
            kwargs={
                "organization_id": organization_id,
                "project_id": project_id,
                "task_id": task_id,
            },
        )
        assert (
            api_client.patch(path, {"status": "in_progress"}, format="json").status_code
            == 404
        )
    assert_unchanged(task)
    assert_unchanged(foreign_task)


def test_owner_of_a_cannot_change_b_as_member_even_if_author(
    api_client, owner, outsider, detail_url
):
    other = Organization.objects.create(name="Other", slug="status-role-other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    Membership.objects.create(organization=other, user=owner, role="member")
    project = Project.objects.create(organization=other, name="Other")
    task = Task.objects.create(project=project, title="Historical", created_by=owner)
    path = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": other.pk,
            "project_id": project.pk,
            "task_id": task.pk,
        },
    )
    assert (
        api_client.patch(detail_url, {"status": "done"}, format="json").status_code
        == 200
    )
    assert api_client.get(path).status_code == 200
    assert api_client.patch(path, {"status": "done"}, format="json").status_code == 403
    assert_unchanged(task)


def test_promotion_demotion_and_removal_with_same_token_enforce_status_permissions(
    api_client, client_for, membership, member, owner, task, detail_url, organization
):
    client = client_for(member)
    path = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    assert (
        client.patch(detail_url, {"status": "done"}, format="json").status_code == 403
    )
    assert api_client.patch(path, {"role": "owner"}, format="json").status_code == 200
    assert (
        client.patch(detail_url, {"status": "done"}, format="json").status_code == 200
    )
    assert api_client.patch(path, {"role": "member"}, format="json").status_code == 200
    assert client.get(detail_url).data["status"] == "done"
    assert (
        client.patch(detail_url, {"status": "todo"}, format="json").status_code == 403
    )
    assert api_client.delete(path).status_code == 204
    assert client.get(detail_url).status_code == 404
    assert (
        client.patch(detail_url, {"status": "todo"}, format="json").status_code == 404
    )
    task.refresh_from_db()
    assert task.status == "done" and task.created_by_id == owner.pk


def test_creator_loses_status_access_after_role_and_link_revocation(
    api_client, client_for, owner, outsider, organization, task, detail_url
):
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    manager = client_for(outsider)
    own_link = Membership.objects.get(organization=organization, user=owner)
    path = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": own_link.pk},
    )
    assert manager.patch(path, {"role": "member"}, format="json").status_code == 200
    assert api_client.get(detail_url).status_code == 200
    assert (
        api_client.patch(detail_url, {"status": "done"}, format="json").status_code
        == 403
    )
    assert manager.delete(path).status_code == 204
    assert (
        api_client.patch(detail_url, {"status": "done"}, format="json").status_code
        == 404
    )
    assert_unchanged(task)


def test_status_can_change_in_archived_project_without_affecting_archive(
    api_client, client_for, member, membership, project, task, detail_url
):
    project.is_archived = True
    project.save(update_fields=["is_archived"])
    response = api_client.patch(detail_url, {"status": "done"}, format="json")
    assert response.status_code == 200 and response.data["status"] == "done"
    assert client_for(member).get(detail_url).data["status"] == "done"
    assert (
        client_for(member)
        .patch(detail_url, {"status": "todo"}, format="json")
        .status_code
        == 403
    )
    project.refresh_from_db()
    assert project.is_archived is True


def test_content_patch_preserves_a_concurrent_change_to_omitted_status(task):
    serializer = TaskUpdateSerializer(
        task, data={"description": "Edited"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    Task.objects.filter(pk=task.pk).update(status="done")
    serializer.save()
    task.refresh_from_db()
    assert task.description == "Edited" and task.status == "done"


def test_status_patch_preserves_a_concurrent_change_to_omitted_content(task):
    serializer = TaskUpdateSerializer(task, data={"status": "done"}, partial=True)
    assert serializer.is_valid(), serializer.errors
    Task.objects.filter(pk=task.pk).update(title="Concurrent title")
    serializer.save()
    task.refresh_from_db()
    assert task.status == "done" and task.title == "Concurrent title"
