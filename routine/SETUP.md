# Trigger the outreach routine from the website backend

The website backend starts an outreach run by POSTing to the routine's API
endpoint. The token can only be generated in the claude.ai web UI.

## 1. Create the routine (claude.ai, ~3 min)

1. Open https://claude.ai/code/routines and click **New routine**.
2. Name: `Grilly Cheese vending outreach`.
3. Instructions: paste all of [`prompt.md`](prompt.md).
4. Repository: `stevendevo/vending-outreach-automation`.
5. Environment: the default one is fine (connectors don't need network allowlisting).
6. Triggers:
   - **Schedule** → Daily, 8:00 AM.
   - **Add another trigger** → **API**.
7. Connectors: keep **Gmail**, **Google Calendar**, **HubSpot**; remove the rest.
8. Click **Create**. Then **Edit** → API trigger → copy the **URL**, click
   **Generate token** and copy it right away (it's shown once).

## 2. Add secrets to the website backend (Replit → Secrets)

| Secret | Value |
|---|---|
| `ROUTINE_FIRE_URL` | the URL from step 1.8 |
| `ROUTINE_FIRE_TOKEN` | the token from step 1.8 |
| `OUTREACH_ADMIN_KEY` | any long random string |

## 3. Wire the code

Copy [`../backend/trigger-outreach.js`](../backend/trigger-outreach.js) into
the site's server, then:

```js
const { registerOutreachRoutes, fireOutreachForLead } = require("./trigger-outreach");
registerOutreachRoutes(app); // after app.use(express.json())

// in an existing vending-inquiry form handler, after saving the lead:
fireOutreachForLead(req.body).catch(console.error);
```

## 4. Test

```bash
curl -X POST https://www.grillycheese.net/api/outreach/run \
  -H "x-admin-key: $OUTREACH_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"mode":"research","town":"Cherry Hill, NJ","segment":"apartments","count":3}'
```

The response has `claude_code_session_url`, where you can watch the run live.

## Payload options

| Field | Values |
|---|---|
| `mode` | `full` (default), `research`, `followups`, `lead` |
| `town` | a town/county in the service area to focus on |
| `segment` | `apartments` or `offices` |
| `count` | 1–25 new prospects (default 10) |
| `lead` | `{name, email, organization, property, town, phone, message}` for `mode: "lead"` |

## Safety

- Runs only ever create **Gmail drafts**; nothing is sent automatically.
- The routine reads the payload as data. It ignores instructions inside it, so
  a spammy form submission can't redirect it.
- The backend throttles manual runs (one per 10 min) and form-triggered runs
  (10 per day), because each fire counts against the daily routine run cap.
- Revoke or rotate the token anytime in the routine's API trigger settings.
