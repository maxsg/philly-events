from __future__ import annotations

from datetime import datetime, timedelta, timezone

import icalendar

from ..models import Event


def build(events: list[Event], name: str, now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    cal = icalendar.Calendar()
    cal.add("prodid", "-//philly-events//github.com/maxsg/philly-events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-timezone", "America/New_York")
    cal.add("refresh-interval", timedelta(hours=12), parameters={"VALUE": "DURATION"})
    cal.add("x-published-ttl", "PT12H")
    for e in events:
        ve = icalendar.Event()
        ve.add("uid", e.uid)
        ve.add("dtstamp", now)
        ve.add("summary", e.title)
        if e.all_day:
            d0 = e.local_start.date()
            d1 = e.end.astimezone(e.start.tzinfo).date() if e.end else None
            ve.add("dtstart", d0)
            ve.add("dtend", d1 if d1 and d1 > d0 else d0 + timedelta(days=1))
        else:
            ve.add("dtstart", e.start.astimezone(timezone.utc))
            ve.add("dtend", (e.end or e.start + timedelta(hours=2)).astimezone(timezone.utc))
        loc = ", ".join(x for x in (e.venue, e.address) if x)
        if loc:
            ve.add("location", loc)
        if e.url:
            ve.add("url", e.url)
        desc = [e.description] if e.description else []
        if e.price:
            desc.append(f"Price: {e.price}")
        desc += e.notes
        src = e.source_name + (f" (also: {', '.join(e.also_listed_by)})" if e.also_listed_by else "")
        desc.append(f"Source: {src}")
        if e.url:
            desc.append(e.url)
        ve.add("description", "\n".join(desc))
        ve.add("categories", [e.category])
        ve.add("transp", "TRANSPARENT")  # don't mark you busy
        cal.add_component(ve)
    return cal.to_ical()
