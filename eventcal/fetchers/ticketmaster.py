from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import TZ, Event, Week
from . import Skip

API = "https://app.ticketmaster.com/discovery/v2/events.json"


def parse(data: dict, src: dict, week: Week) -> list[Event]:
    out = []
    for ev in (data.get("_embedded") or {}).get("events", []):
        dates = (ev.get("dates") or {}).get("start") or {}
        if dates.get("dateTime"):
            start = datetime.fromisoformat(dates["dateTime"].replace("Z", "+00:00"))
            all_day = False
        elif dates.get("localDate"):
            t = dates.get("localTime") or "00:00:00"
            start = datetime.fromisoformat(f"{dates['localDate']}T{t}").replace(tzinfo=TZ)
            all_day = not dates.get("localTime")
        else:
            continue
        venues = (ev.get("_embedded") or {}).get("venues") or [{}]
        v = venues[0]
        addr = ", ".join(x for x in [(v.get("address") or {}).get("line1", ""), (v.get("city") or {}).get("name", "")] if x)
        price = ""
        pr = ev.get("priceRanges") or []
        if pr and pr[0].get("min") is not None:
            price = f"${pr[0]['min']:.0f}+"
        out.append(Event(
            title=ev.get("name", "Untitled"),
            start=start,
            all_day=all_day,
            venue=v.get("name", ""),
            address=addr,
            url=ev.get("url", ""),
            price=price,
            source=src["id"],
            source_name=src.get("name", src["id"]),
            category=src.get("category", "other"),
        ))
    return [e for e in out if week.contains(e.start)]


def fetch(src, week: Week, ctx):
    key = ctx.env.get("TICKETMASTER_API_KEY")
    if not key:
        raise Skip("TICKETMASTER_API_KEY not set")
    fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for cls_name in src.get("classifications") or [None]:
        params = {
            "apikey": key, "city": src.get("city", "Philadelphia"), "stateCode": src.get("state", "PA"),
            "startDateTime": fmt(week.start_dt), "endDateTime": fmt(week.end_dt),
            "size": 100, "sort": "date,asc",
        }
        if cls_name:
            params["classificationName"] = cls_name
        r = requests.get(API, params=params, timeout=30)
        r.raise_for_status()
        out += parse(r.json(), src, week)
    return out
