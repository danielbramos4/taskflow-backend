import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

pytestmark = pytest.mark.django_db

TEST_PASSWORD = "sprint3-acceptance-test-only-password"


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


def test_sprint3_complete_flow_preserves_projects_isolation_and_auth(django_user_model):
    creator, teammate, outsider = [
        django_user_model.objects.create_user(username=username, password=TEST_PASSWORD)
        for username in [
            "project-flow-owner",
            "project-flow-member",
            "project-flow-outsider",
        ]
    ]
    owner_client, owner_tokens = authenticated_client(creator)
    member_client, _ = authenticated_client(teammate)
    outsider_client, _ = authenticated_client(outsider)
    organizations_url = reverse("organizations:organization-list")
    organization = owner_client.post(
        organizations_url,
        {"name": "Project team", "slug": "project-team"},
        format="json",
    )
    external = outsider_client.post(
        organizations_url,
        {"name": "Private team", "slug": "private-team"},
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
    private_project = outsider_client.post(
        external_projects_url, {"name": "Private project"}, format="json"
    )
    created = owner_client.post(
        projects_url,
        {"name": "First project", "description": "Initial scope"},
        format="json",
    )
    assert created.status_code == private_project.status_code == 201
    project_id = created.data["id"]
    assert created.data["organization_id"] == organization_id
    assert created.data["created_by_id"] == creator.pk
    assert created.data["is_archived"] is False
    project_url = reverse(
        "projects:project-detail",
        kwargs={"organization_id": organization_id, "project_id": project_id},
    )
    wrong_parent_url = reverse(
        "projects:project-detail",
        kwargs={
            "organization_id": organization_id,
            "project_id": private_project.data["id"],
        },
    )
    assert owner_client.get(wrong_parent_url).status_code == 404
    assert owner_client.get(external_projects_url).status_code == 404
    assert outsider_client.get(projects_url).status_code == 404
    assert outsider_client.get(project_url).status_code == 404

    memberships_url = reverse(
        "organizations:membership-list", kwargs={"organization_id": organization_id}
    )
    own_membership = Membership.objects.get(
        organization_id=organization_id, user=creator
    )
    own_membership_url = f"{memberships_url}{own_membership.pk}/"
    added = owner_client.post(memberships_url, {"user_id": teammate.pk}, format="json")
    assert added.status_code == 201 and added.data["role"] == "member"
    teammate_membership_url = f"{memberships_url}{added.data['id']}/"
    listing = member_client.get(projects_url)
    assert listing.status_code == 200 and listing.data["count"] == 1
    assert [row["id"] for row in listing.data["results"]] == [project_id]
    assert member_client.get(project_url).data["description"] == "Initial scope"
    assert (
        member_client.post(
            projects_url, {"name": "Forbidden"}, format="json"
        ).status_code
        == 403
    )
    for patch in [{"name": "Forbidden"}, {"is_archived": True}, {"is_archived": False}]:
        assert member_client.patch(project_url, patch, format="json").status_code == 403

    edited = owner_client.patch(
        project_url, {"name": "Reviewed project"}, format="json"
    )
    assert edited.status_code == 200 and edited.data["description"] == "Initial scope"
    archived = owner_client.patch(project_url, {"is_archived": True}, format="json")
    assert archived.status_code == 200 and archived.data["is_archived"] is True
    assert member_client.get(project_url).data["is_archived"] is True
    assert member_client.get(projects_url).data["results"][0]["is_archived"] is True
    edited_archive = owner_client.patch(
        project_url, {"description": "Accepted scope"}, format="json"
    )
    assert (
        edited_archive.status_code == 200 and edited_archive.data["is_archived"] is True
    )
    restored = owner_client.patch(project_url, {"is_archived": False}, format="json")
    assert restored.status_code == 200 and restored.data["is_archived"] is False
    assert restored.data["description"] == "Accepted scope"

    # Existing JWTs observe role changes and membership removal immediately.
    promoted = owner_client.patch(
        teammate_membership_url, {"role": "owner"}, format="json"
    )
    assert promoted.status_code == 200
    for archived_value in [True, False]:
        result = member_client.patch(
            project_url, {"is_archived": archived_value}, format="json"
        )
        assert (
            result.status_code == 200 and result.data["is_archived"] is archived_value
        )
    demoted = member_client.patch(own_membership_url, {"role": "member"}, format="json")
    assert demoted.status_code == 200
    assert owner_client.get(project_url).status_code == 200
    assert (
        owner_client.patch(
            project_url, {"name": "Forbidden"}, format="json"
        ).status_code
        == 403
    )
    assert (
        owner_client.patch(
            project_url, {"is_archived": True}, format="json"
        ).status_code
        == 403
    )
    assert member_client.delete(own_membership_url).status_code == 204
    assert owner_client.get(project_url).status_code == 404
    assert owner_client.get(projects_url).status_code == 404

    refreshed = APIClient().post(
        reverse("token_refresh"), {"refresh": owner_tokens["refresh"]}, format="json"
    )
    assert refreshed.status_code == 200
    owner_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
    assert owner_client.get(reverse("current_user")).data["id"] == creator.pk
    assert owner_client.get(project_url).status_code == 404
    assert owner_client.get(projects_url).status_code == 404
    project = Project.objects.get(pk=project_id)
    assert (project.name, project.description, project.is_archived) == (
        "Reviewed project",
        "Accepted scope",
        False,
    )
    assert (
        project.organization_id == organization_id
        and project.created_by_id == creator.pk
    )
    assert (
        project.created_at.isoformat().replace("+00:00", "Z")
        == created.data["created_at"]
    )
    assert Project.objects.count() == 2
    assert django_user_model.objects.count() == 3
    assert Organization.objects.count() == 2
    assert Membership.objects.count() == 2
    assert Membership.objects.filter(
        organization_id=organization_id, user=teammate, role="owner"
    ).exists()
    external_listing = outsider_client.get(external_projects_url)
    assert external_listing.status_code == 200
    assert external_listing.data["results"] == [private_project.data]
