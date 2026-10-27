import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="task-owner")


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(username="task-member")


@pytest.fixture
def outsider(django_user_model):
    return django_user_model.objects.create_user(username="task-outsider")


@pytest.fixture
def organization(owner):
    organization = Organization.objects.create(name="Task team", slug="task-team")
    Membership.objects.create(organization=organization, user=owner, role="owner")
    return organization


@pytest.fixture
def membership(organization, member):
    return Membership.objects.create(
        organization=organization, user=member, role="member"
    )


@pytest.fixture
def project(organization, owner):
    return Project.objects.create(
        organization=organization, name="Task project", created_by=owner
    )


@pytest.fixture
def client_for():
    def make_client(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        return client

    return make_client


@pytest.fixture
def api_client(client_for, owner):
    return client_for(owner)


@pytest.fixture
def url(organization, project):
    return reverse(
        "projects:tasks:task-list",
        kwargs={"organization_id": organization.pk, "project_id": project.pk},
    )
