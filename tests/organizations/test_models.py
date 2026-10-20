import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.organizations.models import Membership, Organization


@pytest.fixture
def user(db):
    User = get_user_model()

    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def organization(db):
    return Organization.objects.create(
        name="Empresa Teste",
        slug="empresa-teste",
    )


@pytest.mark.django_db
def test_create_organization(organization):
    assert organization.name == "Empresa Teste"
    assert organization.slug == "empresa-teste"


@pytest.mark.django_db
def test_user_can_join_multiple_organizations(user, organization):
    second_organization = Organization.objects.create(
        name="Segunda Empresa",
        slug="segunda-empresa",
    )

    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.OWNER,
    )

    Membership.objects.create(
        user=user,
        organization=second_organization,
        role=Membership.Role.MEMBER,
    )

    assert Membership.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_organization_can_have_multiple_members(user, organization):
    User = get_user_model()

    second_user = User.objects.create_user(
        username="seconduser",
        password="TestPassword123!",
    )

    Membership.objects.create(
        user=user,
        organization=organization,
    )

    Membership.objects.create(
        user=second_user,
        organization=organization,
    )

    assert organization.memberships.count() == 2


@pytest.mark.django_db
def test_duplicate_membership_is_rejected(user, organization):
    Membership.objects.create(
        user=user,
        organization=organization,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(
                user=user,
                organization=organization,
            )

    assert Membership.objects.count() == 1


@pytest.mark.django_db
def test_membership_roles(user, organization):
    membership = Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.OWNER,
    )

    assert membership.role == "owner"
    assert Membership.Role.MEMBER == "member"
