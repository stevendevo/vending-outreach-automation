# vending-outreach-automation

Daily outreach campaign that gets the **Grilly Cheese** food truck booked for vending at **apartment communities / property management groups** and **office parks / business campuses** in the area where we already operate. With vending, residents or employees buy their own food at the window.

| File | What it is |
|---|---|
| `site/index.html` | Landing page: "Food Truck Nights for Apartment Communities & Office Parks" (black + orange, self-contained) |
| `assets/one-pager.html` | Printable leave-behind (print to PDF, letter size) |
| `templates/emails.md` | Initial email + 2 follow-ups for apartments and for offices, plus a re-engagement email for past contacts |
| `service-area.md` | Towns we serve, rebuilt from Google Calendar, Gmail and the website |
| `prospects.csv` | Every prospect, with its source URL, status and next step (used to avoid duplicates) |
| `outreach-log.md` | One entry per run |
| `dashboard/` | Mobile dashboard of all prospects. `python3 dashboard/build.py` rebuilds `index.html` from `prospects.csv` (template in `template.html`) |
| `routine/prompt.md` | The routine's instructions (daily schedule + API trigger) |
| `routine/SETUP.md` | How to create the claude.ai routine and wire the website backend to trigger it |
| `backend/trigger-outreach.js` | Node/Express helper so grillycheese.net can fire the routine |

**Rules the routine follows:** It only uses emails published on official pages or found in real past correspondence, never guessed ones. **Sales minimum (2026-10-09):** Simple Menu $600 per visit within 30 miles of Philadelphia, $750 farther; Full Menu and Breakfast $750 everywhere (`routine/policy.py`, tests: `python3 routine/test_policy.py`). Outreach never mentions a deposit and never calls vending "free".

**Sending (as of 2026-10-09): auto-send is ON.** The routine sends first-touch emails, follow-ups and replies itself when every check in `routine/prompt.md` STEP 4 passes: no calendar conflict or active client thread for any date in the email (Best Food Trucks auto-apply and cancellation emails are ignored), terms that don't contradict what Steven already told the prospect, a known recipient email, a non-borderline distance, and a routine question (price pushback, discounts, contracts and anything unusual are held). Weekdays only, at most 20 sends per run. Anything that fails a check stays a Gmail draft for Steven and is listed in the run summary. Every email is BCC'd to crm@grillycheese.net, ends with the opt-out line and Steven's signature (`templates/signature.html`), and gets the **"Vending Outreach"** Gmail label. Opt-outs are honored immediately.

`assets/brandywine-vending-menus.pdf` is the 3-page vending menu sent to Brandywine (Standard Lunch has no guarantee there; Full Menu and Breakfast: $750 guaranteed sales per visit). Brandywine's Standard Lunch $0 minimum was offered before the 2026-10-09 policy, so its thread is on hold for Steven.
