from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization
from apps.organizations.serializers import OrganizationSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="organization-user")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="other-organization-user")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.fixture
def url():
    return reverse("organizations:organization-list")


@pytest.mark.parametrize("method", ["get", "post"])
def test_collection_requires_authentication(url, method):
    response = getattr(APIClient(), method)(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert not Organization.objects.exists()
    assert not Membership.objects.exists()


def test_invalid_token_is_rejected(url):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")

    response = client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_organization_assigns_request_user_as_owner(api_client, user, url):
    response = api_client.post(
        url, {"name": "Equipe Exemplo", "slug": "equipe-exemplo"}, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert set(response.data) == {
        "id",
        "name",
        "slug",
        "my_role",
        "created_at",
        "updated_at",
    }
    assert response.data["my_role"] == Membership.Role.OWNER
    organization = Organization.objects.get(pk=response.data["id"])
    assert organization.name == "Equipe Exemplo"
    assert organization.slug == "equipe-exemplo"
    membership = Membership.objects.get(organization=organization)
    assert membership.user_id == user.pk
    assert membership.role == Membership.Role.OWNER
    assert Organization.objects.count() == 1
    assert Membership.objects.count() == 1

    listing = api_client.get(url)
    assert listing.data["count"] == 1
    assert listing.data["results"][0] == response.data


@pytest.mark.parametrize(
    "payload, error_field",
    [
        ({"slug": "valid-slug"}, "name"),
        ({"name": "", "slug": "valid-slug"}, "name"),
        ({"name": "   ", "slug": "valid-slug"}, "name"),
        ({"name": None, "slug": "valid-slug"}, "name"),
        ({"name": "x" * 151, "slug": "valid-slug"}, "name"),
        ({"name": "Valid name"}, "slug"),
        ({"name": "Valid name", "slug": ""}, "slug"),
        ({"name": "Valid name", "slug": None}, "slug"),
        ({"name": "Valid name", "slug": "invalid slug!"}, "slug"),
        ({"name": "Valid name", "slug": "x" * 161}, "slug"),
    ],
)
def test_create_rejects_invalid_fields(api_client, url, payload, error_field):
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert error_field in response.data
    assert not Organization.objects.exists()
    assert not Membership.objects.exists()


@pytest.mark.parametrize(
    "field, value",
    [
        ("owner", 999),
        ("user_id", 999),
        ("role", "owner"),
        ("my_role", "owner"),
        ("id", 999),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("updated_at", "2026-01-01T00:00:00Z"),
        ("unexpected", "value"),
    ],
)
def test_create_rejects_unknown_and_server_controlled_fields(
    api_client, url, field, value
):
    response = api_client.post(
        url, {"name": "Equipe", "slug": "equipe", field: value}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data
    assert not Organization.objects.exists()
    assert not Membership.objects.exists()


@pytest.mark.parametrize("payload", [[], "invalid", 123])
def test_create_rejects_non_object_json(api_client, url, payload):
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not Organization.objects.exists()


def test_duplicate_slug_does_not_modify_existing_organization(
    api_client, other_user, url
):
    organization = Organization.objects.create(name="Original", slug="existing")
    membership = Membership.objects.create(
        organization=organization, user=other_user, role=Membership.Role.OWNER
    )

    response = api_client.post(
        url, {"name": "New name", "slug": "existing"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "slug" in response.data
    assert Organization.objects.count() == 1
    assert Membership.objects.count() == 1
    organization.refresh_from_db()
    membership.refresh_from_db()
    assert organization.name == "Original"
    assert membership.user_id == other_user.pk


def test_slug_taken_after_validation_returns_validation_error(user, other_user):
    serializer = OrganizationSerializer(
        data={"name": "Candidate", "slug": "claimed"},
        context={"request": SimpleNamespace(user=user)},
    )
    assert serializer.is_valid(), serializer.errors
    winner = Organization.objects.create(name="Winner", slug="claimed")
    Membership.objects.create(
        organization=winner, user=other_user, role=Membership.Role.OWNER
    )

    with pytest.raises(serializers.ValidationError) as error:
        serializer.save()

    assert "slug" in error.value.detail
    assert list(Organization.objects.values_list("id", flat=True)) == [winner.pk]
    assert Membership.objects.count() == 1
    assert Membership.objects.get().user_id == other_user.pk


def test_membership_failure_rolls_back_organization(api_client, url):
    with patch(
        "apps.organizations.serializers.Membership.objects.create",
        side_effect=IntegrityError("simulated membership failure"),
    ):
        response = api_client.post(
            url, {"name": "Will roll back", "slug": "rollback"}, format="json"
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert str(response.data["detail"]) == "Não foi possível criar a organização."
    assert "simulated membership failure" not in response.content.decode()
    assert not Organization.objects.exists()
    assert not Membership.objects.exists()


def test_list_is_empty_without_membership(api_client, other_user, url):
    organization = Organization.objects.create(name="Private", slug="private")
    Membership.objects.create(
        organization=organization, user=other_user, role=Membership.Role.OWNER
    )

    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"count": 0, "next": None, "previous": None, "results": []}


def test_list_only_contains_own_organizations_and_own_roles(
    api_client, user, other_user, url
):
    owned = Organization.objects.create(name="Zulu", slug="owned")
    shared = Organization.objects.create(name="Alpha", slug="shared")
    hidden = Organization.objects.create(name="Hidden", slug="hidden")
    Membership.objects.create(organization=owned, user=user, role=Membership.Role.OWNER)
    Membership.objects.create(
        organization=shared, user=user, role=Membership.Role.MEMBER
    )
    Membership.objects.create(
        organization=shared, user=other_user, role=Membership.Role.OWNER
    )
    Membership.objects.create(
        organization=hidden, user=other_user, role=Membership.Role.OWNER
    )

    response = api_client.get(
        url, {"user_id": other_user.pk, "organization_id": hidden.pk}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    results = response.data["results"]
    assert [(item["id"], item["my_role"]) for item in results] == [
        (shared.pk, Membership.Role.MEMBER),
        (owned.pk, Membership.Role.OWNER),
    ]
    assert all(
        set(item) == {"id", "name", "slug", "my_role", "created_at", "updated_at"}
        for item in results
    )


def test_superuser_does_not_bypass_membership_filter(api_client, user, other_user, url):
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    organization = Organization.objects.create(name="Private", slug="private")
    Membership.objects.create(
        organization=organization, user=other_user, role=Membership.Role.OWNER
    )

    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response.data["results"] == []


def test_list_rechecks_membership_with_same_jwt(api_client, user, url):
    organization = Organization.objects.create(name="Team", slug="team")
    membership = Membership.objects.create(
        organization=organization, user=user, role=Membership.Role.MEMBER
    )
    assert api_client.get(url).data["count"] == 1

    membership.delete()

    assert api_client.get(url).data["count"] == 0


def test_pagination_is_stable_and_count_excludes_other_organizations(
    api_client, user, other_user, url
):
    organizations = Organization.objects.bulk_create(
        [Organization(name="Same name", slug=f"team-{i:02}") for i in range(21)]
    )
    Membership.objects.bulk_create(
        [
            Membership(organization=organization, user=user)
            for organization in organizations
        ]
    )
    hidden = Organization.objects.create(name="AAAA Hidden", slug="hidden")
    Membership.objects.create(organization=hidden, user=other_user)

    first_page = api_client.get(url, {"page_size": 100})
    second_page = api_client.get(url, {"page": 2})

    assert first_page.status_code == status.HTTP_200_OK
    assert first_page.data["count"] == 21
    assert len(first_page.data["results"]) == 20
    assert first_page.data["next"] is not None
    assert first_page.data["previous"] is None
    assert [item["id"] for item in first_page.data["results"]] == [
        organization.pk for organization in organizations[:20]
    ]
    assert second_page.status_code == status.HTTP_200_OK
    assert second_page.data["next"] is None
    assert second_page.data["previous"] is not None
    assert [item["id"] for item in second_page.data["results"]] == [
        organizations[20].pk
    ]


@pytest.mark.parametrize("page", ["invalid", "0", "2"])
def test_invalid_or_out_of_range_page_returns_404(api_client, url, page):
    response = api_client.get(url, {"page": page})

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_collection_does_not_allow_other_write_methods(api_client, url, method):
    response = getattr(api_client, method)(url, {}, format="json")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert not Organization.objects.exists()
