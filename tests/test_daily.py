"""The Scheduled Deployment entrypoint.

A nightly run has nobody watching it. One stage failing must not stop the
report, and must never stop the run *after* emails have already gone out.
"""
import argparse

import pytest

from vending_outreach import cli
from vending_outreach.config import Config


@pytest.fixture
def cfg():
    return Config.load()


def _args(**kw):
    base = dict(mode="dry-run", enrich_limit=1, queue_limit=1, outreach_limit=1,
                skip_discovery=True, ignore_window=True, strict=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_daily_completes_and_reports(cfg, store, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_enrichment", lambda *a, **k: {"processed": 0})
    monkeypatch.setattr(cli, "compute_portfolio_sizes", lambda *a: 0)
    assert cli.cmd_daily(_args(), cfg, store) == 0
    out = capsys.readouterr().out
    for stage in ("enrich", "score", "queue", "outreach", "sync", "report"):
        assert f"=== {stage}" in out


def test_a_failing_stage_does_not_stop_the_report(cfg, store, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("enrichment exploded")
    monkeypatch.setattr(cli, "run_enrichment", boom)
    monkeypatch.setattr(cli, "compute_portfolio_sizes", lambda *a: 0)
    assert cli.cmd_daily(_args(), cfg, store) == 0
    assert "=== report ===" in capsys.readouterr().out


def test_a_stage_calling_sys_exit_does_not_stop_the_report(cfg, store,
                                                           monkeypatch, capsys):
    """SystemExit is not an Exception. An unconfigured CRM used to abort the
    whole run here, after outreach had already sent."""
    def bail(*a, **k):
        raise SystemExit("missing credentials")
    monkeypatch.setattr(cli, "run_enrichment", bail)
    monkeypatch.setattr(cli, "compute_portfolio_sizes", lambda *a: 0)
    assert cli.cmd_daily(_args(), cfg, store) == 0
    assert "=== report ===" in capsys.readouterr().out


def test_strict_mode_stops_on_a_failing_stage(cfg, store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(cli, "run_enrichment", boom)
    assert cli.cmd_daily(_args(strict=True), cfg, store) == 1


def test_discovery_is_skipped_without_a_places_key(cfg, store, monkeypatch, capsys):
    cfg.secrets.places_api_key = ""
    monkeypatch.setattr(cli, "run_enrichment", lambda *a, **k: {})
    monkeypatch.setattr(cli, "compute_portfolio_sizes", lambda *a: 0)
    monkeypatch.setattr(cli, "run_discovery",
                        lambda *a, **k: pytest.fail("discovery must not run"))
    cli.cmd_daily(_args(skip_discovery=False), cfg, store)
    assert "=== discover" not in capsys.readouterr().out


def test_daily_defaults_to_draft_not_live():
    """The scheduled job must never default to sending."""
    args = cli.build_parser().parse_args(["daily"])
    assert args.mode == "draft"


def test_outreach_defaults_to_dry_run():
    assert cli.build_parser().parse_args(["outreach"]).mode == "dry-run"
