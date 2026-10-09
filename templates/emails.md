# Vending outreach email templates

Written in Steven's voice. Plain text. Fill in the `{placeholders}`, keep each email short, and include one ask.

**Auto-send (2026-10-09):** the routine sends these itself when every check in `routine/prompt.md` STEP 4 passes (no calendar or active-thread conflict for any date in the email, terms not contradicting what Steven already told the prospect, etc.). Otherwise the email stays a Gmail draft for Steven. Every email is tagged with the "Vending Outreach" label.

Rules:
- Only state facts from the website or real bookings. Mention a nearby town we've served only when that's true (see `service-area.md`).
- Refer to past clients by type and town ("an apartment community in Eagleville"), not by name, unless they've agreed to be a reference.
- **Tone (Steven's example, 2026-10-09):** short, warm and plain. Two or three short paragraphs, no pressure, no pricing in a cold first-touch. Example: "Just wanted to follow up and see if there might be an opportunity to bring Grilly Cheese out to one of your communities! We'd love to stop by for a food truck night or resident appreciation event. It's a fun, easy way to bring neighbors together, and we take care of everything from setup to cleanup. ... We'd be happy to work around whatever dates make the most sense for you. Hope we can put something together soon!"
- **Sales minimum (decided 2026-10-09, replaces "no minimum, no cost").** First-touch emails and follow-ups do NOT mention it (keep them friendly). State it in replies as soon as price, terms, cost or dates come up, and in every booking confirmation, for that property: Simple Menu **$600** per visit within 30 miles of Philadelphia, **$750** farther (`python3 routine/policy.py "Town, ST"`). Full Menu and Breakfast are $750 everywhere. Never say vending is "free" or "no cost". Never mention a deposit. Fill `{MinimumLine}` (replies and confirmations only) as:
  `One thing to know up front: our Simple Menu has a ${N} sales minimum per visit. Guests still order and pay individually at the truck, and if sales come in under ${N} (before tax and tips), the property covers the difference.`
  Short form for final notes: `(As a quick reminder, vending visits have a ${N} sales minimum; the property covers any shortfall.)`
- Every email below ends with the opt-out line before the signature. Don't drop it.

## Logging

BCC **crm@grillycheese.net** on every outreach email and reply so the Grilly CRM logs it. The Grilly CRM comes first; HubSpot is updated after.

## Signature

Do **not** write a sign-off. End each email right after the opt-out line, then append `templates/signature.html` (Steven's Gmail signature: "Thank you!", name, both phone numbers, site, Calendly line, logo). The Gmail API does not add it for you.

---

**Follow-ups are paused (2026-10-09):** do not send follow-up #1 or the final note until Steven turns them back on. The follow-up templates below stay for later.

## A. Apartment communities / property managers

### A1 · Initial
Subject: `Food truck night for {Property} residents?`

```
Hi {FirstName}!

I'm Steven with Grilly Cheese, the gourmet grilled cheese food truck (GrubHub named us one of the Top 6 grilled cheese spots in the country). We've done resident events around {nearby town we've served}, and I'd love to bring the truck out to {Property}.

A food truck night is a fun, easy way to bring neighbors together. We park, set up in about 30 minutes, and take care of everything from setup to cleanup, and residents simply order at the window.

Would you be open to a quick call, or should I send a couple of fall dates that might work?

If now isn't the right time, just let me know and I won't follow up.
```

### A2 · Follow-up #1 (5 business days, same thread)
Subject: `Re: Food truck night for {Property} residents?`

```
Hi {FirstName}!

Just floating this back up. A lot of communities use us for resident appreciation nights, and a fall weeknight dinner or a weekend lunch works great. If you tell me a couple of dates that look open, I'll check the truck's calendar.

If you'd rather not hear from us again, just reply and let me know — no hard feelings.
```

### A3 · Follow-up #2, final (7 business days after #1)
Subject: `Re: Food truck night for {Property} residents?`

```
Hi {FirstName}!

I don't want to crowd your inbox, so this is my last note for now. If a food truck night ever makes sense for {Property}, or for another community in your portfolio, just reply here or text me at 856-630-4357. I'd be glad to help.

If you'd rather not hear from us again, just reply and let me know — no hard feelings.
```

---

## B. Office parks / business campuses / landlords

### B1 · Initial
Subject: `Lunch food truck for {Campus} tenants?`

```
Hi {FirstName}!

I'm Steven with Grilly Cheese, the gourmet grilled cheese food truck (GrubHub named us one of the Top 6 grilled cheese spots in the country). We run lunches at business centers around {nearby town we've served}, and I think {Campus} would be a great fit.

It's an easy tenant perk: we park on-site for a lunch window, tenants order at the window, and we're fully self-contained (we serve 100+ people an hour and can provide a COI). No café or kitchen needed.

Would you be open to a trial lunch this fall? If you're not the right person for tenant events, I'd really appreciate a pointer to whoever is.

If now isn't the right time, just let me know and I won't follow up.
```

### B2 · Follow-up #1
Subject: `Re: Lunch food truck for {Campus} tenants?`

```
Hi {FirstName}!

Following up on a food truck lunch for {Campus}. One trial date is usually the easiest way to see how tenants respond, and I'm happy to work around your building's calendar. Would a weekday in the next few weeks work?

If you'd rather not hear from us again, just reply and let me know — no hard feelings.
```

### B3 · Follow-up #2, final
Subject: `Re: Lunch food truck for {Campus} tenants?`

```
Hi {FirstName}!

Last note from me on this. If a lunch truck or a tenant appreciation day ever makes sense for {Campus} or your other properties, reply here or text 856-630-4357 and I'll make it easy.

If you'd rather not hear from us again, just reply and let me know — no hard feelings.
```

---

## C. Re-engaging past contacts
Use this when Gmail shows we talked with the prospect before. Reference the real history and keep it honest.

Subject: `Grilly Cheese for {Property} again?`

```
Hi {FirstName}!

It's Steven from Grilly Cheese. We connected back in {month year} about a food truck for {event/property}. We're now doing regular resident nights at apartment communities and lunches at business parks around {nearby town}, and I'd love to get something on the calendar for {Property}.

Residents can buy their own food at the window, or you can host them with one of our catering packages, whichever works better for you. Would a quick call work?

If you'd rather not hear from us again, just reply and let me know — no hard feelings.
```
