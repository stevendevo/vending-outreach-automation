from bs4 import BeautifulSoup

from vending_outreach.enrich.website import (
    extract_management, extract_units, guess_name_and_title, rank_email, usable_email)


# ------------------------------------------------------------------ unit counts
def test_reads_unit_count_from_marketing_copy():
    assert extract_units("A vibrant community of 318 apartment homes") == 318
    assert extract_units("consisting of 248 units across four buildings") == 248
    assert extract_units("Our 1,100 residences offer...") == 1100


def test_ignores_floorplan_counts_and_absurd_numbers():
    assert extract_units("Choose from 6 units and 3 homes") is None
    assert extract_units("We manage 90000 units nationwide") is None


def test_takes_the_largest_plausible_count():
    assert extract_units("40 units now leasing. 412 apartment homes total.") == 412


# ------------------------------------------------------------------- management
def test_finds_the_management_company():
    assert extract_management("Professionally managed by Morgan Properties") == "Morgan Properties"
    assert extract_management("Managed by Bozzuto Management") == "Bozzuto Management"


def test_no_false_positive_management_match():
    assert extract_management("Welcome to our beautiful community") == ""


# ----------------------------------------------------------------------- emails
def test_rejects_noreply_and_infrastructure_addresses():
    for bad in ("noreply@x.com", "postmaster@x.com", "careers@x.com",
                "privacy@x.com", "maintenance@x.com"):
        assert not usable_email(bad, "x.com")


def test_rejects_free_mail_and_platform_domains():
    assert not usable_email("someone@gmail.com", "x.com")
    assert not usable_email("a@sentry.io", "x.com")


def test_accepts_a_leasing_office_address():
    assert usable_email("leasing@riverloft.com", "riverloft.com")


def test_role_mailbox_on_own_domain_outranks_a_stray_address():
    on_site = rank_email("leasing@riverloft.com", "riverloft.com")
    off_site = rank_email("john.smith@somethingelse.com", "riverloft.com")
    assert on_site > off_site


def test_ranking_is_bounded():
    assert 0 < rank_email("leasing@x.com", "x.com") <= 0.99


# ------------------------------------------------------------------ name/title
def test_pulls_a_name_and_title_from_around_the_email():
    html = """<div class="staff">
                <h3>Dana Whitfield</h3>
                <p>Community Manager</p>
                <a href="mailto:dana@riverloft.com">dana@riverloft.com</a>
              </div>"""
    first, last, title = guess_name_and_title(BeautifulSoup(html, "lxml"),
                                              "dana@riverloft.com")
    assert (first, last) == ("Dana", "Whitfield")
    assert title == "Community Manager"


def test_does_not_invent_a_name_from_boilerplate():
    html = '<p>Contact Us <a href="mailto:info@x.com">info@x.com</a></p>'
    first, _, _ = guess_name_and_title(BeautifulSoup(html, "lxml"), "info@x.com")
    assert first == ""


def test_missing_email_yields_nothing():
    soup = BeautifulSoup("<p>nothing here</p>", "lxml")
    assert guess_name_and_title(soup, "absent@x.com") == ("", "", "")
