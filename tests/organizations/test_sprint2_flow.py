import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization

pytestmark = pytest.mark.django_db

TEST_PASSWORD = "sprint2-acceptance-test-only-password"


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
    assert profile.status_code == 200
    assert profile.data["id"] == user.pk
    return client, response.data


def test_sprint2_complete_flow_preserves_isolation_ownership_and_auth(
    django_user_model,
):
    original_owner, teammate, outsider = [
        django_user_model.objects.create_user(username=username, password=TEST_PASSWORD)
        for username in ["flow-owner", "flow-teammate", "flow-outsider"]
    ]
    owner_client, owner_tokens = authenticated_client(original_owner)
    member_client, _ = authenticated_client(teammate)
    outsider_client, _ = authenticated_client(outsider)
    collection = reverse("organizations:organization-list")
    assert member_client.get(collection).data["count"] == 0

    created = owner_client.post(
        collection, {"name": "Flow team", "slug": "flow-team"}, format="json"
    )
    assert created.status_code == 201
    assert created.data["my_role"] == "owner"
    organization_id = created.data["id"]
    organization_url = reverse(
        "organizations:organization-detail",
        kwargs={"organization_id": organization_id},
    )
    memberships_url = reverse(
        "organizations:membership-list",
        kwargs={"organization_id": organization_id},
    )
    own_membership = Membership.objects.get(
        organization_id=organization_id, user=original_owner
    )
    assert own_membership.role == Membership.Role.OWNER
    own_membership_url = f"{memberships_url}{own_membership.pk}/"
    assert outsider_client.get(organization_url).status_code == 404

    external = outsider_client.post(
        collection, {"name": "External team", "slug": "external-team"}, format="json"
    )
    assert external.status_code == 201
    external_membership = Membership.objects.get(organization_id=external.data["id"])
    assert owner_client.get(f"{collection}{external.data['id']}/").status_code == 404

    added = owner_client.post(memberships_url, {"user_id": teammate.pk}, format="json")
    assert added.status_code == 201
    assert added.data["role"] == "member"
    member_membership_url = f"{memberships_url}{added.data['id']}/"
    listing = member_client.get(collection)
    assert [(row["id"], row["my_role"]) for row in listing.data["results"]] == [
        (organization_id, "member")
    ]
    details = member_client.get(organization_url)
    assert details.status_code == 200 and details.data["my_role"] == "member"
    members = member_client.get(memberships_url)
    assert members.status_code == 200 and members.data["count"] == 2
    assert all(
        set(row) == {"id", "user_id", "username", "role", "created_at"}
        for row in members.data["results"]
    )
    assert (
        member_client.patch(
            organization_url, {"name": "Forbidden"}, format="json"
        ).status_code
        == 403
    )
    assert (
        member_client.patch(
            member_membership_url, {"role": "owner"}, format="json"
        ).status_code
        == 403
    )

    assert (
        owner_client.patch(
            organization_url, {"name": "Owner update"}, format="json"
        ).status_code
        == 200
    )
    assert member_client.get(organization_url).data["name"] == "Owner update"
    assert (
        owner_client.patch(
            member_membership_url, {"role": "owner"}, format="json"
        ).status_code
        == 200
    )

    # The teammate uses the original JWT throughout promotion and transfer.
    assert member_client.get(organization_url).data["my_role"] == "owner"
    assert (
        member_client.patch(
            organization_url, {"name": "Transferred team"}, format="json"
        ).status_code
        == 200
    )
    assert (
        owner_client.patch(
            own_membership_url, {"role": "member"}, format="json"
        ).status_code
        == 200
    )
    assert (
        owner_client.patch(
            organization_url, {"name": "Forbidden after demotion"}, format="json"
        ).status_code
        == 403
    )
    last_owner = member_client.delete(member_membership_url)
    assert last_owner.status_code == 400
    assert "role" in last_owner.data
    assert Membership.objects.get(pk=added.data["id"]).role == Membership.Role.OWNER

    assert (
        member_client.delete(f"{memberships_url}{external_membership.pk}/").status_code
        == 404
    )
    assert member_client.delete(own_membership_url).status_code == 204
    assert owner_client.get(organization_url).status_code == 404
    assert owner_client.get(memberships_url).status_code == 404
    assert owner_client.get(collection).data["count"] == 0

    # Losing an organization link preserves the account and JWT refresh flow.
    refresh = APIClient().post(
        reverse("token_refresh"), {"refresh": owner_tokens["refresh"]}, format="json"
    )
    assert refresh.status_code == 200
    owner_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.data['access']}")
    assert owner_client.get(reverse("current_user")).data["id"] == original_owner.pk
    assert owner_client.get(organization_url).status_code == 404
    assert django_user_model.objects.count() == 3
    assert Organization.objects.count() == 2
    assert Organization.objects.get(pk=organization_id).name == "Transferred team"
    assert Membership.objects.count() == 2
    assert (
        Membership.objects.filter(
            organization_id=organization_id, role="owner", user__is_active=True
        ).count()
        == 1
    )
    assert Membership.objects.filter(
        pk=external_membership.pk, user=outsider, role="owner"
    ).exists()
