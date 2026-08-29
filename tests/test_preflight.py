"""Doctor checks. A Replit run should never fail halfway with a vague error --
these decide what it says up front."""
import pytest

from vending_outreach.config import Config
from vending_outreach.preflight import (
    _mask, check_database, check_google_oauth, on_replit, render, run_checks)


@pytest.fixture
def cfg():
    return Config.load()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("DATABASE_URL", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                "GOOGLE_OAUTH_REFRESH_TOKEN", "REPL_ID", "REPLIT_DEPLOYMENT",
                "REPLIT_DEV_DOMAIN", "CRM_BASE_URL", "CRM_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_secrets_are_masked_never_printed_whole():
    masked = _mask("super-secret-refresh-token-value")
    assert "secret" not in masked
    assert masked.startswith("supe")


def test_short_secrets_are_fully_masked():
    assert _mask("abc123") == "******"


def test_unset_secret_reads_as_unset():
    assert _mask("") == "(unset)"


def test_replit_is_detected_from_its_env(monkeypatch):
    assert not on_replit()
    monkeypatch.setenv("REPL_ID", "abc")
    assert on_replit()


def test_missing_database_on_replit_is_flagged_as_a_failure(cfg, monkeypatch):
    """This is the one that would silently re-email everyone, so it must fail
    the check rather than warn."""
    monkeypatch.setenv("REPL_ID", "abc")
    check = check_database(cfg)
    assert not check.ok
    assert "wiped" in check.detail


def test_missing_database_locally_is_fine(cfg):
    assert check_database(cfg).ok


def test_database_detail_does_not_leak_the_password(cfg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql://user:hunter2@db.replit.com:5432/main")
    check = check_database(cfg)
    assert check.ok
    assert "hunter2" not in check.detail


def test_google_oauth_passes_on_the_three_env_secrets(cfg, monkeypatch):
    for var in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                "GOOGLE_OAUTH_REFRESH_TOKEN"):
        monkeypatch.setenv(var, "x" * 40)
    assert check_google_oauth(cfg).ok


def test_google_oauth_names_exactly_what_is_missing(cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "x" * 40)
    check = check_google_oauth(cfg)
    assert not check.ok
    assert "CLIENT_SECRET" in check.detail and "REFRESH_TOKEN" in check.detail
    assert "CLIENT_ID" not in check.detail.replace("CLIENT_ID,", "")


def test_report_explains_the_cost_of_each_gap(cfg):
    out = render(run_checks(cfg), cfg)
    assert "without it:" in out
    assert "discovering new apartment communities" in out


def test_report_is_clean_when_everything_is_set(cfg, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://h/db")
    for var in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                "GOOGLE_OAUTH_REFRESH_TOKEN"):
        monkeypatch.setenv(var, "x" * 40)
    monkeypatch.setenv("CRM_BASE_URL", "https://crm.example.com")
    monkeypatch.setenv("CRM_API_TOKEN", "x" * 20)
    cfg.secrets.places_api_key = "x" * 30
    cfg.secrets.sender_email = "grillycheese@grillycheese.net"
    cfg.secrets.hubspot_token = "x" * 30
    assert "All configured." in render(run_checks(cfg), cfg)
