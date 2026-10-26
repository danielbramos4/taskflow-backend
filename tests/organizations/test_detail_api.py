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
    return django_user_model.objects.create_user(username="detail-user")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="detail-other-user")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.fixture
def organization(other_user):
    organization = Organization.objects.create(name="Original", slug="original")
    Membership.objects.create(
        organization=organization, user=other_user, role=Membership.Role.OWNER
    )
    return organization


@pytest.fixture
def membership(user, organization):
    return Membership.objects.create(
        organization=organization, user=user, role=Membership.Role.OWNER
    )


@pytest.fixture
def url(organization):
    return reverse(
        "organizations:organization-detail",
        kwargs={"organization_id": organization.pk},
    )


def assert_unchanged(organization):
    original = (organization.name, organization.slug, organization.updated_at)
    organization.refresh_from_db()
    assert (organization.name, organization.slug, organization.updated_at) == original


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_detail_requires_valid_authentication(url, organization, method, token):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = getattr(client, method)(url, {"name": "Attempt"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert_unchanged(organization)


@pytest.mark.parametrize("role", Membership.Role.values)
def test_participant_can_read_organization(
    api_client, membership, organization, url, role
):
    membership.role = role
    membership.save(update_fields=["role"])

    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert set(response.data) == {
        "id",
        "name",
        "slug",
        "my_role",
        "created_at",
        "updated_at",
    }
    assert response.data["id"] == organization.pk
    assert response.data["name"] == "Original"
    assert response.data["slug"] == "original"
    assert response.data["my_role"] == role
    assert_unchanged(organization)


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_cannot_distinguish_existing_and_missing_organization(
    api_client, user, url, organization, method, superuser
):
    user.is_staff = superuser
    user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    missing_url = reverse(
        "organizations:organization-detail",
        kwargs={"organization_id": organization.pk + 1000},
    )

    existing = getattr(api_client, method)(url, {"name": "Attempt"}, format="json")
    missing = getattr(api_client, method)(
        missing_url, {"name": "Attempt"}, format="json"
    )

    assert existing.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert existing.data == missing.data
    assert_unchanged(organization)


@pytest.mark.parametrize("method", ["get", "patch"])
def test_owner_also_receives_404_for_missing_id(api_client, membership, method):
    url = reverse(
        "organizations:organization-detail",
        kwargs={"organization_id": membership.organization_id + 1000},
    )

    response = getattr(api_client, method)(url, {"name": "Attempt"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Renamed"},
        {"slug": "renamed"},
        {"name": "Renamed", "slug": "renamed"},
        {},
    ],
)
def test_owner_can_patch_only_supplied_fields(
    api_client, membership, organization, url, payload
):
    created_at = organization.created_at
    updated_at = organization.updated_at

    response = api_client.patch(url, payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    organization.refresh_from_db()
    assert organization.name == payload.get("name", "Original")
    assert organization.slug == payload.get("slug", "original")
    assert organization.created_at == created_at
    if payload:
        assert organization.updated_at > updated_at
    else:
        assert organization.updated_at == updated_at
    assert response.data["my_role"] == Membership.Role.OWNER
    assert response.data["name"] == organization.name
    assert response.data["slug"] == organization.slug
    assert api_client.get(url).data == response.data
    assert Membership.objects.filter(organization=organization).count() == 2
    membership.refresh_from_db()
    assert membership.role == Membership.Role.OWNER


def test_owner_in_one_organization_cannot_edit_another_as_member(
    api_client, user, membership, organization, url
):
    other_organization = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(
        organization=other_organization, user=user, role=Membership.Role.MEMBER
    )
    other_url = reverse(
        "organizations:organization-detail",
        kwargs={"organization_id": other_organization.pk},
    )

    assert api_client.patch(url, {"name": "Owned"}, format="json").status_code == 200
    assert api_client.get(other_url).data["my_role"] == Membership.Role.MEMBER
    response = api_client.patch(other_url, {"name": "Attempt"}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    other_organization.refresh_from_db()
    assert other_organization.name == "Other"
    organization.refresh_from_db()
    assert organization.name == "Owned"


def test_member_cannot_spoof_owner_identity_or_role(
    api_client, membership, organization, other_user, url
):
    membership.role = Membership.Role.MEMBER
    membership.save(update_fields=["role"])

    response = api_client.patch(
        url + f"?user_id={other_user.pk}&my_role=owner",
        {"name": "Attempt", "user_id": other_user.pk, "my_role": "owner"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert_unchanged(organization)
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER


def test_query_parameters_do_not_select_another_organization_or_user(
    api_client, user, membership, organization, other_user, url
):
    hidden = Organization.objects.create(name="Hidden", slug="hidden")
    Membership.objects.create(
        organization=hidden, user=other_user, role=Membership.Role.OWNER
    )

    response = api_client.patch(
        url + f"?organization_id={hidden.pk}&user_id={other_user.pk}",
        {"name": "Renamed"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == organization.pk
    hidden.refresh_from_db()
    assert hidden.name == "Hidden"
    assert not Membership.objects.filter(user=user, organization=hidden).exists()


@pytest.mark.parametrize(
    "payload, error_field",
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": None}, "name"),
        ({"name": "x" * 151}, "name"),
        ({"slug": ""}, "slug"),
        ({"slug": None}, "slug"),
        ({"slug": "invalid slug!"}, "slug"),
        ({"slug": "x" * 161}, "slug"),
    ],
)
def test_invalid_patch_does_not_change_organization(
    api_client, membership, organization, url, payload, error_field
):
    response = api_client.patch(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert error_field in response.data
    assert_unchanged(organization)


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
def test_patch_rejects_unknown_and_server_controlled_fields(
    api_client, membership, organization, url, field, value
):
    response = api_client.patch(url, {"name": "Attempt", field: value}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data
    assert_unchanged(organization)
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize("payload", [[], "invalid", 123])
def test_patch_rejects_non_object_json(
    api_client, membership, organization, url, payload
):
    response = api_client.patch(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert_unchanged(organization)


def test_duplicate_slug_patch_rolls_back_all_fields(
    api_client, membership, organization, url
):
    hidden = Organization.objects.create(name="Hidden", slug="hidden")

    response = api_client.patch(
        url, {"name": "Attempt", "slug": "hidden"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "slug" in response.data
    assert_unchanged(organization)
    assert_unchanged(hidden)


def test_patch_accepts_unchanged_slug(api_client, membership, organization, url):
    response = api_client.patch(url, {"slug": organization.slug}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["slug"] == organization.slug


def test_slug_claimed_after_update_validation_returns_400(organization):
    serializer = OrganizationSerializer(
        organization, data={"name": "Attempt", "slug": "claimed"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    Organization.objects.create(name="Winner", slug="claimed")

    with pytest.raises(serializers.ValidationError) as error:
        serializer.save()

    assert "slug" in error.value.detail
    organization.refresh_from_db()
    assert organization.name == "Original"
    assert organization.slug == "original"


def test_partial_update_preserves_concurrent_change_to_unsupplied_field(organization):
    serializer = OrganizationSerializer(
        organization, data={"slug": "renamed"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    Organization.objects.filter(pk=organization.pk).update(name="Concurrent name")

    serializer.save()

    organization.refresh_from_db()
    assert organization.name == "Concurrent name"
    assert organization.slug == "renamed"


def test_update_integrity_failure_has_generic_error_and_no_changes(
    api_client, membership, organization, url
):
    with patch(
        "apps.organizations.serializers.Organization.save",
        side_effect=IntegrityError("simulated SQL failure"),
    ):
        response = api_client.patch(url, {"name": "Attempt"}, format="json")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert str(response.data["detail"]) == "Não foi possível atualizar a organização."
    assert "simulated SQL failure" not in response.content.decode()
    assert_unchanged(organization)


def test_detail_rechecks_role_and_membership_with_same_jwt(
    api_client, membership, organization, url
):
    assert api_client.get(url).data["my_role"] == Membership.Role.OWNER
    membership.role = Membership.Role.MEMBER
    membership.save(update_fields=["role"])

    assert api_client.get(url).data["my_role"] == Membership.Role.MEMBER
    assert api_client.patch(url, {"name": "Attempt"}).status_code == 403
    membership.delete()

    assert api_client.get(url).status_code == status.HTTP_404_NOT_FOUND
    assert api_client.patch(url, {"name": "Attempt"}).status_code == 404
    assert_unchanged(organization)


@pytest.mark.parametrize("method", ["put", "post", "delete"])
def test_detail_does_not_offer_other_write_methods(
    api_client, membership, organization, url, method
):
    response = getattr(api_client, method)(url, {"name": "Attempt"}, format="json")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert_unchanged(organization)
