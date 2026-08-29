# Grilly Cheese — apartment vending outreach

Finds apartment communities and property-management groups in the Grilly Cheese
service area, works out which ones are worth pitching, and runs a personalized
email sequence that offers **real open dates from the booking calendar** — with
guardrails so it can't spam anyone or double-email a prospect.

The offer being pitched is resident-pay vending: the truck shows up, residents
buy their own dinner at the window, and the property backs it with a $1,050
sales guarantee that is refunded once sales clear it.

## Why this beats a mail-merge

- **It only pitches dates the truck can actually work.** Every email names three
  open midweek evenings pulled live from the `grill-e-vents` calendar, so nobody
  gets offered a night that's already booked or a week the truck is at the NC
  State Fair.
- **It triages.** There are thousands of communities in the market and time to
  personalize maybe 40 emails a day. Scoring decides which 40, and explains why.
- **It knows a portfolio when it sees one.** A property manager running twelve
  communities is one conversation worth twelve dates, and gets pitched that way.
- **It won't embarrass you.** Nothing sends without an explicit flag, replies
  stop the sequence, and there are daily and per-domain caps.

## Pipeline

```
discover → enrich → score → queue → outreach → sync → report
```

| Stage | What it does |
|---|---|
| `discover` | Sweeps Google Places across 15 market anchors (Philly, South/Central NJ, Wilmington, Bucks/Chester/Delco) for apartment communities and management companies |
| `enrich` | Crawls each property site for a named contact, door count, management company, and resident-event signals |
| `score` | Ranks 0–100 on doors, drive distance, portfolio size, event signals, review volume, and whether we have a human to write to |
| `queue` | Puts the top-scoring contacts into the sequence |
| `outreach` | Renders and sends the next due step for each contact |
| `sync` | Mirrors companies, contacts and deals into HubSpot |
| `report` | Funnel counts and the current top targets |

## Setup

```bash
./scripts/bootstrap.sh          # venv, deps, .env scaffold
```

Then fill in `.env`:

| Variable | What for |
|---|---|
| `GOOGLE_PLACES_API_KEY` | Property discovery. Enable **Places API (New)** |
| `HUBSPOT_ACCESS_TOKEN` | Private-app token with companies/contacts/deals read+write |
| `GOOGLE_OAUTH_CLIENT_SECRETS` | Desktop-app OAuth client JSON, for Gmail + Calendar |
| `SENDER_EMAIL` | `grillycheese@grillycheese.net` |

Authorize Google once (opens a browser, caches a token):

```bash
PYTHONPATH=src python -m vending_outreach slots
```

## Everyday use

```bash
# What dates are actually open?
python -m vending_outreach slots

# Find and rank new targets
python -m vending_outreach discover
python -m vending_outreach enrich --limit 150
python -m vending_outreach score

# See exactly what would go out, without sending anything
python -m vending_outreach queue
python -m vending_outreach outreach --mode dry-run --show-bodies

# Stage them as Gmail drafts to review and send by hand
python -m vending_outreach outreach --mode draft --limit 20

# Actually send
python -m vending_outreach outreach --mode live --limit 40

# Push to HubSpot, then check the funnel
python -m vending_outreach sync
python -m vending_outreach report
```

Already have a list? `python -m vending_outreach import my_list.csv`
(headers: `name,address,city,state,postal_code,website,phone,unit_count,management_company,email,first_name,last_name,title` — only `name` is required).

Nightly, once you trust it: `MODE=draft ./scripts/daily.sh` from cron.

## Safety rails

These are the reason this is safe to leave running. Each one has a test.

| Rail | Behavior |
|---|---|
| **Dry run by default** | `--mode dry-run` renders and logs but sends nothing. `draft` and `live` are opt-in |
| **No double-sends** | Sends are written to the audit log *before* the sequence advances; a crash costs a log row, never a duplicate email |
| **Replies stop everything** | Gmail is checked for an inbound reply before every follow-up. If Gmail can't be reached, the step defers rather than guessing |
| **Daily + per-domain caps** | 40/day overall, 3/day per domain, counted against the log so a restart can't blow past them |
| **Business-hours only** | Live sends refuse outside Mon–Fri 8:30–17:00 ET unless `--ignore-window` |
| **Suppression list** | `config/suppression.txt` takes addresses or bare domains; checked on every send. Add with `vending-outreach suppress <email|domain>` |
| **CAN-SPAM** | Every template carries the postal address and a working opt-out |
| **Minimum size** | Communities under 60 doors are skipped — they can't clear the guarantee |

Enrichment only collects addresses published on a property's own site, prefers
role mailboxes (`leasing@`, `events@`) over personal ones, and drops free-mail
and infrastructure addresses.

## Tuning

Almost everything worth changing is in `config/config.yaml`: markets and search
radius, scoring weights and thresholds, the sequence and its delays, caps, send
windows, preferred weekdays, lead time, and the HubSpot pipeline IDs.

Email copy is in `config/templates/` — four steps plus a shared signature.
Prose is written as one paragraph per line and hard-wrapped at render time, so
conditional blocks never leave ragged half-lines. Anything after `[[VERBATIM]]`
is left exactly as written.

## HubSpot

Writes into portal 6451718's existing **Event Quote Pipeline** rather than
inventing new objects:

- Properties → Companies (deduped on domain, then name)
- Leasing/community contacts → Contacts, associated to the company
- One deal per property, `Resident Vending — <name>`, opened in **Vending
  Request** and moved to **Vending Request - contacted** as the sequence runs

## Tests

```bash
PYTHONPATH=src python -m pytest tests/ -q
```

66 tests. The interesting ones are `test_sequencer.py` (every guardrail above)
and `test_real_calendar.py`, which runs the gap finder against a real snapshot
of the September–October 2026 booking calendar to prove it never offers a date
the truck is already committed to.
