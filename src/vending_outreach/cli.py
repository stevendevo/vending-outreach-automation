"""Command line entry point.

    python -m vending_outreach <command> [options]

The pipeline is a set of small, independently runnable stages so a bad run of
one never forces a re-run of the others:

    discover -> enrich -> score -> queue -> outreach -> sync -> report
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import REPO_ROOT, Config
from .crm.hubspot import HubSpotClient, sync_property
from .discovery.places import run_discovery
from .enrich.website import compute_portfolio_sizes, run_enrichment
from .models import Contact, Property, property_key
from .outreach.sequencer import Sequencer, enqueue_candidates, within_send_window
from .scoring import run_scoring
from .slots import format_dates, open_dates
from .store import DEFAULT_DB, Store

log = logging.getLogger("vending_outreach")


def _google(cfg: Config):
    """Imported lazily -- the offline stages must not require the Google stack."""
    from .outreach.google_client import GoogleClient

    cfg.secrets.require("sender_email")
    return GoogleClient(
        cfg.secrets.google_client_secrets,
        cfg.secrets.google_token_cache,
        cfg.secrets.sender_email,
    )


def _table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "(nothing)"
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    out = [" | ".join(c.ljust(widths[c]) for c in columns),
           "-+-".join("-" * widths[c] for c in columns)]
    for r in rows:
        out.append(" | ".join(str(r.get(c, ""))[:widths[c]].ljust(widths[c]) for c in columns))
    return "\n".join(out)


# --------------------------------------------------------------------- commands
def cmd_discover(args, cfg: Config, store: Store) -> int:
    stats = run_discovery(cfg, store, markets=args.market, queries=args.query)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_import(args, cfg: Config, store: Store) -> int:
    """Load properties from a CSV -- useful for a list you already own.

    Expected headers: name, address, city, state, postal_code, website, phone,
    unit_count, management_company (only `name` is required).
    """
    added = 0
    with open(args.path, newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            address = (row.get("address") or "").strip()
            prop = Property(
                key=property_key(name, address), name=name, address=address,
                city=(row.get("city") or "").strip(),
                state=(row.get("state") or "").strip(),
                postal_code=(row.get("postal_code") or "").strip(),
                website=(row.get("website") or "").strip(),
                phone=(row.get("phone") or "").strip(),
                management_company=(row.get("management_company") or "").strip(),
                unit_count=int(row["unit_count"]) if (row.get("unit_count") or "").isdigit() else None,
                source="csv",
            )
            if store.upsert_property(prop):
                added += 1
            email = (row.get("email") or "").strip().lower()
            if email:
                store.upsert_contact(Contact(
                    property_key=prop.key, email=email,
                    first_name=(row.get("first_name") or "").strip(),
                    last_name=(row.get("last_name") or "").strip(),
                    title=(row.get("title") or "").strip(),
                    source="csv", confidence=0.9,
                ))
    store.conn.commit()
    print(f"Imported {added} new properties from {args.path}")
    return 0


def cmd_enrich(args, cfg: Config, store: Store) -> int:
    stats = run_enrichment(store, limit=args.limit)
    groups = compute_portfolio_sizes(store)
    stats["management_groups"] = groups
    print(json.dumps(stats, indent=2))
    return 0


def cmd_score(args, cfg: Config, store: Store) -> int:
    stats = run_scoring(cfg, store)
    print(json.dumps(stats, indent=2))
    top = store.properties(
        "score >= ? ORDER BY score DESC LIMIT ?",
        (cfg.scoring["min_score_to_contact"], args.limit),
    )
    rows = [{"score": p.score, "name": p.name[:38], "city": p.city,
             "units": p.unit_count or "?", "why": p.score_reasons[:60]} for p in top]
    print()
    print(_table(rows, ["score", "name", "city", "units", "why"]))
    return 0


def cmd_queue(args, cfg: Config, store: Store) -> int:
    added = enqueue_candidates(cfg, store, limit=args.limit)
    print(f"Queued {added} contacts for outreach.")
    return 0


def cmd_slots(args, cfg: Config, store: Store) -> int:
    cal = cfg.calendar
    if args.offline:
        days = open_dates([], cal)
    else:
        google = _google(cfg)
        tz = ZoneInfo(cal["timezone"])
        now = datetime.now(tz)
        events = google.list_events(
            cal["calendar_id"], now.isoformat(),
            (now + timedelta(days=cal["horizon_days"] + 7)).isoformat(),
        )
        print(f"Read {len(events)} events from {cal['calendar_id']}")
        days = open_dates(events, cal, count=args.count)
    print("\nOpen vending dates:")
    for label in format_dates(days, cfg.offer):
        print(f"  - {label}")
    return 0


def cmd_outreach(args, cfg: Config, store: Store) -> int:
    mode = args.mode
    google = None
    if mode in ("draft", "live") or not args.offline:
        try:
            google = _google(cfg)
        except SystemExit:
            if mode != "dry-run":
                raise
            log.warning("No Google credentials; running fully offline.")

    if mode == "live":
        ok, why = within_send_window(cfg)
        if not ok and not args.ignore_window:
            print(f"Refusing to send: {why}")
            print("Re-run inside the window, or pass --ignore-window if you mean it.")
            return 1

    seq = Sequencer(cfg, store, google=google)
    results = seq.run(mode=mode, limit=args.limit, ignore_window=args.ignore_window)

    if args.show_bodies:
        for r in results:
            if r.get("body"):
                print("=" * 72)
                print(f"To: {r['email']}  [{r['step']}]  ({r['property']})")
                print(f"Subject: {r['subject']}\n")
                print(r["body"])
    print()
    print(_table(
        [{k: v for k, v in r.items() if k in ("email", "property", "step", "action", "reason")}
         for r in results],
        ["email", "property", "step", "action", "reason"],
    ))
    counts: dict[str, int] = {}
    for r in results:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    print(f"\n{len(results)} processed: {counts}")
    if mode == "dry-run":
        print("\nDry run -- nothing was sent or drafted. "
              "Use --mode draft to stage in Gmail, --mode live to send.")
    return 0


def cmd_sync(args, cfg: Config, store: Store) -> int:
    cfg.secrets.require("hubspot_token")
    client = HubSpotClient(cfg.secrets.hubspot_token)
    props = store.properties(
        "score >= ? ORDER BY score DESC LIMIT ?",
        (args.min_score or cfg.scoring["min_score_to_contact"], args.limit),
    )
    synced = 0
    for prop in props:
        try:
            res = sync_property(client, cfg, store, prop, create_deal=not args.no_deals)
            synced += 1
            print(f"  {prop.score:>3}  {prop.name[:44]:<44} company={res['company_id']} "
                  f"deal={res['deal_id'] or '-'}")
        except Exception as exc:
            log.error("Sync failed for %s: %s", prop.name, exc)
    print(f"\nSynced {synced}/{len(props)} properties to HubSpot portal "
          f"{cfg.hubspot['portal_id']}.")
    return 0


def cmd_report(args, cfg: Config, store: Store) -> int:
    counts = store.counts()
    print("Pipeline")
    print("--------")
    for k, v in counts.items():
        print(f"  {k:<14} {v}")

    rows = store.conn.execute(
        """SELECT s.step_key, s.mode, COUNT(*) n FROM sends s
           GROUP BY s.step_key, s.mode ORDER BY s.step_key"""
    ).fetchall()
    if rows:
        print("\nEmails by step")
        print("--------------")
        for r in rows:
            print(f"  {r['step_key']:<8} {r['mode']:<8} {r['n']}")

    top = store.properties("score > 0 ORDER BY score DESC LIMIT 15")
    if top:
        print("\nTop targets")
        print("-----------")
        print(_table(
            [{"score": p.score, "name": p.name[:40], "city": p.city,
              "units": p.unit_count or "?", "mgmt": (p.management_company or "-")[:24]}
             for p in top],
            ["score", "name", "city", "units", "mgmt"],
        ))
    return 0


def cmd_export(args, cfg: Config, store: Store) -> int:
    out = Path(args.path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = store.conn.execute(
        """SELECT p.score, p.name, p.address, p.city, p.state, p.unit_count,
                  p.management_company, p.portfolio_size, p.website, p.phone,
                  p.score_reasons, c.email, c.first_name, c.last_name, c.title,
                  COALESCE(o.status,'not queued') AS status
           FROM properties p
           LEFT JOIN contacts c ON c.property_key = p.key
           LEFT JOIN outreach o ON o.email = c.email
           WHERE p.score >= ?
           ORDER BY p.score DESC""",
        (args.min_score,),
    ).fetchall()
    with open(out, "w", newline="") as fh:
        if not rows:
            print("Nothing to export.")
            return 0
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


def cmd_suppress(args, cfg: Config, store: Store) -> int:
    path = REPO_ROOT / cfg.outreach["suppression_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if path.exists():
        existing = {l.strip().lower() for l in path.read_text().splitlines() if l.strip()}
    new = [v.lower() for v in args.value if v.lower() not in existing]
    with open(path, "a") as fh:
        for v in new:
            fh.write(v + "\n")
    for v in new:
        store.conn.execute(
            "UPDATE outreach SET status='stopped', notes='suppressed' WHERE email = ?", (v,)
        )
    store.conn.commit()
    print(f"Added {len(new)} entries to {path}")
    return 0


# ------------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vending-outreach",
        description="Find apartment communities and fill the Grilly Cheese calendar.",
    )
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite store")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="sweep Google Places for apartment communities")
    d.add_argument("--market", action="append", help="limit to a market name (repeatable)")
    d.add_argument("--query", action="append", help="override search queries (repeatable)")
    d.set_defaults(func=cmd_discover)

    i = sub.add_parser("import", help="load properties from a CSV")
    i.add_argument("path")
    i.set_defaults(func=cmd_import)

    e = sub.add_parser("enrich", help="crawl property sites for contacts and unit counts")
    e.add_argument("--limit", type=int, default=200)
    e.set_defaults(func=cmd_enrich)

    s = sub.add_parser("score", help="rank properties by fit")
    s.add_argument("--limit", type=int, default=25)
    s.set_defaults(func=cmd_score)

    q = sub.add_parser("queue", help="enqueue top-scoring contacts into the sequence")
    q.add_argument("--limit", type=int, default=100)
    q.set_defaults(func=cmd_queue)

    sl = sub.add_parser("slots", help="show open vending dates on the booking calendar")
    sl.add_argument("--count", type=int, default=10)
    sl.add_argument("--offline", action="store_true", help="skip Calendar, assume all open")
    sl.set_defaults(func=cmd_slots)

    o = sub.add_parser("outreach", help="work the outreach queue")
    o.add_argument("--mode", choices=["dry-run", "draft", "live"], default="dry-run")
    o.add_argument("--limit", type=int, default=25)
    o.add_argument("--show-bodies", action="store_true")
    o.add_argument("--offline", action="store_true", help="dry-run without Google access")
    o.add_argument("--ignore-window", action="store_true",
                   help="send outside the configured business-hours window")
    o.set_defaults(func=cmd_outreach)

    sy = sub.add_parser("sync", help="push properties/contacts/deals into HubSpot")
    sy.add_argument("--limit", type=int, default=50)
    sy.add_argument("--min-score", type=int, default=None)
    sy.add_argument("--no-deals", action="store_true")
    sy.set_defaults(func=cmd_sync)

    r = sub.add_parser("report", help="pipeline status")
    r.set_defaults(func=cmd_report)

    x = sub.add_parser("export", help="dump the target list to CSV")
    x.add_argument("--path", default="data/exports/targets.csv")
    x.add_argument("--min-score", type=int, default=0)
    x.set_defaults(func=cmd_export)

    su = sub.add_parser("suppress", help="never contact these addresses or domains")
    su.add_argument("value", nargs="+")
    su.set_defaults(func=cmd_suppress)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.load(args.config)
    store = Store(args.db)
    try:
        return args.func(args, cfg, store)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
