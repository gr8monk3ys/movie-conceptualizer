"""Tests for job admin endpoints, ownership, and audit logging."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOVIECON_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MOVIECON_REQUIRE_AUTH", "true")
    monkeypatch.setenv("MOVIECON_DEV_MODE", "true")
    monkeypatch.setenv("MOVIECON_ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("MOVIECON_ADMIN_USERS", "dev")
    monkeypatch.setenv("MOVIECON_WORKFLOW_BACKEND", "mock")
    monkeypatch.setenv("MOVIECON_JOB_BACKEND", "inprocess")
    monkeypatch.setenv("MOVIECON_INPROCESS_INLINE", "true")

    import movie_conceptualizer.api.auth as auth
    import movie_conceptualizer.api.dependencies as deps
    import movie_conceptualizer.api.main as main

    importlib.reload(auth)
    importlib.reload(deps)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _get_token(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _register_user(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_project_ownership_and_listing(client):
    admin_token = _get_token(client, "dev", "dev123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates a project
    response = client.post(
        "/api/v1/projects",
        json={"title": "Admin Project"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    admin_project = response.json()
    assert admin_project["user_id"] is not None

    # Register a non-admin user
    user_id = _register_user(client, "alice", "alicepass123")
    user_token = _get_token(client, "alice", "alicepass123")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Non-admin creates a project
    response = client.post(
        "/api/v1/projects",
        json={"title": "User Project"},
        headers=user_headers,
    )
    assert response.status_code == 201
    user_project = response.json()
    assert user_project["user_id"] == user_id

    # Non-admin should only list their own projects
    response = client.get("/api/v1/projects", headers=user_headers)
    assert response.status_code == 200
    projects = response.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["id"] == user_project["id"]

    # Non-admin cannot access admin project
    response = client.get(f"/api/v1/projects/{admin_project['id']}", headers=user_headers)
    assert response.status_code == 403

    # Admin can assign ownership to the user
    response = client.post(
        f"/api/v1/projects/{admin_project['id']}/owner",
        json={"user_id": user_id},
        headers=admin_headers,
    )
    assert response.status_code == 200

    # Now user can access the admin project
    response = client.get(f"/api/v1/projects/{admin_project['id']}", headers=user_headers)
    assert response.status_code == 200


def test_jobs_access_and_audit_logs(client):
    admin_token = _get_token(client, "dev", "dev123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user_id = _register_user(client, "bob", "bobpass123")
    user_token = _get_token(client, "bob", "bobpass123")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Create a project for user and run analysis async to create a job
    response = client.post(
        "/api/v1/projects",
        json={"title": "User Job Project"},
        headers=user_headers,
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    script_body = {
        "content": "Title: Sample\nAuthor: Tester\n\nINT. HOUSE - DAY\nJOHN\nHello there.",
        "format": "fountain",
    }
    response = client.post(
        f"/api/v1/projects/{project_id}/script",
        json=script_body,
        headers=user_headers,
    )
    assert response.status_code == 201

    response = client.post(
        f"/api/v1/projects/{project_id}/analyze?async_run=true",
        headers=user_headers,
    )
    assert response.status_code == 202
    user_job_id = response.json()["job_id"]

    # User can list their jobs and see their job id
    response = client.get("/api/v1/jobs", headers=user_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    job_ids = {item["job_id"] for item in items}
    assert user_job_id in job_ids
    job_item = next(item for item in items if item["job_id"] == user_job_id)
    assert job_item["user_id"] == user_id

    response = client.get("/api/v1/jobs?status=RUNNING", headers=user_headers)
    assert response.status_code == 200

    response = client.get("/api/v1/jobs?status=not-a-status", headers=user_headers)
    assert response.status_code == 400

    # Admin creates a job
    response = client.post(
        "/api/v1/projects",
        json={"title": "Admin Job Project"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    admin_project_id = response.json()["id"]
    response = client.post(
        f"/api/v1/projects/{admin_project_id}/script",
        json=script_body,
        headers=admin_headers,
    )
    assert response.status_code == 201
    response = client.post(
        f"/api/v1/projects/{admin_project_id}/analyze?async_run=true",
        headers=admin_headers,
    )
    assert response.status_code == 202
    admin_job_id = response.json()["job_id"]

    # User should not access admin job
    response = client.get(f"/api/v1/jobs/{admin_job_id}", headers=user_headers)
    assert response.status_code == 403

    # Admin metrics endpoint should work and generate audit logs
    response = client.get("/api/v1/jobs/metrics", headers=admin_headers)
    assert response.status_code == 200

    response = client.get("/api/v1/jobs/audit", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    first_log = response.json()["items"][0]
    assert isinstance(first_log.get("created_at"), str)
    assert "T" in first_log.get("created_at", "")
    assert {"id", "actor_user_id", "action", "created_at"} <= set(first_log.keys())
    assert isinstance(first_log.get("id"), str)
    assert isinstance(first_log.get("actor_user_id"), str)
    assert isinstance(first_log.get("action"), str)

    response = client.get("/api/v1/jobs/audit?format=csv", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")
    content_disposition = response.headers.get("content-disposition", "")
    assert content_disposition.startswith("attachment; filename=job_audit_logs_")
    assert content_disposition.endswith(".csv")
    assert len(content_disposition) >= len("attachment; filename=job_audit_logs_20240101_000000.csv")
    assert "created_at" in response.text
    assert "Z" in response.text

    response = client.get("/api/v1/jobs/audit?format=CSV", headers=admin_headers)
    assert response.status_code == 200

    response = client.get("/api/v1/jobs/audit?format=xml", headers=admin_headers)
    assert response.status_code == 400
