"""Headless credential handling.

The browser OAuth flow cannot run on Replit. These pin the behaviour that keeps
a Scheduled Deployment from hanging forever on a callback that never comes.
"""
import pytest

from vending_outreach.outreach import google_client


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                "GOOGLE_OAUTH_REFRESH_TOKEN", "REPL_ID", "REPLIT_DEPLOYMENT"):
        monkeypatch.delenv(var, raising=False)


def test_no_env_credentials_returns_none(monkeypatch):
    assert google_client.credentials_from_env() is None


def test_partial_env_credentials_returns_none(monkeypatch):
    """Two of three is not enough, and must not be treated as configured."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    assert google_client.credentials_from_env() is None


def test_env_credentials_are_built_and_refreshed(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REFRESH_TOKEN", "refresh")

    refreshed = []
    monkeypatch.setattr(google_client.Credentials, "refresh",
                        lambda self, request: refreshed.append(True))
    creds = google_client.credentials_from_env()
    assert creds.refresh_token == "refresh"
    assert refreshed, "a refresh token alone has no access token; must mint one"


def test_env_credentials_win_over_a_token_file(monkeypatch, tmp_path):
    """Deployments are configured by Secrets; a stale cached file must not
    shadow them."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(google_client.Credentials, "refresh", lambda s, r: None)

    cache = tmp_path / "token.json"
    cache.write_text("{}")
    creds = google_client.get_credentials("missing.json", str(cache))
    assert creds.refresh_token == "refresh"


def test_refuses_to_open_a_browser_on_replit(monkeypatch, tmp_path):
    """run_local_server would wait forever for a callback that never arrives."""
    monkeypatch.setenv("REPL_ID", "abc")
    secrets = tmp_path / "client.json"
    secrets.write_text("{}")
    with pytest.raises(SystemExit) as exc:
        google_client.get_credentials(str(secrets), str(tmp_path / "nope.json"))
    assert "Replit" in str(exc.value)


def test_missing_credentials_message_explains_the_replit_path(tmp_path):
    with pytest.raises(SystemExit) as exc:
        google_client.get_credentials(str(tmp_path / "absent.json"),
                                      str(tmp_path / "absent-token.json"))
    message = str(exc.value)
    assert "GOOGLE_OAUTH_REFRESH_TOKEN" in message
    assert "vending_outreach auth" in message
