import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, owner):
    return Project.objects.create(
        organization=organization,
        created_by=owner,
        name="Original",
        description="Original description",
    )


@pytest.fixture
def detail_url(project):
    return reverse(
        "projects:project-detail",
        kwargs={"organization_id": project.organization_id, "project_id": project.pk},
    )


def identity_and_content(project):
    return (
        project.pk,
        project.organization_id,
        project.created_by_id,
        project.name,
        project.description,
        project.created_at,
    )


def assert_unchanged(project):
    before = (identity_and_content(project), project.is_archived, project.updated_at)
    project.refresh_from_db()
    assert (
        identity_and_content(project),
        project.is_archived,
        project.updated_at,
    ) == before


@pytest.mark.parametrize("archived", [True, False])
def test_owner_changes_archive_flag_preserving_records_and_external_projects(
    api_client, owner, outsider, organization, membership, project, detail_url, archived
):
    project.is_archived = not archived
    project.save(update_fields=["is_archived"])
    before = identity_and_content(project)
    previous_updated_at = project.updated_at
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    external = Project.objects.create(
        organization=other, created_by=outsider, name="External"
    )
    counts = [
        model.objects.count()
        for model in [owner.__class__, Organization, Membership, Project]
    ]

    response = api_client.patch(detail_url, {"is_archived": archived}, format="json")

    assert response.status_code == 200
    assert response.data["is_archived"] is archived
    project.refresh_from_db()
    assert project.is_archived is archived
    assert identity_and_content(project) == before
    assert project.updated_at > previous_updated_at
    assert [
        model.objects.count()
        for model in [owner.__class__, Organization, Membership, Project]
    ] == counts
    assert_unchanged(external)
    membership.refresh_from_db()
    assert membership.role == "member"


def test_archived_project_remains_readable_editable_and_restorable(
    api_client, client_for, member, membership, project, detail_url, url, organization
):
    active = Project.objects.create(organization=organization, name="Active sibling")
    assert (
        api_client.patch(detail_url, {"is_archived": True}, format="json").status_code
        == 200
    )
    reader = client_for(member)

    details = reader.get(detail_url)
    collection = reader.get(url)

    assert details.status_code == 200 and details.data["is_archived"] is True
    assert collection.data["count"] == 2
    assert {row["id"] for row in collection.data["results"]} == {project.pk, active.pk}
    archived_row = next(
        row for row in collection.data["results"] if row["id"] == project.pk
    )
    assert archived_row["is_archived"] is True
    edited = api_client.patch(
        detail_url, {"name": "Edited while archived"}, format="json"
    )
    assert edited.status_code == 200 and edited.data["is_archived"] is True
    assert (
        reader.patch(detail_url, {"description": "Attempt"}, format="json").status_code
        == 403
    )
    assert api_client.delete(detail_url).status_code == 405

    restored = api_client.patch(detail_url, {"is_archived": False}, format="json")

    assert restored.status_code == 200
    assert restored.data["is_archived"] is False
    project.refresh_from_db()
    assert project.name == "Edited while archived"
    assert project.description == "Original description"
    assert reader.get(detail_url).data["is_archived"] is False
    assert Project.objects.count() == 2


def test_archive_flag_can_be_combined_with_content_in_one_patch(
    api_client, project, detail_url
):
    response = api_client.patch(
        detail_url,
        {"name": "Renamed", "description": "Revised description", "is_archived": True},
        format="json",
    )

    assert response.status_code == 200
    project.refresh_from_db()
    assert (project.name, project.description, project.is_archived) == (
        "Renamed",
        "Revised description",
        True,
    )


def test_repeating_archive_and_restore_does_not_duplicate_or_delete_project(
    api_client, project, detail_url
):
    before = identity_and_content(project)
    for archived in [True, True, False, False]:
        response = api_client.patch(
            detail_url, {"is_archived": archived}, format="json"
        )
        assert response.status_code == 200
        assert response.data["id"] == project.pk
        assert response.data["is_archived"] is archived
        assert Project.objects.count() == 1
    project.refresh_from_db()
    assert identity_and_content(project) == before


@pytest.mark.parametrize(
    "value",
    [None, "true", "false", "TRUE", "1", "0", "", 1, 0, 1.0, 0.0, -1, [], {}, 999],
)
def test_archive_requires_actual_json_boolean_and_rolls_back_other_fields(
    api_client, project, detail_url, value
):
    response = api_client.patch(
        detail_url, {"name": "Attempt", "is_archived": value}, format="json"
    )

    assert response.status_code == 400
    assert "is_archived" in response.data
    assert_unchanged(project)


