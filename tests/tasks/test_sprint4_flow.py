import pytest
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "sprint4-acceptance-test-only-password"


def authenticated_client(user):
    client = APIClient()
    response = client.post(
        reverse("token_obtain_pair"),
        {"username": user.username, "password": TEST_PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    profile = client.get(reverse("current_user"))
    assert profile.status_code == 200 and profile.data["id"] == user.pk
    return client, response.data


def test_sprint4_complete_flow_preserves_tasks_isolation_ownership_and_auth(
    django_user_model,
):
    creator, teammate, outsider = [
        django_user_model.objects.create_user(username=username, password=TEST_PASSWORD)
        for username in ["task-flow-owner", "task-flow-member", "task-flow-outsider"]
    ]
    owner_client, owner_tokens = authenticated_client(creator)
    member_client, _ = authenticated_client(teammate)
    outsider_client, _ = authenticated_client(outsider)
    organizations_url = reverse("organizations:organization-list")
    organization = owner_client.post(
        organizations_url,
        {"name": "Task team", "slug": "task-flow-team"},
        format="json",
    )
    external = outsider_client.post(
        organizations_url,
        {"name": "Private team", "slug": "task-flow-private"},
        format="json",
    )
    assert organization.status_code == external.status_code == 201
    organization_id = organization.data["id"]
    projects_url = reverse(
        "projects:project-list", kwargs={"organization_id": organization_id}
    )
    external_projects_url = reverse(
        "projects:project-list", kwargs={"organization_id": external.data["id"]}
    )
    project = owner_client.post(
        projects_url, {"name": "Delivery project"}, format="json"
    )
    sibling_project = owner_client.post(
        projects_url, {"name": "Sibling project"}, format="json"
    )
    private_project = outsider_client.post(
        external_projects_url, {"name": "Private project"}, format="json"
    )
    assert (
        project.status_code
        == sibling_project.status_code
        == private_project.status_code
        == 201
    )
    project_id = project.data["id"]
    project_url = reverse(
        "projects:project-detail",
        kwargs={"organization_id": organization_id, "project_id": project_id},
    )
    tasks_url = reverse(
        "projects:tasks:task-list",
        kwargs={"organization_id": organization_id, "project_id": project_id},
    )
    sibling_tasks_url = reverse(
        "projects:tasks:task-list",
        kwargs={
            "organization_id": organization_id,
            "project_id": sibling_project.data["id"],
        },
    )
    private_tasks_url = reverse(
        "projects:tasks:task-list",
        kwargs={
            "organization_id": external.data["id"],
            "project_id": private_project.data["id"],
        },
    )
    created = owner_client.post(
        tasks_url,
        {"title": "First task", "description": "Initial scope"},
        format="json",
    )
    sibling = owner_client.post(
        sibling_tasks_url, {"title": "Sibling task"}, format="json"
    )
    private = outsider_client.post(
        private_tasks_url, {"title": "Private task"}, format="json"
    )
    assert created.status_code == sibling.status_code == private.status_code == 201
    task_id = created.data["id"]
    assert set(created.data) == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "created_by_id",
        "created_at",
        "updated_at",
    }
    assert created.data["project_id"] == project_id
    assert (
        created.data["created_by_id"] == creator.pk and created.data["status"] == "todo"
    )
    task_url = reverse(
        "projects:tasks:task-detail",
        kwargs={
            "organization_id": organization_id,
            "project_id": project_id,
            "task_id": task_id,
        },
    )
    assert outsider_client.get(tasks_url).status_code == 404
    assert outsider_client.get(task_url).status_code == 404
    assert owner_client.get(private_tasks_url).status_code == 404
    for wrong_task_id in [sibling.data["id"], private.data["id"]]:
        path = reverse(
            "projects:tasks:task-detail",
            kwargs={
                "organization_id": organization_id,
                "project_id": project_id,
                "task_id": wrong_task_id,
            },
        )
        assert owner_client.get(path).status_code == 404
        assert (
            owner_client.patch(path, {"status": "done"}, format="json").status_code
            == 404
        )

    memberships_url = reverse(
        "organizations:membership-list", kwargs={"organization_id": organization_id}
    )
    own_link = Membership.objects.get(organization_id=organization_id, user=creator)
    own_link_url = f"{memberships_url}{own_link.pk}/"
    added = owner_client.post(memberships_url, {"user_id": teammate.pk}, format="json")
    assert added.status_code == 201 and added.data["role"] == "member"
    teammate_link_url = f"{memberships_url}{added.data['id']}/"
    listing = member_client.get(tasks_url)
    assert listing.status_code == 200 and listing.data["count"] == 1
    assert listing.data["results"] == [created.data]
    assert member_client.get(task_url).data == created.data
    assert (
        member_client.post(tasks_url, {"title": "Forbidden"}, format="json").status_code
        == 403
    )
    for payload in [
        {"title": "Forbidden"},
        {"status": "in_progress"},
        {"status": "done"},
        {"status": "todo"},
    ]:
        assert member_client.patch(task_url, payload, format="json").status_code == 403

    edited = owner_client.patch(task_url, {"title": "Reviewed task"}, format="json")
    assert edited.status_code == 200
    assert (
        edited.data["description"] == "Initial scope"
        and edited.data["status"] == "todo"
    )
    for state in ["in_progress", "done", "todo", "done"]:
        response = owner_client.patch(task_url, {"status": state}, format="json")
        assert response.status_code == 200 and response.data["status"] == state
        assert member_client.get(task_url).data["status"] == state
    archived = owner_client.patch(project_url, {"is_archived": True}, format="json")
    assert archived.status_code == 200 and archived.data["is_archived"] is True
    assert member_client.get(task_url).data["status"] == "done"
    archived_edit = owner_client.patch(
        task_url,
        {"description": "Accepted scope", "status": "in_progress"},
        format="json",
    )
    assert archived_edit.status_code == 200
    assert (
        archived_edit.data["description"] == "Accepted scope"
        and archived_edit.data["status"] == "in_progress"
    )
    restored = owner_client.patch(project_url, {"is_archived": False}, format="json")
    assert restored.status_code == 200 and restored.data["is_archived"] is False

    # The original JWTs remain in use while the organization roles change.
    assert (
        owner_client.patch(
            teammate_link_url, {"role": "owner"}, format="json"
        ).status_code
        == 200
    )
    promoted_edit = member_client.patch(task_url, {"status": "done"}, format="json")
    assert (
        promoted_edit.status_code == 200
        and promoted_edit.data["created_by_id"] == creator.pk
    )
    assert (
        member_client.patch(own_link_url, {"role": "member"}, format="json").status_code
        == 200
    )
    assert owner_client.get(task_url).status_code == 200
    assert (
        owner_client.patch(task_url, {"title": "Forbidden"}, format="json").status_code
        == 403
    )
    assert (
        owner_client.patch(task_url, {"status": "todo"}, format="json").status_code
        == 403
    )
    assert member_client.delete(teammate_link_url).status_code == 400
    assert member_client.delete(own_link_url).status_code == 204
    assert owner_client.get(tasks_url).status_code == 404
    assert owner_client.get(task_url).status_code == 404
    assert (
        owner_client.patch(task_url, {"status": "todo"}, format="json").status_code
        == 404
    )

    refreshed = APIClient().post(
        reverse("token_refresh"), {"refresh": owner_tokens["refresh"]}, format="json"
    )
    assert refreshed.status_code == 200
    owner_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
    profile = owner_client.get(reverse("current_user"))
    assert profile.status_code == 200 and profile.data["id"] == creator.pk
    assert owner_client.get(tasks_url).status_code == 404
    assert owner_client.get(task_url).status_code == 404
    assert (
        owner_client.patch(task_url, {"status": "todo"}, format="json").status_code
        == 404
    )
    reopened = member_client.patch(task_url, {"status": "todo"}, format="json")
    assert reopened.status_code == 200 and reopened.data["status"] == "todo"

    task = Task.objects.get(pk=task_id)
    assert (task.title, task.description, task.status) == (
        "Reviewed task",
        "Accepted scope",
        "todo",
    )
    assert task.project_id == project_id and task.created_by_id == creator.pk
    assert task.created_at == parse_datetime(created.data["created_at"])
    stored_project = Project.objects.get(pk=project_id)
    assert (
        stored_project.organization_id == organization_id
        and stored_project.is_archived is False
    )
    assert stored_project.created_by_id == creator.pk
    assert django_user_model.objects.count() == 3
    assert Organization.objects.count() == 2 and Project.objects.count() == 3
    assert Task.objects.count() == 3 and Membership.objects.count() == 2
    assert Membership.objects.filter(
        organization_id=organization_id,
        user=teammate,
        role="owner",
        user__is_active=True,
    ).exists()
    assert member_client.get(sibling_tasks_url).data["results"] == [sibling.data]
    assert outsider_client.get(private_tasks_url).data["results"] == [private.data]
