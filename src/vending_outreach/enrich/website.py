"""Website enrichment.

For each discovered property we fetch a handful of pages and pull out the three
things that decide whether it is worth an email: who to write to, how many
doors are behind them, and whether the community already does resident events.

Deliberately conservative: only addresses published on the property's own site
are collected, role addresses are preferred over personal ones, and anything
that looks like a resident or vendor address is dropped.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import Contact, Property
from ..store import utcnow

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (compatible; GrillyCheeseOutreach/1.0; "
      "+https://www.grillycheese.net)")

# Pages most likely to carry a leasing/community contact.
CANDIDATE_PATHS = ["", "/contact", "/contact-us", "/about", "/about-us",
                   "/team", "/our-team", "/leasing", "/management", "/amenities"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Role mailboxes that reach the leasing office -- our best first target.
ROLE_PREFIXES = ("leasing", "info", "manager", "management", "office", "hello",
                 "contact", "community", "lifestyle", "events", "concierge")

# Never contact these: vendor spam traps, personal-ish, or legal/HR.
BAD_PREFIXES = ("noreply", "no-reply", "donotreply", "postmaster", "abuse",
                "webmaster", "privacy", "legal", "careers", "jobs", "hr",
                "maintenance", "press", "media", "unsubscribe")
BAD_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com",
               "squarespace.com", "gmail.com", "yahoo.com", "hotmail.com",
               "aol.com", "outlook.com", "icloud.com")

# "312 apartment homes", "consisting of 248 units", "1,100-unit community"
# The comma-grouped alternative must come first so "1,100" is not read as "100".
UNIT_RE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d{2,4})\s*[-\s]?(?:apartment homes|apartment residences|"
    r"apartments|units|residences|homes|doors)\b", re.I)

EVENT_RE = re.compile(
    r"\b(resident events?|community events?|resident appreciation|social calendar|"
    r"events calendar|lifestyle director|community manager|resident activities|"
    r"monthly events?|happy hour)\b", re.I)
FOOD_TRUCK_RE = re.compile(r"\bfood truck", re.I)

TITLE_HINTS = ("community manager", "property manager", "lifestyle director",
               "resident experience", "leasing manager", "general manager",
               "regional manager", "assistant manager", "events coordinator",
               "activities director", "director of marketing")

MGMT_RE = re.compile(
    r"(?:[Mm]anaged by|[Aa] community of|[Pp]art of)\s+"
    r"([A-Z][A-Za-z&.'\-]*(?:\s+[A-Z][A-Za-z&.'\-]*){0,4}?\s+"
    r"(?:Properties|Property Management|Management|Residential|Realty|"
    r"Communities|Group|Partners|Companies))",
)


def _clean_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def fetch(url: str, session: requests.Session, timeout: int = 15) -> Optional[str]:
    try:
        resp = session.get(url, timeout=timeout, headers={"User-Agent": UA},
                           allow_redirects=True)
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and "html" in ctype:
            return resp.text
    except requests.RequestException as exc:
        log.debug("fetch failed %s: %s", url, exc)
    return None


def usable_email(email: str, site_domain: str) -> bool:
    email = email.lower().strip(".,;:'\"")
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if any(local.startswith(b) for b in BAD_PREFIXES):
        return False
    if domain in BAD_DOMAINS:
        return False
    if any(domain.endswith(ext) for ext in (".png", ".jpg", ".gif", ".webp", ".svg")):
        return False
    # Free-mail addresses on a property site are almost always a resident or a
    # vendor, not the leasing office.
    if not site_domain:
        return domain not in BAD_DOMAINS
    return True


def rank_email(email: str, site_domain: str) -> float:
    """Higher is better. Role mailbox on the property's own domain wins."""
    local, _, domain = email.lower().partition("@")
    score = 0.35
    if site_domain and domain == site_domain:
        score += 0.35
    if any(local.startswith(p) for p in ROLE_PREFIXES):
        score += 0.25
    # A person-shaped local part is fine but slightly riskier to cold-email.
    if "." in local and not any(local.startswith(p) for p in ROLE_PREFIXES):
        score += 0.05
    return round(min(score, 0.99), 2)


def extract_units(text: str) -> Optional[int]:
    """Largest plausible door count mentioned on the page."""
    best = None
    for raw in UNIT_RE.findall(text):
        try:
            n = int(raw.replace(",", ""))
        except ValueError:
            continue
        # Below 20 is usually a floorplan count; above 5000 is a typo or a
        # portfolio-wide number, not this property.
        if 20 <= n <= 5000 and (best is None or n > best):
            best = n
    return best


