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

**Sending (as of 2026-09-30):** first-touch emails and scheduled follow-ups (#1, #2) send automatically — up to 10/day, Mon-Fri 9am-5pm ET only, always BCC'd to crm@grillycheese.net, and always ending with an opt-out line. Anything that needs Steven's judgment stays a draft for him to review and send: replies from a prospect who wrote back, anything involving a booking/date/price, and inbound leads from the website. See `routine/prompt.md` (STEP 4) for the exact rules and exceptions.
