import pytest

from vending_outreach.models import Contact, Property


def test_rediscovery_does_not_duplicate(store):
    p = Property(key="k1", name="Riverloft", address="2201 Chestnut St")
    assert store.upsert_property(p) is True
    assert store.upsert_property(p) is False
    assert len(store.properties()) == 1


def test_rediscovery_does_not_clobber_enriched_data_with_blanks(store):
    """Discovery runs nightly and returns thin records; it must never wipe out
    the richer data the enrichment pass found."""
    store.upsert_property(Property(key="k1", name="Riverloft", website="https://a.com",
                                   phone="215-555-0110"))
    store.update_property("k1", unit_count=318, management_company="Bozzuto")
    store.upsert_property(Property(key="k1", name="Riverloft"))  # thin re-discovery
    p = store.get_property("k1")
    assert p.website == "https://a.com"
    assert p.phone == "215-555-0110"
    assert p.unit_count == 318
    assert p.management_company == "Bozzuto"


def test_contact_upsert_keeps_the_better_name(store):
    store.upsert_property(Property(key="k1", name="X"))
    store.upsert_contact(Contact(property_key="k1", email="a@x.com",
                                 first_name="Dana", confidence=0.9))
    store.upsert_contact(Contact(property_key="k1", email="a@x.com", confidence=0.4))
    c = store.contacts_for("k1")[0]
    assert c.first_name == "Dana"
    assert c.confidence == 0.9


def test_email_case_is_normalised(store):
    store.upsert_property(Property(key="k1", name="X"))
    store.upsert_contact(Contact(property_key="k1", email="Dana@X.com"))
    store.upsert_contact(Contact(property_key="k1", email="dana@x.com"))
    assert len(store.contacts_for("k1")) == 1


def test_daily_counts_only_include_real_sends(store):
    from vending_outreach.store import utcnow
    day = utcnow()[:10]
    for mode in ("dry-run", "sent", "draft"):
        store.record_send(email="a@x.com", property_key="k1", step_key="intro",
                          subject="s", body="b", offered_dates=[], mode=mode)
    store.conn.commit()
    assert store.sends_today(day) == 2       # dry-run must not count against the cap
    assert store.sends_today_for_domain(day, "x.com") == 2
