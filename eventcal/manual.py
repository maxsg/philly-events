from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import TZ, Event, Week

DAY_IDX = {d: i for i, d in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}
STALE_DAYS = 60


def _d(v) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def expand(manual: dict, week: Week, warnings: list[str]) -> list[Event]:
    out = []
    for i, r in enumerate(manual.get("recurring") or []):
        if r.get("paused"):
            continue
        try:
            days = [DAY_IDX[str(x).lower()[:3]] for x in r["days"]]
            hh, mm = map(int, str(r["time"]).split(":"))
        except (KeyError, ValueError) as e:
            warnings.append(f"manual.yaml recurring #{i+1} ({r.get('title', '?')}): bad days/time ({e})")
            continue
        first, until = _d(r.get("start_date")), _d(r.get("until"))
        every = int(r.get("every", 1))
        notes = []
        lv = _d(r.get("last_verified"))
        if lv and (week.start - lv).days > STALE_DAYS:
            notes.append(f"Not verified since {lv:%b %-d, %Y}")
        for wd in days:
            d = week.start + timedelta(days=wd)
            if (first and d < first) or (until and d > until):
                continue
            if every > 1 and first and ((d - first).days // 7) % every:
                continue
            start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
            out.append(Event(
                title=r["title"], start=start,
                end=start + timedelta(minutes=int(r.get("duration_min", 120))),
                venue=r.get("venue", ""), address=r.get("address", ""), url=r.get("url", ""),
                description=r.get("description", ""), category=r.get("category", "other"),
                source="manual", source_name="Your list", recurring=True, notes=list(notes),
            ))
    for i, r in enumerate(manual.get("one_off") or []):
        try:
            s = str(r["start"]).replace("T", " ")
            all_day = bool(r.get("all_day")) or len(s) == 10
            start = datetime.fromisoformat(s[:10] if all_day else s).replace(tzinfo=TZ)
            end = datetime.fromisoformat(str(r["end"]).replace("T", " ")).replace(tzinfo=TZ) if r.get("end") else None
        except (KeyError, ValueError) as e:
            warnings.append(f"manual.yaml one_off #{i+1} ({r.get('title', '?')}): bad start/end ({e})")
            continue
        if not week.contains(start):
            continue
        out.append(Event(
            title=r["title"], start=start, end=end or (None if all_day else start + timedelta(hours=2)),
            all_day=all_day, venue=r.get("venue", ""), address=r.get("address", ""), url=r.get("url", ""),
            description=r.get("description", ""), category=r.get("category", "other"),
            source="manual", source_name="Your list",
        ))
    return out
