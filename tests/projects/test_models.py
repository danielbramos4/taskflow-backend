import pytest
from django.db.models.deletion import ProtectedError

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


def test_project_defaults_and_relations(organization, owner):
    project = Project.objects.create(
        organization=organization, created_by=owner, name="First project"
    )

    assert project.description == ""
    assert project.is_archived is False
    assert project.created_at and project.updated_at
    assert str(project) == "First project"
    assert organization.projects.get() == project
    assert owner.created_projects.get() == project


def test_project_protects_organization_from_cascading_deletion(organization, owner):
    project = Project.objects.create(
        organization=organization, created_by=owner, name="Preserved"
    )

    with pytest.raises(ProtectedError):
        organization.delete()

    assert Project.objects.filter(pk=project.pk).exists()
    assert Organization.objects.filter(pk=organization.pk).exists()
    assert Membership.objects.filter(organization=organization, user=owner).exists()


def test_deleting_author_preserves_project_with_null_attribution(
    organization, owner, outsider
):
    Membership.objects.create(organization=organization, user=outsider, role="owner")
    project = Project.objects.create(
        organization=organization, created_by=owner, name="Preserved"
    )

    owner.delete()

    project.refresh_from_db()
    assert project.created_by_id is None
    assert project.organization_id == organization.pk
    assert project.name == "Preserved"
    assert Membership.objects.filter(
        organization=organization, user=outsider, role="owner"
    ).exists()


def test_project_names_can_repeat_and_order_is_stable(organization, owner):
    projects = [
        Project.objects.create(organization=organization, created_by=owner, name="Same")
        for _ in range(2)
    ]

    assert list(Project.objects.all()) == projects
    assert projects[0].pk != projects[1].pk
