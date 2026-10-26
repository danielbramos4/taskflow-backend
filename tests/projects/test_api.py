from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_collection_requires_valid_jwt(url, method, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = getattr(client, method)(url, {"name": "Attempt"}, format="json")

    assert response.status_code == 401
    assert not Project.objects.exists()


@pytest.mark.parametrize("description", [None, "Description"])
def test_owner_creates_project_with_server_identity(
    api_client, organization, owner, url, description
):
    payload = {"name": "  New project  "}
    if description is not None:
        payload["description"] = description

    response = api_client.post(url, payload, format="json")

    assert response.status_code == 201
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
    project = Project.objects.get(pk=response.data["id"])
    assert project.organization_id == organization.pk
    assert project.created_by_id == owner.pk
    assert project.name == "New project"
    assert project.description == (description or "")
    assert project.is_archived is False
    assert response.data["created_by_id"] == owner.pk
    assert api_client.get(url).data["results"] == [response.data]


def test_member_reads_but_cannot_create(
    api_client, membership, client_for, member, organization, url
):
    created = api_client.post(url, {"name": "Visible"}, format="json")
    member_client = client_for(member)

    listing = member_client.get(url)
    denied = member_client.post(url, {"name": "Attempt"}, format="json")

    assert listing.status_code == 200
    assert listing.data["results"] == [created.data]
    assert denied.status_code == 403
    assert list(Project.objects.values_list("name", flat=True)) == ["Visible"]


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_gets_identical_404_for_existing_and_missing_org(
    client_for, outsider, organization, url, method, superuser
):
    outsider.is_staff = superuser
    outsider.is_superuser = superuser
    outsider.save(update_fields=["is_staff", "is_superuser"])
    client = client_for(outsider)
    missing = reverse(
        "projects:project-list", kwargs={"organization_id": organization.pk + 1000}
    )

    existing_response = getattr(client, method)(url, {"name": "Attempt"}, format="json")
    missing_response = getattr(client, method)(
        missing, {"name": "Attempt"}, format="json"
    )

    assert existing_response.status_code == missing_response.status_code == 404
    assert existing_response.data == missing_response.data
    assert not Project.objects.exists()


@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "  "}, "name"),
        ({"name": None}, "name"),
        ({"name": "x" * 151}, "name"),
        ({"name": "Valid", "description": None}, "description"),
        ({"name": "Valid", "description": "x" * 5001}, "description"),
    ],
)
def test_invalid_input_creates_no_project(api_client, url, payload, field):
    response = api_client.post(url, payload, format="json")

    assert response.status_code == 400
    assert field in response.data
    assert not Project.objects.exists()


def test_creation_accepts_field_limits(api_client, url):
    response = api_client.post(
        url, {"name": "x" * 150, "description": "x" * 5000}, format="json"
    )

    assert response.status_code == 201
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
        "is_archived",
        "created_at",
        "updated_at",
        "owner",
        "my_role",
        "unexpected",
    ],
)
def test_post_rejects_server_controlled_fields(api_client, url, field):
    response = api_client.post(url, {"name": "Attempt", field: 999}, format="json")

    assert response.status_code == 400
    assert field in response.data
    assert not Project.objects.exists()


@pytest.mark.parametrize("payload", [[], "invalid", 123])
def test_post_requires_object_json(api_client, url, payload):
    response = api_client.post(url, payload, format="json")

    assert response.status_code == 400
    assert not Project.objects.exists()


def test_projects_are_scoped_to_path_and_queries_do_not_change_identity(
    api_client, owner, outsider, organization, url
):
    other = Organization.objects.create(name="External", slug="external")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    hidden = Project.objects.create(
        organization=other, created_by=outsider, name="Hidden"
    )

    created = api_client.post(
        url + f"?organization_id={other.pk}&user_id={outsider.pk}",
        {"name": "Owned"},
        format="json",
    )
    listing = api_client.get(
        url, {"organization_id": other.pk, "created_by_id": outsider.pk}
    )

    assert created.status_code == 201
    assert created.data["organization_id"] == organization.pk
    assert created.data["created_by_id"] == owner.pk
    assert listing.data["count"] == 1
    assert [row["id"] for row in listing.data["results"]] == [created.data["id"]]
    assert Project.objects.get(pk=hidden.pk).organization_id == other.pk


