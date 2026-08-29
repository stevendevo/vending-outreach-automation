"""Discovery via Google Places API (New).

Sweeps each configured market anchor with a set of text queries and folds the
results into the store. Deduplication happens on the normalized property key,
so overlapping market radii cost quota but never create duplicate rows.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Iterable, Iterator, Optional

import requests

from ..config import Config
from ..geo import drive_miles
from ..models import Property, property_key

log = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Ask for exactly what we use -- Places bills by requested field mask.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.primaryType",
])

# Places returns plenty of things that are not a rentable community.
EXCLUDE_NAME = re.compile(
    r"\b(storage|hotel|motel|inn|realty group llc|title|mortgage|insurance|"
    r"assisted living|nursing|rehab|hostel|dormitory|trailer|mobile home)\b",
    re.I,
)
MGMT_HINT = re.compile(r"\b(management|properties|property group|realty|residential)\b", re.I)


class PlacesClient:
    def __init__(self, api_key: str, session: Optional[requests.Session] = None):
        self.api_key = api_key
        self.session = session or requests.Session()

    def search_text(self, query: str, lat: float, lng: float, radius_m: int,
                    max_results: int = 60) -> Iterator[dict]:
        """Text search with paging. Places (New) caps a page at 20."""
        page_token = None
        fetched = 0
        while fetched < max_results:
            body: dict = {
                "textQuery": query,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": float(radius_m),
                    }
                },
                "pageSize": min(20, max_results - fetched),
            }
            if page_token:
                body["pageToken"] = page_token
            resp = self.session.post(
                SEARCH_URL,
                json=body,
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": FIELD_MASK + ",nextPageToken",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                log.warning("Places search failed (%s): %s", resp.status_code, resp.text[:300])
                return
            data = resp.json()
            places = data.get("places", []) or []
            for place in places:
                yield place
            fetched += len(places)
            page_token = data.get("nextPageToken")
            if not page_token or not places:
                return
            # Places requires a short pause before a page token is valid.
            time.sleep(2)


def _component(place: dict, ctype: str) -> str:
    for comp in place.get("addressComponents", []) or []:
        if ctype in (comp.get("types") or []):
            return comp.get("shortText") or comp.get("longText") or ""
    return ""


def place_to_property(place: dict) -> Optional[Property]:
    name = (place.get("displayName") or {}).get("text", "").strip()
    if not name or EXCLUDE_NAME.search(name):
        return None
    address = place.get("formattedAddress", "") or ""
    loc = place.get("location") or {}
    is_mgmt = bool(MGMT_HINT.search(name))
    return Property(
        key=property_key(name, address),
        name=name,
        address=address,
        city=_component(place, "locality") or _component(place, "sublocality"),
        state=_component(place, "administrative_area_level_1"),
        postal_code=_component(place, "postal_code"),
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        phone=place.get("nationalPhoneNumber", "") or "",
        website=place.get("websiteUri", "") or "",
        google_place_id=place.get("id", "") or "",
        rating=place.get("rating"),
        rating_count=place.get("userRatingCount", 0) or 0,
        source="places_mgmt" if is_mgmt else "places",
    )


def run_discovery(cfg: Config, store, markets: Optional[Iterable[str]] = None,
                  queries: Optional[Iterable[str]] = None) -> dict[str, int]:
    """Sweep every market x query combination. Returns a small run summary."""
    cfg.secrets.require("places_api_key")
    client = PlacesClient(cfg.secrets.places_api_key)
    disc = cfg.discovery
    biz = cfg.business

    wanted_markets = set(markets) if markets else None
    q_list = list(queries) if queries else list(disc["queries"])

    seen = 0
    added = 0
    skipped_far = 0
    skipped_filter = 0

    for market in disc["markets"]:
        if wanted_markets and market["name"] not in wanted_markets:
            continue
        for query in q_list:
            log.info("Searching %r near %s", query, market["name"])
            for place in client.search_text(
                query, market["lat"], market["lng"],
                disc["radius_meters"], disc["max_results_per_query"],
            ):
                seen += 1
                prop = place_to_property(place)
                if prop is None:
                    skipped_filter += 1
                    continue
                miles = drive_miles(biz["base_lat"], biz["base_lng"], prop.lat, prop.lng)
                if miles is not None and miles > disc["max_distance_miles"]:
                    skipped_far += 1
                    continue
                if store.upsert_property(prop):
                    added += 1
        store.conn.commit()

    store.conn.commit()
    return {
        "results_seen": seen,
        "new_properties": added,
        "skipped_out_of_range": skipped_far,
        "skipped_filtered": skipped_filter,
    }
