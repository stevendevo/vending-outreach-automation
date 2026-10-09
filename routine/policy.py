"""Sales-minimum policy for vending outreach (Steven, 2026-10-09).

Within 30 miles of Philadelphia (straight line from City Hall): the Simple Menu (a.k.a. Standard Lunch)
has a $600 sales minimum per visit; the Full Menu and Breakfast keep their $750 minimum.
Further than 30 miles: $750 minimum across the board.

Usage:  python3 routine/policy.py "Union, NJ" "Bryn Mawr, PA"
Towns within 3 miles of the 30-mile line are "borderline": the minimum is None and the routine must NOT
auto-send for them (Steven decides; straight-line distance can be well off the real drive).

Add a town to TOWNS (lat, lon) before drafting for it; unknown towns raise KeyError so a prospect is never
quoted the wrong minimum.
"""
import math
import sys

PHILLY = (39.9526, -75.1652)  # City Hall
RADIUS_MILES = 30
BORDERLINE_MILES = 3
NEAR_SIMPLE_MENU = 600
FAR_ALL = 750
FULL_MENU = 750

TOWNS = {
    "philadelphia, pa": (39.9526, -75.1652), "east norriton, pa": (40.1445, -75.3466), "bryn mawr, pa": (40.0229, -75.3157),
    "plymouth meeting, pa": (40.1021, -75.2749), "conshohocken, pa": (40.0793, -75.3016), "radnor, pa": (40.0460, -75.3599),
    "berwyn, pa": (40.0440, -75.4380), "king of prussia, pa": (40.1013, -75.3836), "blue bell, pa": (40.1523, -75.2663),
    "malvern, pa": (40.0362, -75.5138), "horsham, pa": (40.1785, -75.1285), "eagleville, pa": (40.1520, -75.4030),
    "chester, pa": (39.8496, -75.3557), "souderton, pa": (40.3117, -75.3238), "hatfield, pa": (40.2793, -75.2993),
    "newtown, pa": (40.2290, -74.9371), "mount laurel, nj": (39.9340, -74.8910), "clementon, nj": (39.8112, -74.9833),
    "cherry hill, nj": (39.9348, -75.0307), "marlton, nj": (39.8912, -74.9218), "collingswood, nj": (39.9184, -75.0718),
    "pennsauken, nj": (39.9560, -75.0585), "turnersville, nj": (39.7701, -75.0577), "medford, nj": (39.9185, -74.8266),
    "swedesboro, nj": (39.7471, -75.3105), "princeton, nj": (40.3573, -74.6672), "plainsboro, nj": (40.3335, -74.5882),
    "cranbury, nj": (40.3162, -74.5137), "somerset, nj": (40.4984, -74.4885), "union, nj": (40.6976, -74.2632),
    "wilmington, de": (39.7391, -75.5398), "new castle, de": (39.6620, -75.5663),
}


def miles_from_philly(town: str) -> float:
    lat, lon = TOWNS[town.strip().lower()]
    (la1, lo1), (la2, lo2) = PHILLY, (lat, lon)
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def minimums(town: str) -> dict:
    miles = miles_from_philly(town)
    near = miles <= RADIUS_MILES
    borderline = abs(miles - RADIUS_MILES) <= BORDERLINE_MILES
    return {
        "town": town, "miles": round(miles, 1), "near": near, "borderline": borderline,
        "simple_menu": None if borderline else (NEAR_SIMPLE_MENU if near else FAR_ALL),
        "full_menu": None if borderline else (FULL_MENU if near else FAR_ALL),
    }


if __name__ == "__main__":
    for t in sys.argv[1:] or sorted(TOWNS):
        m = minimums(t)
        tag = "  BORDERLINE: hold, Steven decides" if m["borderline"] else f"  Simple ${m['simple_menu']}  Full ${m['full_menu']}"
        print(f"{t:24} {m['miles']:5.1f} mi{tag}")
