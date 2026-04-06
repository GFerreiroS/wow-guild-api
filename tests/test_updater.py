"""Tests for lib/updater.py and /admin/updates/* endpoints."""

from unittest.mock import MagicMock, patch

import pytest

import lib.updater as updater
from tests.conftest import auth_headers, make_user


# ---------------------------------------------------------------------------
# Unit: get_local_version
# ---------------------------------------------------------------------------

def test_get_local_version(tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.2.3\n")
    with patch.object(updater, "VERSION_FILE", f):
        assert updater.get_local_version() == "1.2.3"


def test_get_local_version_strips_whitespace(tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("  2.0.0  \n")
    with patch.object(updater, "VERSION_FILE", f):
        assert updater.get_local_version() == "2.0.0"


# ---------------------------------------------------------------------------
# Unit: _parse_version
# ---------------------------------------------------------------------------

def test_parse_version_basic():
    assert updater._parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_strips_v_prefix():
    assert updater._parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_double_digit_minor():
    assert updater._parse_version("1.10.0") > updater._parse_version("1.9.0")


# ---------------------------------------------------------------------------
# Unit: get_latest_release
# ---------------------------------------------------------------------------

def test_get_latest_release_returns_data(mocker):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"tag_name": "v2.0.0", "html_url": "https://example.com", "body": "notes"}
    mocker.patch("lib.updater.requests.get", return_value=mock_resp)
    result = updater.get_latest_release()
    assert result["tag_name"] == "v2.0.0"


def test_get_latest_release_uses_github_repo(mocker):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"tag_name": "v1.0.0", "html_url": "", "body": ""}
    mock_get = mocker.patch("lib.updater.requests.get", return_value=mock_resp)
    with patch.object(updater, "GITHUB_REPO", "myuser/myrepo"):
        updater.get_latest_release()
    assert "myuser/myrepo" in mock_get.call_args[0][0]


# ---------------------------------------------------------------------------
# Unit: check_for_updates
# ---------------------------------------------------------------------------

def _mock_github_release(mocker, tag: str):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "tag_name": tag,
        "html_url": "https://github.com/example/releases/tag/" + tag,
        "body": "Release notes",
    }
    mocker.patch("lib.updater.requests.get", return_value=mock_resp)


