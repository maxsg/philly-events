from __future__ import annotations

from datetime import date, datetime, timedelta

import icalendar
import recurring_ical_events

from ..models import TZ, Event, Week


def _to_dt(v) -> tuple[datetime, bool]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=TZ)), False
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time(), TZ), True
    raise ValueError(f"unexpected date value {v!r}")


def parse_ics(text: str | bytes, src: dict, week: Week) -> list[Event]:
    cal = icalendar.Calendar.from_ical(text)
    occurrences = recurring_ical_events.of(cal).between(week.start_dt, week.end_dt)
    out = []
    for comp in occurrences:
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start, all_day = _to_dt(comp.decoded("DTSTART"))
        end = None
        if comp.get("DTEND"):
            end, _ = _to_dt(comp.decoded("DTEND"))
        elif comp.get("DURATION"):
            end = start + comp.decoded("DURATION")
        loc = str(comp.get("LOCATION", "") or "").strip()
        venue, _, address = loc.partition(",")
        desc = str(comp.get("DESCRIPTION", "") or "").strip()
        url = str(comp.get("URL", "") or "") or src.get("link", "")
        out.append(Event(
            title=str(comp.get("SUMMARY", "Untitled")).strip(),
            start=start,
            end=end if end and end > start and not (all_day and end - start == timedelta(days=1)) else None,
            all_day=all_day,
            venue=venue.strip(),
            address=address.strip(),
            url=url,
            description=desc[:1000],
            source=src["id"],
            source_name=src.get("name", src["id"]),
            category=src.get("category", "other"),
        ))
    return [e for e in out if week.contains(e.start)]


def fetch(src, week, ctx):
    return parse_ics(ctx.get(src["url"]).content, src, week)
