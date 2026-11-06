"""badslava.com open-mic pages: a list grouped under weekday headers, each mic a
time line followed by venue and address lines. Dates in the headers are the site's own
(often stale), so mics are treated as weekly by weekday and placed into the target week."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..models import TZ, Event, Week

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_RE = re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b\s*(\d{1,2}/\d{1,2}/\d{2,4})?", re.I)
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$", re.I)
STOP_RE = re.compile(r"^open mics in the united states", re.I)


def parse_lines(lines: list[str]) -> tuple[list[dict], date | None]:
    mics, day, header_dates = [], None, []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if STOP_RE.match(ln):
            break
        m = DAY_RE.match(ln)
        if m:
            day = DAYS.index(m.group(1).lower())
            if m.group(2):
                fmt = "%m/%d/%y" if len(m.group(2).split("/")[-1]) == 2 else "%m/%d/%Y"
                try:
                    header_dates.append(datetime.strptime(m.group(2), fmt).date())
                except ValueError:
                    pass
            i += 1
            continue
        t = TIME_RE.match(ln)
        if t and day is not None and i + 1 < len(lines):
            h, mnt, ap = int(t.group(1)), int(t.group(2)), t.group(3).lower()
            h = h % 12 + (12 if ap == "p" else 0)
            venue = lines[i + 1]
            address = ""
            if i + 2 < len(lines) and not TIME_RE.match(lines[i + 2]) and not DAY_RE.match(lines[i + 2]):
                address = lines[i + 2]
            mics.append({"weekday": day, "hour": h, "minute": mnt, "venue": venue, "address": address})
            i += 3 if address else 2
            continue
        i += 1
    return mics, (max(header_dates) if header_dates else None)


def parse_html(html: str) -> tuple[list[dict], date | None]:
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    return parse_lines([x for x in lines if x])


def fetch(src, week: Week, ctx):
    html = ctx.get(src["url"]).text
    mics, last_date = parse_html(html)
    if not mics:
        raise RuntimeError("parsed 0 open mics - page layout probably changed")
    note = []
    stale_after = src.get("stale_after_days", 60)
    if last_date and (week.start - last_date).days > stale_after:
        msg = f"{src.get('name', src['id'])}: page's own dates end {last_date:%b %-d, %Y} - listings may be stale; confirm before going."
        ctx.warnings.append(msg)
        note.append(f"Badslava listing last dated {last_date:%b %-d, %Y}; confirm it's still running")
    out = []
    for m in mics:
        d = week.start + timedelta(days=m["weekday"])
        start = datetime(d.year, d.month, d.day, m["hour"], m["minute"], tzinfo=TZ)
        out.append(Event(
            title=f"Open mic: {m['venue']}",
            start=start,
            end=start + timedelta(hours=2),
            venue=m["venue"],
            address=m["address"],
            url=src["url"],
            source=src["id"],
            source_name=src.get("name", src["id"]),
            category=src.get("category", "open-mic"),
            recurring=True,
            notes=list(note),
        ))
    return out