@pytest.mark.parametrize("archived", [True, False])
def test_post_cannot_choose_archive_flag_even_when_false(api_client, url, archived):
    response = api_client.post(
        url, {"name": "Attempt", "is_archived": archived}, format="json"
    )

    assert response.status_code == 400
    assert "is_archived" in response.data
    assert not Project.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"description": None},
        {"name": "x" * 151},
        {"organization_id": 999},
        {"created_by_id": 999},
        {"unexpected": "value"},
    ],
)
def test_invalid_companion_field_prevents_archiving(
    api_client, project, detail_url, payload
):
    response = api_client.patch(
        detail_url, {"is_archived": True, **payload}, format="json"
    )

    assert response.status_code == 400
    assert_unchanged(project)


@pytest.mark.parametrize("archived", [True, False])
def test_member_cannot_archive_or_restore(
    client_for, member, membership, project, detail_url, archived
):
    project.is_archived = not archived
    project.save(update_fields=["is_archived"])

    response = client_for(member).patch(
        detail_url, {"is_archived": archived}, format="json"
    )

    assert response.status_code == 403
    assert_unchanged(project)


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_archive_requires_valid_jwt(project, detail_url, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.patch(detail_url, {"is_archived": True}, format="json")

    assert response.status_code == 401
    assert_unchanged(project)


@pytest.mark.parametrize("archived", [True, False])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_gets_same_404_for_existing_and_missing_project(
    client_for, outsider, project, detail_url, archived, superuser
):
    outsider.is_staff = superuser
    outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    client = client_for(outsider)
    missing = reverse(
        "projects:project-detail",
        kwargs={
            "organization_id": project.organization_id,
            "project_id": project.pk + 1000,
        },
    )

    existing_response = client.patch(
        detail_url, {"is_archived": archived}, format="json"
    )
    missing_response = client.patch(missing, {"is_archived": archived}, format="json")

    assert existing_response.status_code == missing_response.status_code == 404
    assert existing_response.data == missing_response.data
    assert_unchanged(project)


@pytest.mark.parametrize("archived", [True, False])
def test_archive_lookup_stays_inside_parent_for_owner_of_both(
    api_client, owner, organization, project, archived
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=owner, role="owner")
    external = Project.objects.create(
        organization=other, created_by=owner, name="External", is_archived=not archived
    )
    wrong_parent = reverse(
        "projects:project-detail",
        kwargs={"organization_id": organization.pk, "project_id": external.pk},
    )

    response = api_client.patch(wrong_parent, {"is_archived": archived}, format="json")

    assert response.status_code == 404
    assert_unchanged(external)
    assert_unchanged(project)


@pytest.mark.parametrize("archived", [True, False])
def test_owner_of_a_cannot_archive_b_as_member_even_if_author(
    api_client, owner, outsider, organization, archived
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    Membership.objects.create(organization=other, user=owner, role="member")
    external = Project.objects.create(
        organization=other,
        created_by=owner,
        name="Historical authorship",
        is_archived=not archived,
    )
    other_url = reverse(
        "projects:project-detail",
        kwargs={"organization_id": other.pk, "project_id": external.pk},
    )

    response = api_client.patch(other_url, {"is_archived": archived}, format="json")

    assert response.status_code == 403
    assert_unchanged(external)


def test_archive_authorization_changes_with_role_and_membership_using_same_jwt(
    api_client, client_for, member, membership, project, detail_url, organization
):
    client = client_for(member)
    membership_url = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )
    assert (
        client.patch(detail_url, {"is_archived": True}, format="json").status_code
        == 403
    )
    assert (
        api_client.patch(membership_url, {"role": "owner"}, format="json").status_code
        == 200
    )
    assert (
        client.patch(detail_url, {"is_archived": True}, format="json").status_code
        == 200
    )
    assert (
        api_client.patch(membership_url, {"role": "member"}, format="json").status_code
        == 200
    )
    assert (
        client.patch(detail_url, {"is_archived": False}, format="json").status_code
        == 403
    )
    assert api_client.delete(membership_url).status_code == 204

    assert (
        client.patch(detail_url, {"is_archived": False}, format="json").status_code
        == 404
    )
    project.refresh_from_db()
    assert project.is_archived is True
    assert Project.objects.filter(pk=project.pk).exists()
