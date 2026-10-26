from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.projects.serializers import ProjectSerializer

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


def snapshot(project):
    return (
        project.name,
        project.description,
        project.organization_id,
        project.created_by_id,
        project.is_archived,
        project.created_at,
        project.updated_at,
    )


def assert_unchanged(project):
    before = snapshot(project)
    project.refresh_from_db()
    assert snapshot(project) == before


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_detail_requires_valid_jwt(detail_url, project, method, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = getattr(client, method)(detail_url, {"name": "Attempt"}, format="json")

    assert response.status_code == 401
    assert_unchanged(project)


@pytest.mark.parametrize("role", ["owner", "member"])
@pytest.mark.parametrize("archived", [False, True])
def test_participants_read_active_and_archived_projects(
    client_for, owner, member, membership, project, detail_url, role, archived
):
    project.is_archived = archived
    project.save(update_fields=["is_archived"])
    client = client_for(owner if role == "owner" else member)

    response = client.get(detail_url)

    assert response.status_code == 200
    assert set(response.data) == {
        "id",
        "organization_id",
        "name",
        "description",
        "is_archived",
        "created_by_id",
        "created_at",
        "updated_at",
    }
    assert response.data["id"] == project.pk
    assert response.data["organization_id"] == project.organization_id
    assert response.data["created_by_id"] == owner.pk
    assert response.data["is_archived"] is archived
    assert response.data["name"] == "Original"
    assert_unchanged(project)


def test_details_support_null_historical_author(api_client, project, detail_url):
    Project.objects.filter(pk=project.pk).update(created_by=None)

    response = api_client.get(detail_url)

    assert response.status_code == 200
    assert response.data["created_by_id"] is None


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_cannot_distinguish_existing_and_missing_project(
    client_for, outsider, project, detail_url, method, superuser
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

    existing_response = getattr(client, method)(
        detail_url, {"name": "Attempt"}, format="json"
    )
    missing_response = getattr(client, method)(
        missing, {"name": "Attempt"}, format="json"
    )

    assert existing_response.status_code == missing_response.status_code == 404
    assert existing_response.data == missing_response.data
    assert_unchanged(project)


@pytest.mark.parametrize("method", ["get", "patch"])
def test_owner_receives_404_for_missing_organization_or_project(
    api_client, project, method
):
    paths = [
        {"organization_id": project.organization_id + 1000, "project_id": project.pk},
        {"organization_id": project.organization_id, "project_id": project.pk + 1000},
    ]
    for kwargs in paths:
        response = getattr(api_client, method)(
            reverse("projects:project-detail", kwargs=kwargs),
            {"name": "Attempt"},
            format="json",
        )
        assert response.status_code == 404
    assert_unchanged(project)


@pytest.mark.parametrize("method", ["get", "patch"])
def test_project_lookup_stays_inside_parent_even_for_owner_of_both(
    api_client, owner, organization, project, detail_url, method
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=owner, role="owner")
    external = Project.objects.create(
        organization=other, created_by=owner, name="External"
    )
    wrong_parent = reverse(
        "projects:project-detail",
        kwargs={"organization_id": organization.pk, "project_id": external.pk},
    )

    response = getattr(api_client, method)(
        wrong_parent, {"name": "Attempt"}, format="json"
    )

    assert response.status_code == 404
    assert_unchanged(external)
    assert_unchanged(project)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Renamed"},
        {"description": "Changed"},
        {"description": ""},
        {"name": "Renamed", "description": "Changed"},
        {},
    ],
)
def test_owner_patch_preserves_unsupplied_and_server_fields(
    api_client, project, detail_url, payload
):
    original = snapshot(project)

    response = api_client.patch(detail_url, payload, format="json")

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == payload.get("name", "Original")
    assert project.description == payload.get("description", "Original description")
    assert snapshot(project)[2:-1] == original[2:-1]
    if payload:
        assert project.updated_at > original[-1]
    else:
        assert project.updated_at == original[-1]
    assert response.data["name"] == project.name
    assert response.data["description"] == project.description
    assert api_client.get(detail_url).data == response.data


def test_owner_can_edit_archived_project_without_changing_archive_flag(
    api_client, project, detail_url
):
    project.is_archived = True
    project.save(update_fields=["is_archived"])

    response = api_client.patch(
        detail_url, {"description": "Edited history"}, format="json"
    )

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.is_archived is True
    assert project.description == "Edited history"


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": None}, "name"),
        ({"name": "x" * 151}, "name"),
        ({"description": None}, "description"),
        ({"description": "x" * 5001}, "description"),
    ],
)
def test_invalid_patch_changes_nothing(api_client, project, detail_url, payload, field):
    response = api_client.patch(detail_url, payload, format="json")

    assert response.status_code == 400
    assert field in response.data
    assert_unchanged(project)


def test_patch_accepts_name_and_description_at_field_limits(api_client, detail_url):
    response = api_client.patch(
        detail_url, {"name": "x" * 150, "description": "x" * 5000}, format="json"
    )

    assert response.status_code == 200
    assert len(response.data["name"]) == 150
    assert len(response.data["description"]) == 5000


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "organization",
        "organization_id",
        "created_by",
        "created_by_id",
        "created_at",
        "updated_at",
        "is_archived",
        "owner",
        "my_role",
        "unexpected",
    ],
)
def test_patch_rejects_identity_transfer_archive_and_unknown_fields(
    api_client, project, detail_url, field
):
    response = api_client.patch(
        detail_url, {"name": "Attempt", field: 999}, format="json"
    )

    assert response.status_code == 400
    assert field in response.data
    assert_unchanged(project)


