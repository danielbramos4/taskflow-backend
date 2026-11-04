import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client


def sign_in(client, user, password):
    assert client.get("/entrar/").status_code == 200
    response = client.post(
        "/entrar/",
        {"username": user.username, "password": password},
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 302 and response.url == "/"
    return client.cookies["csrftoken"].value


@pytest.mark.django_db
def test_web_login_session_csrf_and_role_checks(django_user_model):
    password = "only-a-test-password-123"
    owner = django_user_model.objects.create_user(
        username="web_owner", password=password
    )
    member = django_user_model.objects.create_user(
        username="web_member", password=password
    )
    browser = Client(enforce_csrf_checks=True)
    reader = Client(enforce_csrf_checks=True)
    assert browser.get("/").url.startswith("/entrar/")
    assert browser.get("/api/v1/organizations/").status_code == 401
    csrf = sign_in(browser, owner, password)
    assert b"Nova tarefa" in browser.get("/").content
    assert browser.get("/api/v1/auth/me/").json()["id"] == owner.pk
    org_path = "/api/v1/organizations/"
    org_body = {"name": "Web test", "slug": "web-test"}
    assert (
        browser.post(org_path, org_body, content_type="application/json").status_code
        == 403
    )

    def post(path, body):
        response = browser.post(
            path, body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
        )
        assert response.status_code == 201
        return response.json()

    org = post(org_path, org_body)
    path = f"{org_path}{org['id']}/"
    project = post(f"{path}projects/", {"name": "Interface"})
    link = post(f"{path}memberships/", {"user_id": member.pk})
    tasks = f"{path}projects/{project['id']}/tasks/"
    task = post(
        tasks,
        {
            "title": "Validar interface",
            "due_date": "2026-11-12",
            "assignee_membership_id": link["id"],
        },
    )
    reader_csrf = sign_in(reader, member, password)
    assert reader.get(f"{tasks}?due_to=2026-11-12").json()["count"] == 1
    detail = f"{tasks}{task['id']}/"
    assert (
        reader.patch(
            detail,
            {"status": "done"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=reader_csrf,
        ).status_code
        == 403
    )
    complete = browser.patch(
        detail,
        {"status": "done"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert complete.status_code == 200 and complete.json()["status"] == "done"
    assert browser.get("/sair/").status_code == 405
    assert browser.post("/sair/", HTTP_X_CSRFTOKEN=csrf).status_code == 302
    assert browser.get("/api/v1/organizations/").status_code == 401


@pytest.mark.django_db
def test_bootstrap_never_resets_or_promotes(monkeypatch, django_user_model):
    monkeypatch.setenv("TASKFLOW_ADMIN_USERNAME", "bootstrap_user")
    password = "A-long-secret-only-for-this-test-1"
    monkeypatch.setenv("TASKFLOW_ADMIN_PASSWORD", password)
    call_command("bootstrap_web_admin")
    admin = django_user_model.objects.get(username="bootstrap_user")
    assert admin.is_superuser and admin.check_password(password)
    monkeypatch.setenv("TASKFLOW_ADMIN_PASSWORD", "A-different-test-password-2")
    call_command("bootstrap_web_admin")
    admin.refresh_from_db()
    assert admin.check_password(password)
    existing = django_user_model.objects.create_user(username="not_admin")
    monkeypatch.setenv("TASKFLOW_ADMIN_USERNAME", existing.username)
    with pytest.raises(CommandError, match="already in use"):
        call_command("bootstrap_web_admin")
    existing.refresh_from_db()
    assert not existing.is_staff and not existing.is_superuser