def test_owner_of_a_cannot_create_in_b_as_member(
    api_client, owner, outsider, organization
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    Membership.objects.create(organization=other, user=owner, role="member")
    url = reverse("projects:project-list", kwargs={"organization_id": other.pk})

    assert api_client.get(url).status_code == 200
    response = api_client.post(url, {"name": "Attempt"}, format="json")

    assert response.status_code == 403
    assert not Project.objects.exists()


def test_role_revocation_overrides_authorship_with_same_jwt(
    api_client, owner, member, membership, client_for, organization, url
):
    membership.role = "owner"
    membership.save(update_fields=["role"])
    creator_client = client_for(member)
    created = creator_client.post(url, {"name": "Historical authorship"}, format="json")
    assert created.status_code == 201
    membership_url = reverse(
        "organizations:membership-detail",
        kwargs={"organization_id": organization.pk, "membership_id": membership.pk},
    )

    assert (
        api_client.patch(membership_url, {"role": "member"}, format="json").status_code
        == 200
    )
    assert creator_client.get(url).data["count"] == 1
    assert (
        creator_client.post(url, {"name": "Denied"}, format="json").status_code == 403
    )
    assert api_client.delete(membership_url).status_code == 204

    assert creator_client.get(url).status_code == 404
    assert (
        creator_client.post(url, {"name": "Denied"}, format="json").status_code == 404
    )
    project = Project.objects.get(pk=created.data["id"])
    assert project.created_by_id == member.pk
    assert project.name == "Historical authorship"


def test_empty_collection_and_pagination_are_scoped_and_stable(
    api_client, organization, owner, outsider, url
):
    assert api_client.get(url).data == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }
    projects = Project.objects.bulk_create(
        [
            Project(organization=organization, created_by=owner, name="Same")
            for _ in range(21)
        ]
    )
    other = Organization.objects.create(name="Other", slug="other")
    Project.objects.create(organization=other, created_by=outsider, name="AAA hidden")

    first = api_client.get(url, {"page_size": 100})
    second = api_client.get(url, {"page": 2})

    assert first.status_code == second.status_code == 200
    assert first.data["count"] == second.data["count"] == 21
    assert [row["id"] for row in first.data["results"]] == [
        row.pk for row in projects[:20]
    ]
    assert [row["id"] for row in second.data["results"]] == [projects[20].pk]
    assert first.data["previous"] is None and first.data["next"]
    assert second.data["previous"] and second.data["next"] is None


def test_list_includes_archived_and_null_author_without_private_user_fields(
    api_client, organization, url
):
    project = Project.objects.create(
        organization=organization, name="Historical", is_archived=True
    )

    response = api_client.get(url)

    assert response.status_code == 200
    assert response.data["results"][0]["id"] == project.pk
    assert response.data["results"][0]["is_archived"] is True
    assert response.data["results"][0]["created_by_id"] is None
    assert set(response.data["results"][0]) == {
        "id",
        "organization_id",
        "name",
        "description",
        "is_archived",
        "created_by_id",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize("page", ["invalid", "0", "2"])
def test_invalid_pages_return_404(api_client, url, page):
    assert api_client.get(url, {"page": page}).status_code == 404


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_collection_unsupported_methods(api_client, url, method):
    assert getattr(api_client, method)(url, {}, format="json").status_code == 405
    assert not Project.objects.exists()


def test_integrity_failure_is_generic_and_rolls_back(api_client, url):
    with patch(
        "apps.projects.serializers.Project.objects.create",
        side_effect=IntegrityError("simulated private SQL failure"),
    ):
        response = api_client.post(url, {"name": "Attempt"}, format="json")

    assert response.status_code == 500
    assert str(response.data["detail"]) == "Não foi possível criar o projeto."
    assert "simulated private SQL failure" not in response.content.decode()
    assert not Project.objects.exists()
