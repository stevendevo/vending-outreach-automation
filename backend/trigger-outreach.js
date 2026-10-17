// Fires the "Grilly Cheese vending outreach" Claude Code routine from the
// grillycheese.net backend. Node 18+ (built-in fetch), no dependencies.
//
// Required secrets (Replit → Secrets), never commit them:
//   ROUTINE_FIRE_URL    https://api.anthropic.com/v1/claude_code/routines/<trig_id>/fire
//   ROUTINE_FIRE_TOKEN  token from claude.ai/code/routines → routine → Edit → API trigger
//   OUTREACH_ADMIN_KEY  any long random string; required to call the admin endpoint

// Each fire uses one run from the account's daily routine cap, so throttle.
const MIN_INTERVAL_MS = 10 * 60 * 1000; // manual/research runs
const MAX_LEAD_FIRES_PER_DAY = 10; // public form submissions (spam guard)
let lastFiredAt = 0;
let leadDay = "";
let leadFires = 0;

async function fireOutreach(payload = {}) {
  const now = Date.now();
  if (payload.mode === "lead") {
    const today = new Date(now).toISOString().slice(0, 10);
    if (today !== leadDay) {
      leadDay = today;
      leadFires = 0;
    }
    if (leadFires >= MAX_LEAD_FIRES_PER_DAY) {
      return { skipped: true, reason: "daily lead trigger limit reached" };
    }
    leadFires++;
  } else if (now - lastFiredAt < MIN_INTERVAL_MS) {
    return { skipped: true, reason: "fired less than 10 minutes ago" };
  }

  const res = await fetch(process.env.ROUTINE_FIRE_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.ROUTINE_FIRE_TOKEN}`,
      "anthropic-beta": "experimental-cc-routine-2026-04-01",
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    },
    // The routine reads `text` as JSON data: mode, town, segment, count, lead.
    body: JSON.stringify({ text: JSON.stringify(payload) }),
  });

  if (!res.ok) {
    throw new Error(`Routine fire failed: ${res.status} ${await res.text()}`);
  }
  if (payload.mode !== "lead") lastFiredAt = now;
  return res.json(); // { type, claude_code_session_id, claude_code_session_url }
}

// Express wiring. Call registerOutreachRoutes(app) from the server entry file.
function registerOutreachRoutes(app) {
  // Admin/manual trigger, e.g. from a dashboard button or a cron job:
  //   curl -X POST https://www.grillycheese.net/api/outreach/run \
  //     -H "x-admin-key: $OUTREACH_ADMIN_KEY" -H "Content-Type: application/json" \
  //     -d '{"mode":"research","town":"Cherry Hill, NJ","segment":"apartments","count":10}'
  app.post("/api/outreach/run", async (req, res) => {
    if (req.get("x-admin-key") !== process.env.OUTREACH_ADMIN_KEY) {
      return res.status(401).json({ error: "unauthorized" });
    }
    const { mode, town, segment, count } = req.body || {};
    try {
      res.json(await fireOutreach({ mode, town, segment, count }));
    } catch (err) {
      res.status(502).json({ error: err.message });
    }
  });
}

// Call from an existing vending-inquiry form handler after the lead is saved.
// Pass only the form fields; the routine drafts a reply but never sends it.
async function fireOutreachForLead(lead) {
  const { name, email, organization, property, town, phone, message } = lead;
  return fireOutreach({
    mode: "lead",
    lead: { name, email, organization, property, town, phone, message },
  });
}

module.exports = { fireOutreach, fireOutreachForLead, registerOutreachRoutes };
