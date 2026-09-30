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
| `routine/prompt.md` | The routine's instructions (daily schedule + API trigger) |
| `routine/SETUP.md` | How to create the claude.ai routine and wire the website backend to trigger it |
| `backend/trigger-outreach.js` | Node/Express helper so grillycheese.net can fire the routine |

**Rules the routine follows:** It only uses emails published on official pages or found in real past correspondence, never guessed ones. Apartment and office-park vending has no minimum and no cost to the property, and outreach never mentions a deposit.

**Sending (as of 2026-09-30):** Gmail drafts only — the routine never sends email on its own. Every draft (first-touch, both follow-ups, and every reply) is BCC'd to crm@grillycheese.net, ends with an opt-out line, and gets the **"Vending Outreach"** Gmail label so it's easy to find and tell apart from Steven's other mail. He reviews and sends each one himself.
