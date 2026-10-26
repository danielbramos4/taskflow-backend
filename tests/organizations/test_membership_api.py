from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization

pytestmark = pytest.mark.django_db


def collection_url(organization):
    return reverse(
        "organizations:membership-list", kwargs={"organization_id": organization.pk}
    )


def detail_url(membership, organization=None):
    return reverse(
        "organizations:membership-detail",
        kwargs={
            "organization_id": organization.pk
            if organization
            else membership.organization_id,
            "membership_id": membership.pk,
        },
    )


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="membership-owner")


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(username="membership-member")


@pytest.fixture
def candidate(django_user_model):
    return django_user_model.objects.create_user(username="membership-candidate")


@pytest.fixture
def organization(owner):
    organization = Organization.objects.create(name="Team", slug="team")
    Membership.objects.create(
        organization=organization, user=owner, role=Membership.Role.OWNER
    )
    return organization


@pytest.fixture
def membership(organization, member):
    return Membership.objects.create(organization=organization, user=member)


@pytest.fixture
def api_client(owner):
    return client_for(owner)


@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_membership_endpoints_require_valid_jwt(
    organization, membership, method, token
):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    url = (
        collection_url(organization)
        if method in {"get", "post"}
        else detail_url(membership)
    )

    response = getattr(client, method)(url, {}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize("requester", ["owner", "member"])
def test_participants_list_members_without_private_user_fields(
    owner, member, organization, membership, requester
):
    client = client_for(owner if requester == "owner" else member)

    response = client.get(collection_url(organization))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    assert [(row["user_id"], row["role"]) for row in response.data["results"]] == [
        (owner.pk, "owner"),
        (member.pk, "member"),
    ]
    for row in response.data["results"]:
        assert set(row) == {"id", "user_id", "username", "role", "created_at"}
    assert response.data["results"][1]["username"] == member.username


@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
@pytest.mark.parametrize("superuser", [False, True])
def test_outsider_and_superuser_cannot_discover_organization(
    candidate, organization, membership, method, superuser
):
    candidate.is_staff = superuser
    candidate.is_superuser = superuser
    candidate.save(update_fields=["is_staff", "is_superuser"])
    client = client_for(candidate)
    url = (
        collection_url(organization)
        if method in {"get", "post"}
        else detail_url(membership)
    )
    missing = url.replace(
        f"/organizations/{organization.pk}/",
        f"/organizations/{organization.pk + 1000}/",
    )

    existing_response = getattr(client, method)(url, {}, format="json")
    missing_response = getattr(client, method)(missing, {}, format="json")

    assert (
        existing_response.status_code
        == missing_response.status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert existing_response.data == missing_response.data
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_member_cannot_add_promote_or_remove_even_self(
    member, candidate, organization, membership, method
):
    client = client_for(member)
    url = collection_url(organization) if method == "post" else detail_url(membership)
    response = getattr(client, method)(
        url + "?my_role=owner",
        {"user_id": candidate.pk, "role": "owner"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize("role", [None, "member", "owner"])
def test_owner_adds_existing_active_user_with_default_or_explicit_role(
    api_client, candidate, organization, role
):
    payload = {"user_id": candidate.pk}
    if role is not None:
        payload["role"] = role

    response = api_client.post(collection_url(organization), payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert set(response.data) == {"id", "user_id", "username", "role", "created_at"}
    assert response.data["user_id"] == candidate.pk
    assert response.data["username"] == candidate.username
    assert response.data["role"] == (role or "member")
    assert (
        Membership.objects.get(pk=response.data["id"]).organization_id
        == organization.pk
    )
    assert candidate.__class__.objects.count() == 2


@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "user_id"),
        ({"user_id": None}, "user_id"),
        ({"user_id": "not-an-id"}, "user_id"),
        ({"user_id": True}, "user_id"),
        ({"user_id": 99999999}, "user_id"),
        ({"role": "admin"}, "role"),
        ({"role": ""}, "role"),
        ({"role": None}, "role"),
    ],
)
def test_create_rejects_invalid_user_or_role(
    api_client, candidate, organization, payload, field
):
    if field == "role":
        payload = {"user_id": candidate.pk, **payload}
    response = api_client.post(collection_url(organization), payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data
    assert Membership.objects.filter(organization=organization).count() == 1


def test_create_rejects_inactive_user(api_client, candidate, organization):
    candidate.is_active = False
    candidate.save(update_fields=["is_active"])

    response = api_client.post(
        collection_url(organization), {"user_id": candidate.pk}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "user_id" in response.data
    assert not Membership.objects.filter(user=candidate).exists()


def test_duplicate_inclusion_does_not_change_role(api_client, organization, membership):
    response = api_client.post(
        collection_url(organization),
        {"user_id": membership.user_id, "role": "owner"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "user_id" in response.data
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "username",
        "organization",
        "organization_id",
        "created_at",
        "my_role",
        "unexpected",
    ],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_mutations_reject_server_controlled_or_unknown_fields(
    api_client, candidate, organization, membership, method, field
):
    url = collection_url(organization) if method == "post" else detail_url(membership)
    payload = {"user_id": candidate.pk} if method == "post" else {"role": "owner"}
    payload[field] = 999

    response = getattr(api_client, method)(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER
    assert Membership.objects.filter(organization=organization).count() == 2


def test_patch_cannot_move_membership_to_another_user(
    api_client, candidate, membership
):
    response = api_client.patch(
        detail_url(membership),
        {"user_id": candidate.pk, "role": "owner"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "user_id" in response.data
    original_user = membership.user_id
    membership.refresh_from_db()
    assert membership.user_id == original_user
    assert membership.role == Membership.Role.MEMBER


@pytest.mark.parametrize("payload", [[], "invalid", 123])
@pytest.mark.parametrize("method", ["post", "patch"])
def test_mutations_require_object_json(
    api_client, organization, membership, method, payload
):
    url = collection_url(organization) if method == "post" else detail_url(membership)
    response = getattr(api_client, method)(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Membership.objects.filter(organization=organization).count() == 2


@pytest.mark.parametrize("role", ["admin", "", None])
def test_patch_rejects_invalid_role(api_client, membership, role):
    response = api_client.patch(detail_url(membership), {"role": role}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER


@pytest.mark.parametrize("payload", [{}, {"role": "member"}, {"role": "owner"}])
def test_owner_changes_only_role_or_keeps_current_role(api_client, membership, payload):
    before = (membership.user_id, membership.organization_id, membership.created_at)

    response = api_client.patch(detail_url(membership), payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    membership.refresh_from_db()
    assert (
        membership.user_id,
        membership.organization_id,
        membership.created_at,
    ) == before
    assert membership.role == payload.get("role", "member")
    assert response.data["role"] == membership.role


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.parametrize("inactive_other_owner", [False, True])
def test_last_active_owner_cannot_be_demoted_or_removed(
    api_client, owner, candidate, organization, method, inactive_other_owner
):
    own_membership = Membership.objects.get(user=owner, organization=organization)
    if inactive_other_owner:
        candidate.is_active = False
        candidate.save(update_fields=["is_active"])
        Membership.objects.create(
            organization=organization, user=candidate, role=Membership.Role.OWNER
        )

    response = getattr(api_client, method)(
        detail_url(own_membership), {"role": "member"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "role" in response.data
    own_membership.refresh_from_db()
    assert own_membership.role == Membership.Role.OWNER


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_owner_can_transfer_responsibility_and_leave_role(
    api_client, owner, member, organization, membership, method
):
    own_membership = Membership.objects.get(user=owner, organization=organization)
    promote = api_client.patch(detail_url(membership), {"role": "owner"}, format="json")
    assert promote.status_code == status.HTTP_200_OK

    response = getattr(api_client, method)(
        detail_url(own_membership), {"role": "member"}, format="json"
    )

    assert response.status_code == (200 if method == "patch" else 204)
    membership.refresh_from_db()
    assert membership.role == Membership.Role.OWNER
    assert organization.__class__.objects.filter(pk=organization.pk).exists()
    assert owner.__class__.objects.filter(pk__in=[owner.pk, member.pk]).count() == 2
    # The same token loses management rights on its next request.
    next_response = api_client.patch(
        detail_url(membership), {"role": "member"}, format="json"
    )
    assert next_response.status_code == (403 if method == "patch" else 404)


def test_deleting_member_preserves_accounts_organization_and_other_links(
    api_client, owner, member, organization, membership
):
    other = Organization.objects.create(name="Other", slug="other")
    other_membership = Membership.objects.create(
        organization=other, user=member, role=Membership.Role.OWNER
    )

    response = api_client.delete(detail_url(membership))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not response.content
    assert not Membership.objects.filter(pk=membership.pk).exists()
    assert Membership.objects.filter(pk=other_membership.pk, role="owner").exists()
    assert Organization.objects.filter(pk__in=[organization.pk, other.pk]).count() == 2
    assert owner.__class__.objects.filter(pk__in=[owner.pk, member.pk]).count() == 2


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_membership_lookup_is_scoped_to_authorized_organization(
    api_client, owner, organization, membership, method
):
    other = Organization.objects.create(name="Other", slug="other")
    other_membership = Membership.objects.create(
        organization=other, user=owner, role=Membership.Role.OWNER
    )
    wrong_url = detail_url(membership, other)
    missing_url = wrong_url.replace(
        f"/memberships/{membership.pk}/", f"/memberships/{membership.pk + 1000}/"
    )

    wrong = getattr(api_client, method)(wrong_url, {"role": "owner"}, format="json")
    missing = getattr(api_client, method)(missing_url, {"role": "owner"}, format="json")

    assert wrong.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert wrong.data == missing.data
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER
    assert Membership.objects.filter(pk=other_membership.pk).exists()


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_owner_of_a_cannot_manage_b_as_member(
    api_client, owner, member, candidate, organization, membership, method
):
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(
        organization=other, user=owner, role=Membership.Role.MEMBER
    )
    other_owner = Membership.objects.create(
        organization=other, user=member, role=Membership.Role.OWNER
    )
    url = collection_url(other) if method == "post" else detail_url(other_owner)

    response = getattr(api_client, method)(
        url, {"user_id": candidate.pk, "role": "member"}, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    other_owner.refresh_from_db()
    assert other_owner.role == Membership.Role.OWNER
    assert not Membership.objects.filter(user=candidate).exists()


def test_removed_member_loses_all_reads_with_same_jwt(
    api_client, member, organization, membership
):
    member_client = client_for(member)
    assert member_client.get(collection_url(organization)).status_code == 200
    assert api_client.delete(detail_url(membership)).status_code == 204

    assert member_client.get(collection_url(organization)).status_code == 404
    detail = reverse(
        "organizations:organization-detail", kwargs={"organization_id": organization.pk}
    )
    assert member_client.get(detail).status_code == 404
    listing = member_client.get(reverse("organizations:organization-list"))
    assert listing.data["count"] == 0


def test_membership_pagination_is_stable_and_excludes_other_organizations(
    api_client, owner, organization, django_user_model
):
    people = django_user_model.objects.bulk_create(
        [django_user_model(username=f"paged-{i}") for i in range(21)]
    )
    memberships = Membership.objects.bulk_create(
        [Membership(organization=organization, user=person) for person in people]
    )
    # Tied timestamps exercise the ID tiebreaker.
    Membership.objects.filter(organization=organization).update(
        created_at=memberships[0].created_at
    )
    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(organization=other, user=owner, role="owner")
    expected = list(
        Membership.objects.filter(organization=organization)
        .order_by("created_at", "id")
        .values_list("id", flat=True)
    )

    first = api_client.get(
        collection_url(organization), {"page_size": 100, "organization_id": other.pk}
    )
    second = api_client.get(collection_url(organization), {"page": 2})

    assert first.status_code == second.status_code == 200
    assert first.data["count"] == second.data["count"] == 22
    assert [row["id"] for row in first.data["results"]] == expected[:20]
    assert [row["id"] for row in second.data["results"]] == expected[20:]
    assert first.data["previous"] is None and first.data["next"]
    assert second.data["previous"] and second.data["next"] is None


@pytest.mark.parametrize("page", ["invalid", "0", "2"])
def test_membership_invalid_page_returns_404(api_client, organization, page):
    response = api_client.get(collection_url(organization), {"page": page})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_collection_unsupported_methods(api_client, organization, method):
    response = getattr(api_client, method)(
        collection_url(organization), {}, format="json"
    )
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.parametrize("method", ["get", "put", "post"])
def test_membership_detail_unsupported_methods(api_client, membership, method):
    response = getattr(api_client, method)(detail_url(membership), {}, format="json")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.parametrize(
    "method, model_method, message",
    [
        ("post", "create", "Não foi possível adicionar o membro."),
        ("patch", "save", "Não foi possível atualizar o membro."),
        ("delete", "delete", "Não foi possível remover o membro."),
    ],
)
def test_integrity_errors_are_generic_and_leave_memberships_unchanged(
    api_client, candidate, organization, membership, method, model_method, message
):
    url = collection_url(organization) if method == "post" else detail_url(membership)
    target = (
        "apps.organizations.services.Membership.objects.create"
        if method == "post"
        else f"apps.organizations.services.Membership.{model_method}"
    )
    with patch(target, side_effect=IntegrityError("simulated private SQL failure")):
        response = getattr(api_client, method)(
            url,
            {"user_id": candidate.pk} if method == "post" else {"role": "owner"},
            format="json",
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert str(response.data["detail"]) == message
    assert "simulated private SQL failure" not in response.content.decode()
    membership.refresh_from_db()
    assert membership.role == Membership.Role.MEMBER
    assert Membership.objects.filter(organization=organization).count() == 2
