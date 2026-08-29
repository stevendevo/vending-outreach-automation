"""Template rendering.

Each template is a Markdown file with a YAML front-matter block holding the
subject line. Both subject and body go through Jinja so the same personalization
variables work in either.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..config import REPO_ROOT, Config
from ..models import Contact, Property

TEMPLATE_DIR = REPO_ROOT / "config" / "templates"
FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class RenderedEmail:
    subject: str
    body: str
    offered_dates: list[str]


def _format_time(hhmm: str) -> str:
    dt = datetime.strptime(hhmm, "%H:%M")
    return dt.strftime("%-I:%M %p").replace(":00 ", " ")


VERBATIM = "[[VERBATIM]]"
WRAP_WIDTH = 78
BULLET = re.compile(r"^\s*[•\-\*]\s")


def reflow(text: str, width: int = WRAP_WIDTH) -> str:
    """Rewrap prose paragraphs so conditional Jinja blocks don't leave ragged
    half-lines. Bullet lists keep their own line breaks, and everything after
    the [[VERBATIM]] marker (the signature) is left exactly as written."""
    head, sep, tail = text.partition(VERBATIM)
    blocks = []
    for block in head.split("\n\n"):
        lines = [l for l in block.split("\n")]
        if any(BULLET.match(l) for l in lines):
            blocks.append("\n".join(l.rstrip() for l in lines if l.strip()))
            continue
        joined = " ".join(l.strip() for l in lines if l.strip())
        if not joined:
            continue
        blocks.append(textwrap.fill(joined, width=width,
                                    break_long_words=False,
                                    break_on_hyphens=False))
    out = "\n\n".join(blocks)
    if sep:
        out = out.rstrip() + "\n\n" + tail.lstrip("\n")
    return out


def service_window(offer: dict) -> str:
    """"5-7 PM" -- how it reads in an email."""
    start = _format_time(offer["default_start_local"])
    end = _format_time(offer["default_end_local"])
    return f"{start}-{end}".replace(" AM-", "-").replace(" PM-", "-")


class Renderer:
    def __init__(self, cfg: Config, template_dir: Path = TEMPLATE_DIR):
        self.cfg = cfg
        self.dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.dir)),
            undefined=StrictUndefined,
            trim_blocks=False,
            lstrip_blocks=False,
            keep_trailing_newline=True,
        )

    def _context(self, prop: Property, contact: Contact,
                 offered_dates: list[str]) -> dict[str, Any]:
        offer = dict(self.cfg.offer)
        offer["service_window"] = service_window(self.cfg.offer)
        offer["guarantee_display"] = f"${offer['sales_guarantee_usd']:,}"
        return {
            "business": self.cfg.business,
            "offer": offer,
            "property": prop,
            "contact": contact,
            "offered_dates": offered_dates,
        }

    def render(self, template_name: str, prop: Property, contact: Contact,
               offered_dates: list[str]) -> RenderedEmail:
        raw = (self.dir / template_name).read_text()
        meta: dict = {}
        m = FRONT_MATTER.match(raw)
        if m:
            meta = yaml.safe_load(m.group(1)) or {}
            raw = raw[m.end():]

        ctx = self._context(prop, contact, offered_dates)
        subject = self.env.from_string(str(meta.get("subject", ""))).render(**ctx).strip()
        body = self.env.from_string(raw).render(**ctx)
        # Jinja's conditional blocks leave ragged blank lines and half-width
        # lines; reflow so the email doesn't look machine-made.
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        body = reflow(body).strip() + "\n"
        return RenderedEmail(subject=subject, body=body, offered_dates=offered_dates)
