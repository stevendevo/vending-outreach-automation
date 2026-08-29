from vending_outreach.config import Config
from vending_outreach.models import Contact, Property
from vending_outreach.outreach.templates import Renderer, reflow, service_window

DATES = ["Tuesday, September 22", "Wednesday, September 23", "Thursday, September 24"]


def flat(text: str) -> str:
    """Bodies are hard-wrapped, so a phrase can straddle a line break.
    Compare against a whitespace-normalized copy."""
    return " ".join(text.split())


def _render(template, **prop_kw):
    cfg = Config.load()
    prop = Property(key="k", name="Haddon Point", city="Pennsauken", **prop_kw)
    contact = Contact(property_key="k", email="a@x.com", first_name="Dana")
    return Renderer(cfg).render(template, prop, contact, DATES)


def test_every_template_renders_for_a_bare_property():
    """Templates must survive a property where nothing was enriched."""
    for name in ("01_intro.md", "02_bump.md", "03_proof.md", "04_close.md"):
        out = _render(name)
        assert out.subject
        assert "{{" not in out.body and "{%" not in out.body


def test_intro_names_the_open_dates():
    out = _render("01_intro.md", unit_count=412)
    for d in DATES:
        assert d in out.body


def test_guarantee_is_formatted_with_a_comma():
    assert "$1,050" in _render("01_intro.md").body


def test_food_truck_history_changes_the_pitch():
    proven = flat(_render("01_intro.md", unit_count=412, hosts_food_trucks=True).body)
    plain = flat(_render("01_intro.md", unit_count=412).body)
    assert "already know how these go" in proven
    assert "already know how these go" not in plain
    # The generic unit-count line is replaced, not duplicated.
    assert "more than enough foot traffic" in plain
    assert "more than enough foot traffic" not in proven


def test_portfolio_line_only_appears_for_multi_property_managers():
    single = flat(_render("03_proof.md").body)
    multi = flat(_render("03_proof.md", portfolio_size=8,
                         management_company="Morgan Properties").body)
    assert "rotation across" not in single
    assert "rotation across the rest of the Morgan Properties" in multi


def test_can_spam_requirements_are_present_in_every_email():
    """Cold commercial email needs a postal address and a working opt-out."""
    for name in ("01_intro.md", "02_bump.md", "03_proof.md", "04_close.md"):
        body = _render(name).body
        assert "Marlton, NJ" in flat(body)
        assert "unsubscribe" in body.lower()


def test_no_line_is_absurdly_long():
    body = _render("01_intro.md", unit_count=412).body
    assert max(len(l) for l in body.splitlines()) <= 82


def test_reflow_leaves_bullets_alone():
    text = "Some prose here.\n\n  • one\n  • two"
    assert "  • one\n  • two" in reflow(text)


def test_reflow_preserves_the_verbatim_signature():
    text = "Prose.\n\n[[VERBATIM]]\nThank you!\nSteven\n(c) 856-630-4357"
    out = reflow(text)
    assert "Thank you!\nSteven\n(c) 856-630-4357" in out


def test_service_window_reads_naturally():
    assert service_window({"default_start_local": "17:00",
                           "default_end_local": "19:00"}) == "5-7 PM"
