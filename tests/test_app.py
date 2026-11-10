import os

import pytest


def test_health_and_ready(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").get_json() == {"status": "ready"}


def test_version_reports_release(client):
    body = client.get("/api/version").get_json()
    assert body == {"service": "notes-api", "version": "1.8.3", "environment": "validation"}


def test_not_ready_without_release_version(client, monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert "RELEASE_VERSION is not set" in response.get_json()["problems"]


def test_not_ready_with_unknown_environment(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "qa")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert any("APP_ENV 'qa'" in problem for problem in response.get_json()["problems"])


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_not_ready_when_data_dir_is_read_only(client, service_env):
    service_env.chmod(0o555)
    try:
        response = client.get("/readyz")
    finally:
        service_env.chmod(0o755)
    assert response.status_code == 503
    assert any("not writable" in problem for problem in response.get_json()["problems"])


def test_not_ready_when_data_dir_is_missing(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "nope"))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert any("does not exist" in problem for problem in response.get_json()["problems"])


def test_notes_round_trip(client):
    created = client.post("/api/notes", json={"text": "  cutover at 02:00  "})
    assert created.status_code == 201
    assert created.get_json()["text"] == "cutover at 02:00"

    notes = client.get("/api/notes").get_json()["notes"]
    assert [note["text"] for note in notes] == ["cutover at 02:00"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "{not json", "content_type": "application/json"},
        {"json": ["text"]},
        {"json": {"text": ""}},
        {"json": {"text": {"$gt": ""}}},
        {"json": {"text": "x" * 501}},
    ],
)
def test_bad_notes_are_rejected(client, kwargs):
    response = client.post("/api/notes", **kwargs)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_oversized_body_is_refused(client):
    response = client.post("/api/notes", data=b"x" * 20000, content_type="application/json")
    assert response.status_code == 413


def test_errors_are_json_without_internals(client):
    response = client.get("/no-such-thing")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not found"}
    assert response.headers["Cache-Control"] == "no-store"
