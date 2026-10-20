import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_credentials():
    return {
        "username": "authuser",
        "password": "TestPassword123!",
    }


@pytest.fixture
def user(db, user_credentials):
    return get_user_model().objects.create_user(
        **user_credentials,
        email="auth@example.com",
        first_name="Auth",
        last_name="User",
    )


@pytest.fixture
def token_pair(api_client, user, user_credentials):
    response = api_client.post(
        reverse("token_obtain_pair"), user_credentials, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    return response.data


def test_login_returns_access_and_refresh(api_client, user, user_credentials):
    response = api_client.post(
        reverse("token_obtain_pair"), user_credentials, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data["access"], str)
    assert response.data["access"]
    assert isinstance(response.data["refresh"], str)
    assert response.data["refresh"]


def test_login_with_invalid_password(api_client, user, user_credentials):
    response = api_client.post(
        reverse("token_obtain_pair"),
        {**user_credentials, "password": "WrongPassword123!"},
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token(api_client, token_pair):
    response = api_client.post(
        reverse("token_refresh"),
        {"refresh": token_pair["refresh"]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data["access"], str)
    assert response.data["access"]
    assert response.data["access"] != token_pair["access"]


def test_me_requires_authentication(api_client):
    response = api_client.get(reverse("current_user"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_me_returns_authenticated_user(api_client, user, token_pair):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_pair['access']}")

    response = api_client.get(reverse("current_user"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def test_me_rejects_invalid_token(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")

    response = api_client.get(reverse("current_user"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