@pytest.mark.parametrize("payload", [[], "invalid", 123])
def test_patch_requires_object_json(api_client, project, detail_url, payload):
    response = api_client.patch(detail_url, payload, format="json")

    assert response.status_code == 400
    assert_unchanged(project)


def test_member_cannot_spoof_owner_in_query_or_body(
    client_for, member, membership, owner, project, detail_url
):
    client = client_for(member)

    response = client.patch(
        detail_url + f"?user_id={owner.pk}&my_role=owner",
        {"name": "Attempt", "created_by_id": owner.pk, "my_role": "owner"},
        format="json",
    )

    assert response.status_code == 403
    assert_unchanged(project)
    membership.refresh_from_db()
    assert membership.role == "member"


def test_query_parameters_cannot_switch_project_organization_or_identity(
    api_client, owner, outsider, project, detail_url
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    external = Project.objects.create(
        organization=other, created_by=outsider, name="External"
    )

    response = api_client.patch(
        detail_url
        + f"?organization_id={other.pk}&project_id={external.pk}&user_id={outsider.pk}",
        {"name": "Renamed"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["id"] == project.pk
    assert response.data["organization_id"] == project.organization_id
    assert response.data["created_by_id"] == owner.pk
    assert_unchanged(external)


def test_owner_of_a_cannot_edit_b_as_member_even_if_author(
    api_client, owner, outsider, project, detail_url
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    Membership.objects.create(organization=other, user=owner, role="member")
    external = Project.objects.create(
        organization=other, created_by=owner, name="Historical authorship"
    )
    other_url = reverse(
        "projects:project-detail",
        kwargs={"organization_id": other.pk, "project_id": external.pk},
    )

    assert (
        api_client.patch(
            detail_url, {"name": "Owned update"}, format="json"
        ).status_code
        == 200
    )
    assert api_client.get(other_url).status_code == 200
    assert (
        api_client.patch(other_url, {"name": "Attempt"}, format="json").status_code
        == 403
    )
    assert_unchanged(external)


def test_author_loses_write_then_read_with_same_jwt_after_revocation(
    api_client, client_for, owner, outsider, project, detail_url, organization
):
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    manager = client_for(outsider)
    author_membership = Membership.objects.get(organization=organization, user=owner)
    membership_url = reverse(
        "organizations:membership-detail",
        kwargs={
            "organization_id": organization.pk,
            "membership_id": author_membership.pk,
        },
    )
    assert api_client.get(detail_url).status_code == 200

    assert (
        manager.patch(membership_url, {"role": "member"}, format="json").status_code
        == 200
    )
    assert api_client.get(detail_url).status_code == 200
    assert (
        api_client.patch(detail_url, {"name": "Attempt"}, format="json").status_code
        == 403
    )
    assert manager.delete(membership_url).status_code == 204

    assert api_client.get(detail_url).status_code == 404
    assert (
        api_client.patch(detail_url, {"name": "Attempt"}, format="json").status_code
        == 404
    )
    assert_unchanged(project)
    assert project.created_by_id == owner.pk


def test_promoted_member_can_edit_using_original_jwt(
    api_client, client_for, member, membership, project, detail_url
):
    client = client_for(member)
    assert (
        client.patch(detail_url, {"name": "Attempt"}, format="json").status_code == 403
    )
    membership_url = reverse(
        "organizations:membership-detail",
        kwargs={
            "organization_id": project.organization_id,
            "membership_id": membership.pk,
        },
    )
    assert (
        api_client.patch(membership_url, {"role": "owner"}, format="json").status_code
        == 200
    )

    response = client.patch(detail_url, {"name": "Promoted editor"}, format="json")

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == "Promoted editor"


def test_partial_update_does_not_overwrite_concurrent_change_to_unsupplied_field(
    project,
):
    serializer = ProjectSerializer(
        project, data={"description": "Edited description"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    Project.objects.filter(pk=project.pk).update(name="Concurrent name")

    serializer.save()

    project.refresh_from_db()
    assert project.name == "Concurrent name"
    assert project.description == "Edited description"


def test_update_integrity_failure_is_generic_and_rolls_back(
    api_client, project, detail_url
):
    with patch(
        "apps.projects.serializers.Project.save",
        side_effect=IntegrityError("simulated private SQL failure"),
    ):
        response = api_client.patch(detail_url, {"name": "Attempt"}, format="json")

    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível atualizar o projeto."
    assert "simulated private SQL failure" not in response.content.decode()
    assert_unchanged(project)


@pytest.mark.parametrize("method", ["put", "post", "delete"])
def test_detail_does_not_offer_other_write_methods(
    api_client, project, detail_url, method
):
    response = getattr(api_client, method)(
        detail_url, {"name": "Attempt"}, format="json"
    )

    assert response.status_code == 405
    assert_unchanged(project)