def extract_management(text: str) -> str:
    m = MGMT_RE.search(text)
    return m.group(1).strip() if m else ""


def guess_name_and_title(soup: BeautifulSoup, email: str) -> tuple[str, str, str]:
    """Look near the email for a person's name and role."""
    node = soup.find(string=re.compile(re.escape(email), re.I))
    if node is None:
        return "", "", ""
    # Walk up a couple of levels and read the surrounding block.
    block = node.parent
    for _ in range(3):
        if block is None or len(block.get_text(" ", strip=True)) > 40:
            break
        block = block.parent
    context = block.get_text(" ", strip=True) if block else ""
    title = next((t for t in TITLE_HINTS if t in context.lower()), "")
    # A name is two or three capitalized words not part of the title.
    name_m = re.search(r"\b([A-Z][a-z]{1,15})\s+([A-Z][a-z]{1,20})\b", context)
    first, last = (name_m.group(1), name_m.group(2)) if name_m else ("", "")
    if first.lower() in ("contact", "email", "our", "the", "meet", "about"):
        first, last = "", ""
    return first, last, title.title()


def enrich_property(prop: Property, session: requests.Session,
                    max_pages: int = 5) -> tuple[Property, list[Contact]]:
    """Fetch a few pages of the property site and fill in what we can find."""
    if not prop.website:
        return prop, []

    site_domain = _clean_domain(prop.website)
    corpus: list[str] = []
    email_hits: Counter[str] = Counter()
    soups: list[BeautifulSoup] = []

    base = prop.website.rstrip("/")
    for path in CANDIDATE_PATHS[:max_pages + 4]:
        if len(corpus) >= max_pages:
            break
        html = fetch(urljoin(base + "/", path.lstrip("/")) if path else base, session)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        soups.append(soup)
        text = soup.get_text(" ", strip=True)
        corpus.append(text)
        # mailto: links are higher-signal than free text.
        for a in soup.select('a[href^="mailto:"]'):
            addr = a["href"][7:].split("?")[0].strip().lower()
            if usable_email(addr, site_domain):
                email_hits[addr] += 3
        for addr in EMAIL_RE.findall(html):
            addr = addr.lower()
            if usable_email(addr, site_domain):
                email_hits[addr] += 1

    blob = " ".join(corpus)
    if blob:
        prop.unit_count = prop.unit_count or extract_units(blob)
        prop.management_company = prop.management_company or extract_management(blob)
        prop.event_signal = bool(EVENT_RE.search(blob))
        prop.hosts_food_trucks = bool(FOOD_TRUCK_RE.search(blob))

    contacts: list[Contact] = []
    # Take the best few addresses; more than that is spraying, not outreach.
    ranked = sorted(email_hits, key=lambda e: (-rank_email(e, site_domain), -email_hits[e]))
    for email in ranked[:3]:
        first = last = title = ""
        for soup in soups:
            first, last, title = guess_name_and_title(soup, email)
            if first or title:
                break
        contacts.append(Contact(
            property_key=prop.key, email=email, first_name=first, last_name=last,
            title=title, source="website", confidence=rank_email(email, site_domain),
        ))
    return prop, contacts


def run_enrichment(store, limit: int = 200) -> dict[str, int]:
    session = requests.Session()
    stats = {"processed": 0, "with_contact": 0, "with_units": 0, "no_website": 0}
    for prop in store.properties_needing_enrichment(limit):
        stats["processed"] += 1
        if not prop.website:
            stats["no_website"] += 1
            store.update_property(prop.key, enriched_at=utcnow())
            continue
        prop, contacts = enrich_property(prop, session)
        store.update_property(
            prop.key,
            unit_count=prop.unit_count,
            management_company=prop.management_company,
            event_signal=prop.event_signal,
            hosts_food_trucks=prop.hosts_food_trucks,
            enriched_at=utcnow(),
        )
        for c in contacts:
            store.upsert_contact(c)
        if contacts:
            stats["with_contact"] += 1
        if prop.unit_count:
            stats["with_units"] += 1
        store.conn.commit()
    return stats


def compute_portfolio_sizes(store) -> int:
    """A manager running 12 communities is one conversation worth 12 dates.
    Count properties per management company and stamp it on each row."""
    rows = store.conn.execute(
        """SELECT management_company AS mc, COUNT(*) AS n
           FROM properties WHERE management_company != '' GROUP BY management_company"""
    ).fetchall()
    for row in rows:
        store.conn.execute(
            "UPDATE properties SET portfolio_size = ? WHERE management_company = ?",
            (row["n"], row["mc"]),
        )
    store.conn.commit()
    return len(rows)
