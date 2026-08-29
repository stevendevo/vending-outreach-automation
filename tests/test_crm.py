"""CRM adapter tests. HubSpot is now a contacts-only mirror; the Replit CRM
is the primary sink."""
import json

import pytest
import requests

from vending_outreach.config import Config
from vending_outreach.crm import build_hubspot, build_primary, lead_from
from vending_outreach.crm.base import ActivityPayload, LeadPayload
from vending_outreach.crm.replit_crm import PreviewCRMClient, ReplitCRMClient
from vending_outreach.models import Contact, Property


@pytest.fixture
def cfg():
    return Config.load()


def _lead():
    return LeadPayload(external_id="k1", name="Haddon Point", city="Pennsauken",
                       state="NJ", unit_count=412, score=69,
                       contact_email="info@hp.com", contact_first_name="Dana")


class FakeSession:
    def __init__(self, status=200, payload=None):
        self.headers = {}
        self.status, self.payload = status, payload or {"id": "lead_1"}
        self.calls = []

    def request(self, method, url, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "body": json})
        return FakeResponse(self.status, self.payload)


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


# --------------------------------------------------------------- payload shape
def test_lead_omits_empty_fields():
    """The CRM shouldn't have to store a wall of empty strings."""
    body = LeadPayload(external_id="k", name="X").to_dict()
    assert "address" not in body
    assert body["name"] == "X"


def test_lead_carries_the_offer_terms(cfg):
    prop = Property(key="k", name="X", unit_count=300)
    lead = lead_from(prop, None, cfg)
    assert lead.offer_guarantee_usd == 1050.0
    assert lead.offer_model == "resident-pay vending"


def test_lead_carries_the_named_contact(cfg):
    prop = Property(key="k", name="X")
    contact = Contact(property_key="k", email="a@x.com", first_name="Dana",
                      title="Community Manager")
    lead = lead_from(prop, contact, cfg)
    assert lead.contact_email == "a@x.com"
    assert lead.contact_title == "Community Manager"


def test_external_id_is_the_property_key_so_resync_updates(cfg):
    """Re-running sync must update the same CRM record, not create a second."""
    prop = Property(key="stable-key", name="X")
    assert lead_from(prop, None, cfg).external_id == "stable-key"


# ------------------------------------------------------------- replit adapter
def test_posts_to_the_configured_endpoint():
    session = FakeSession()
    client = ReplitCRMClient("https://crm.example.com", "tok", session=session,
                             endpoints={"upsert_lead": "POST /api/v2/leads"})
    client.upsert_lead(_lead())
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://crm.example.com/api/v2/leads"


def test_bearer_token_is_attached():
    session = FakeSession()
    ReplitCRMClient("https://crm.example.com", "tok", session=session)
    assert session.headers["Authorization"] == "Bearer tok"


def test_raw_auth_scheme_sends_the_token_unwrapped():
    session = FakeSession()
    ReplitCRMClient("https://crm.example.com", "tok", session=session,
                    auth_scheme="raw", auth_header="X-API-Key")
    assert session.headers["X-API-Key"] == "tok"


def test_field_map_renames_onto_the_crm_schema():
    """The CRM's column names shouldn't force a code change."""
    session = FakeSession()
    client = ReplitCRMClient("https://crm.example.com", session=session,
                             field_map={"name": "company_name",
                                        "contact_email": "email"})
    client.upsert_lead(_lead())
    body = session.calls[0]["body"]
    assert body["company_name"] == "Haddon Point"
    assert body["email"] == "info@hp.com"
    assert "name" not in body


def test_trailing_slash_on_base_url_does_not_double_up():
    session = FakeSession()
    ReplitCRMClient("https://crm.example.com/", session=session).upsert_lead(_lead())
    assert "//api" not in session.calls[0]["url"].replace("https://", "")


def test_missing_base_url_fails_loudly():
    with pytest.raises(SystemExit):
        ReplitCRMClient("")


def test_server_error_propagates():
    session = FakeSession(status=500)
    client = ReplitCRMClient("https://crm.example.com", session=session)
    with pytest.raises(requests.HTTPError):
        client.upsert_lead(_lead())


def test_activity_records_the_email_that_went_out():
    session = FakeSession()
    client = ReplitCRMClient("https://crm.example.com", session=session)
    client.log_activity(ActivityPayload(
        external_id="k1", contact_email="info@hp.com", subject="Food truck night",
        step="intro", offered_dates=["Tuesday, September 22"]))
    body = session.calls[0]["body"]
    assert body["subject"] == "Food truck night"
    assert body["offered_dates"] == ["Tuesday, September 22"]


# -------------------------------------------------------------------- preview
def test_preview_sends_nothing_and_records_the_contract(capsys):
    client = PreviewCRMClient(base_url="https://crm.example.com")
    client.upsert_lead(_lead())
    out = capsys.readouterr().out
    assert "POST https://crm.example.com/api/crm/leads" in out
    assert "Haddon Point" in out
    assert len(client.calls) == 1


# -------------------------------------------------------------------- factory
def test_primary_resolves_to_the_replit_crm(cfg, store, monkeypatch):
    monkeypatch.setenv("CRM_BASE_URL", "https://crm.example.com")
    monkeypatch.setenv("CRM_API_TOKEN", "tok")
    assert build_primary(cfg, store).name == "replit"


def test_preview_flag_never_builds_a_live_client(cfg, store, monkeypatch):
    monkeypatch.delenv("CRM_BASE_URL", raising=False)
    # No base URL configured -- preview must still work rather than exiting.
    assert build_primary(cfg, store, preview=True).name == "preview"


def test_primary_none_disables_the_sink(cfg, store):
    cfg.raw["crm"]["primary"] = "none"
    assert build_primary(cfg, store) is None


def test_hubspot_mirror_is_skipped_without_a_token(cfg, store, monkeypatch):
    cfg.secrets.hubspot_token = ""
    assert build_hubspot(cfg, store) is None


def test_hubspot_mirror_is_skipped_when_disabled(cfg, store):
    cfg.raw["crm"]["hubspot"]["enabled"] = False
    cfg.secrets.hubspot_token = "tok"
    assert build_hubspot(cfg, store) is None


def test_hubspot_contacts_only_writes_no_companies_or_deals(cfg, store):
    """HubSpot is an archive now. It must not create deals or move pipeline."""
    cfg.secrets.hubspot_token = "tok"
    adapter = build_hubspot(cfg, store, contacts_only=True)
    calls = []

    adapter.client.upsert_contact = lambda c, company, owner: (
        calls.append(("contact", company)) or "c1")
    adapter.client.upsert_company = lambda *a, **k: calls.append(("company",))
    adapter.client.create_deal = lambda *a, **k: calls.append(("deal",))

    store.upsert_property(Property(key="k1", name="X"))
    store.upsert_contact(Contact(property_key="k1", email="a@x.com"))
    store.conn.commit()

    adapter.upsert_lead(LeadPayload(external_id="k1", name="X",
                                    contact_email="a@x.com"))
    assert calls == [("contact", "")]


def test_hubspot_contacts_only_logs_no_timeline_activity(cfg, store):
    cfg.secrets.hubspot_token = "tok"
    adapter = build_hubspot(cfg, store, contacts_only=True)
    assert adapter.log_activity(ActivityPayload(external_id="k",
                                                contact_email="a@x.com")) == ""
