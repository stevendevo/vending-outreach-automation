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
| `sync` | Pushes leads into the primary CRM, optionally mirroring contacts to HubSpot |
| `report` | Funnel counts and the current top targets |

## Running on Replit

This is built to run as a **Replit Scheduled Deployment**: one pass each
weekday morning that finds new targets and stages the day's emails as Gmail
drafts for you to skim and send.

### 1. Add a PostgreSQL database

In the Repl: **Tools → Database → create a PostgreSQL database.** That sets
`DATABASE_URL` for you.

This is not optional. Scheduled Deployments run on an **ephemeral filesystem** —
anything written to disk is gone by the next run. Without Postgres the tool
forgets who it already contacted and emails them again the next morning. With
`DATABASE_URL` set it uses Postgres; without it, a local SQLite file.

### 2. Mint a Google refresh token

Replit is headless, so the usual browser OAuth flow can't run there. Do it once
on your laptop:

```bash
python main.py auth
```

That opens a browser, then prints three values to paste into Replit Secrets.
The deployment refreshes its own access tokens from then on.

### 3. Set Secrets (Tools → Secrets)

| Secret | Required | What it unlocks |
|---|---|---|
| `DATABASE_URL` | yes | Remembering who was already contacted (set automatically in step 1) |
| `GOOGLE_OAUTH_CLIENT_ID` | yes | Gmail + Calendar |
| `GOOGLE_OAUTH_CLIENT_SECRET` | yes | Gmail + Calendar |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | yes | Gmail + Calendar |
| `SENDER_EMAIL` | yes | The From address |
| `GOOGLE_PLACES_API_KEY` | yes | Discovering new communities |
| `CRM_BASE_URL` | for sync | Your Replit CRM |
| `CRM_API_TOKEN` | for sync | Your Replit CRM |
| `HUBSPOT_ACCESS_TOKEN` | optional | Contact mirror only |

Then confirm everything landed:

```bash
python main.py doctor
```

It prints what is live, what is missing, and what each gap costs you. Secrets
are masked, never echoed.

### 4. Deploy

`.replit` already sets the Scheduled Deployment to:

```
python main.py daily --mode draft
```

Pick the schedule in the Deployments pane — weekday mornings around 8:30am ET
matches the send window in `config.yaml`. **Mode is `draft`**: emails are staged
in Gmail for review, not sent. Change to `live` once the copy has earned it.

The green Run button does a dry run and sends nothing.

### Workflows in the Repl sidebar

`Dry run` · `Check setup` · `Open dates` · `Preview CRM payloads` ·
`Stage drafts in Gmail` · `Tests`

## Local setup

```bash
./scripts/bootstrap.sh          # venv, deps, .env scaffold
python main.py auth             # one-time Google authorization
python main.py doctor
```

## Everyday use

```bash
# What dates are actually open?
python main.py slots

# Find and rank new targets
python main.py discover
python main.py enrich --limit 150
python main.py score

# See exactly what would go out, without sending anything
python main.py queue
python main.py outreach --mode dry-run --show-bodies

# Stage them as Gmail drafts to review and send by hand
python main.py outreach --mode draft --limit 20

# Actually send
python main.py outreach --mode live --limit 40

# Push to HubSpot, then check the funnel
python main.py sync
python main.py report
```

Already have a list? `python main.py import my_list.csv`
(headers: `name,address,city,state,postal_code,website,phone,unit_count,management_company,email,first_name,last_name,title` — only `name` is required).

Nightly on Replit: the Scheduled Deployment runs `python main.py daily --mode draft`.
Outside Replit: `MODE=draft ./scripts/daily.sh` from cron.

## Safety rails

These are the reason this is safe to leave running. Each one has a test.

| Rail | Behavior |
|---|---|
| **Dry run by default** | `--mode dry-run` renders and logs but sends nothing. `draft` and `live` are opt-in, and the scheduled job defaults to `draft` |
| **No double-sends** | Sends are written to the audit log *before* the sequence advances; a crash costs a log row, never a duplicate email |
| **Replies stop everything** | Gmail is checked for an inbound reply before every follow-up. If Gmail can't be reached, the step defers rather than guessing |
| **Daily + per-domain caps** | 40/day overall, 3/day per domain, counted against the log so a restart can't blow past them |
| **Business-hours only** | Live sends refuse outside Mon–Fri 8:30–17:00 ET unless `--ignore-window` |
| **Suppression list** | `config/suppression.txt` takes addresses or bare domains; checked on every send. Add with `vending-outreach suppress <email|domain>` |
| **CAN-SPAM** | Every template carries the postal address and a working opt-out |
| **Minimum size** | Communities under 60 doors are skipped — they can't clear the guarantee |
| **Persistent state** | On Replit, state lives in Postgres. `doctor` fails the check if `DATABASE_URL` is missing there, because an ephemeral store means re-emailing everyone |
| **Stage isolation** | A failing stage in the nightly run never stops the rest — including after emails have gone out |

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

## CRM

The primary sink is the **Replit-hosted CRM** alongside grillycheese.net.
HubSpot is kept only as a contact archive (`crm.hubspot.contacts_only: true`) —
no companies, no deals, no pipeline movement.

Endpoints and field names live in `config.yaml` under `crm.replit`, so pointing
this at whatever the CRM actually exposes is a config change, not a code change:

```yaml
crm:
  primary: replit
  replit:
    endpoints:
      upsert_lead:  "POST /api/crm/leads"
      log_activity: "POST /api/crm/activities"
    field_map:
      name: company_name      # rename our fields onto the CRM's columns
```

To see the exact JSON it would POST, without sending anything:

```bash
python main.py sync --preview
```

That output *is* the contract — hand it to whoever builds the endpoint. Leads
are keyed on `external_id` (our stable property key), so re-syncing updates the
same record rather than creating duplicates.

Set `crm.primary: hubspot` to fall back to the old behavior (companies, deals,
and the Vending Request pipeline stages in portal 6451718).

## Tests

```bash
python -m pytest tests/ -q

# Run the whole suite against a real Postgres, the way Replit runs it
TEST_DATABASE_URL=postgresql://... python -m pytest tests/ -q
```

117 tests, passing on both backends. The interesting ones:

- `test_sequencer.py` — every guardrail above
- `test_real_calendar.py` — the gap finder against a real snapshot of the
  September–October 2026 booking calendar, proving it never offers a date the
  truck is already committed to
- `test_daily.py` — a failing stage never stops the scheduled run's report
- `test_db.py` — the SQLite/Postgres dialect differences
- `test_google_auth.py` — the headless credential path