def test_check_update_available(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.0.0")
    _mock_github_release(mocker, "v2.0.0")
    with patch.object(updater, "VERSION_FILE", f):
        result = updater.check_for_updates()
    assert result["update_available"] is True
    assert result["current_version"] == "1.0.0"
    assert result["latest_version"] == "2.0.0"


def test_check_no_update_same_version(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("2.0.0")
    _mock_github_release(mocker, "v2.0.0")
    with patch.object(updater, "VERSION_FILE", f):
        result = updater.check_for_updates()
    assert result["update_available"] is False


def test_check_no_update_local_ahead(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("2.1.0")
    _mock_github_release(mocker, "v2.0.0")
    with patch.object(updater, "VERSION_FILE", f):
        result = updater.check_for_updates()
    assert result["update_available"] is False


def test_check_includes_release_url_and_notes(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.0.0")
    _mock_github_release(mocker, "v1.1.0")
    with patch.object(updater, "VERSION_FILE", f):
        result = updater.check_for_updates()
    assert "example" in result["release_url"]
    assert result["release_notes"] == "Release notes"


# ---------------------------------------------------------------------------
# Unit: apply_update
# ---------------------------------------------------------------------------

def test_apply_runs_git_pull_and_alembic(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.1.0")
    mock_run = mocker.patch("lib.updater.subprocess.run", return_value=MagicMock(returncode=0))
    mocker.patch("lib.updater.threading.Timer")
    with patch.object(updater, "VERSION_FILE", f):
        updater.apply_update()
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0][0][0] == ["git", "pull"]
    assert mock_run.call_args_list[1][0][0] == ["alembic", "upgrade", "head"]


def test_apply_git_pull_failure_raises(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.1.0")
    mocker.patch("lib.updater.subprocess.run", return_value=MagicMock(returncode=1, stderr="auth error"))
    mocker.patch("lib.updater.threading.Timer")
    with patch.object(updater, "VERSION_FILE", f):
        with pytest.raises(RuntimeError, match="git pull failed"):
            updater.apply_update()


def test_apply_alembic_failure_raises(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.1.0")
    mocker.patch("lib.updater.subprocess.run", side_effect=[
        MagicMock(returncode=0),                           # git pull ok
        MagicMock(returncode=1, stderr="migration error"), # alembic fails
    ])
    mocker.patch("lib.updater.threading.Timer")
    with patch.object(updater, "VERSION_FILE", f):
        with pytest.raises(RuntimeError, match="alembic upgrade failed"):
            updater.apply_update()


def test_apply_returns_new_version(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.5.0")
    mocker.patch("lib.updater.subprocess.run", return_value=MagicMock(returncode=0))
    mocker.patch("lib.updater.threading.Timer")
    with patch.object(updater, "VERSION_FILE", f):
        result = updater.apply_update()
    assert result["updated_to"] == "1.5.0"
    assert result["restarting"] is True


def test_apply_schedules_restart_with_delay(mocker, tmp_path):
    f = tmp_path / "VERSION"
    f.write_text("1.1.0")
    mocker.patch("lib.updater.subprocess.run", return_value=MagicMock(returncode=0))
    mock_timer = mocker.patch("lib.updater.threading.Timer")
    with patch.object(updater, "VERSION_FILE", f):
        updater.apply_update()
    mock_timer.assert_called_once()
    assert mock_timer.call_args[0][0] == 1.0


# ---------------------------------------------------------------------------
# API: GET /admin/updates/check
# ---------------------------------------------------------------------------

def test_check_endpoint_requires_auth(client):
    resp = client.get("/api/admin/updates/check")
    assert resp.status_code == 401


def test_check_endpoint_plain_user_forbidden(client, session):
    make_user(session, rank=2)
    resp = client.get("/api/admin/updates/check", headers=auth_headers(client))
    assert resp.status_code == 403


def test_check_endpoint_owner_allowed(client, session, mocker):
    make_user(session, rank=0, username="owner")
    mocker.patch("lib.updater.check_for_updates", return_value={
        "current_version": "1.0.0",
        "latest_version": "1.1.0",
        "update_available": True,
        "release_url": "https://example.com",
        "release_notes": "New raid tier added.",
    })
    resp = client.get("/api/admin/updates/check", headers=auth_headers(client, "owner"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["update_available"] is True
    assert data["latest_version"] == "1.1.0"
    assert data["current_version"] == "1.0.0"


def test_check_endpoint_admin_allowed(client, session, mocker):
    make_user(session, rank=1, username="officer", character_id=2)
    mocker.patch("lib.updater.check_for_updates", return_value={
        "current_version": "1.0.0",
        "latest_version": "1.0.0",
        "update_available": False,
        "release_url": None,
        "release_notes": None,
    })
    resp = client.get("/api/admin/updates/check", headers=auth_headers(client, "officer"))
    assert resp.status_code == 200
    assert resp.json()["update_available"] is False


def test_check_endpoint_github_unreachable_returns_502(client, session, mocker):
    make_user(session, rank=0, username="owner")
    mocker.patch("lib.updater.check_for_updates", side_effect=Exception("connection timeout"))
    resp = client.get("/api/admin/updates/check", headers=auth_headers(client, "owner"))
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# API: POST /admin/updates/apply
# ---------------------------------------------------------------------------

def test_apply_endpoint_requires_auth(client):
    resp = client.post("/api/admin/updates/apply")
    assert resp.status_code == 401


def test_apply_endpoint_plain_user_forbidden(client, session):
    make_user(session, rank=2)
    resp = client.post("/api/admin/updates/apply", headers=auth_headers(client))
    assert resp.status_code == 403


def test_apply_endpoint_admin_forbidden(client, session):
    make_user(session, rank=1, username="officer")
    resp = client.post("/api/admin/updates/apply", headers=auth_headers(client, "officer"))
    assert resp.status_code == 403


def test_apply_endpoint_owner_allowed(client, session, mocker):
    make_user(session, rank=0, username="owner")
    mocker.patch("lib.updater.apply_update", return_value={"updated_to": "1.1.0", "restarting": True})
    resp = client.post("/api/admin/updates/apply", headers=auth_headers(client, "owner"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_to"] == "1.1.0"
    assert data["restarting"] is True


def test_apply_endpoint_calls_apply_update(client, session, mocker):
    make_user(session, rank=0, username="owner")
    mock_apply = mocker.patch("lib.updater.apply_update", return_value={"updated_to": "1.1.0", "restarting": True})
    client.post("/api/admin/updates/apply", headers=auth_headers(client, "owner"))
    mock_apply.assert_called_once_with()


def test_apply_endpoint_git_failure_returns_500(client, session, mocker):
    make_user(session, rank=0, username="owner")
    mocker.patch("lib.updater.apply_update", side_effect=RuntimeError("git pull failed: auth error"))
    resp = client.post("/api/admin/updates/apply", headers=auth_headers(client, "owner"))
    assert resp.status_code == 500
