from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..models import TZ, Event, SourceResult, Week

COMPACT = {"open-mic"}


def fmt_time(e: Event) -> str:
    if e.all_day:
        return "All day"
    t = e.local_start
    return t.strftime("%-I:%M %p").replace(":00 ", " ")


def _line(e: Event, cats: dict) -> str:
    title = f"[{e.title}]({e.url})" if e.url else e.title
    bits = [f"**{fmt_time(e)}** · {title}"]
    where = e.venue or e.address
    if where:
        bits.append(f"— {where}")
    meta = [e.category] + ([e.price] if e.price else [])
    line = " ".join(bits) + f" · _{', '.join(meta)}_"
    if e.description:
        line += f"  \n  {e.description}"
    for n in e.notes:
        line += f"  \n  Note: {n}"
    return "- " + line


def render(week: Week, events: list[Event], results: list[SourceResult], warnings: list[str],
           categories: dict, feed_base: str = "", generated: datetime | None = None) -> str:
    generated = generated or datetime.now(TZ)
    by_day: dict = defaultdict(list)
    for e in events:
        by_day[e.day].append(e)
    out = [f"# Philly week of {week.label()}", "",
           f"_Generated {generated:%a %b %-d, %-I:%M %p} · {len(events)} events_", ""]
    if feed_base:
        out += [f"Calendar feeds: [everything]({feed_base}/calendar.ics) · " +
                " · ".join(f"[{c}]({feed_base}/feeds/{c}.ics)" for c in categories) , ""]
    for d in week.days():
        evs = by_day.get(d, [])
        out.append(f"## {d:%A, %b %-d}")
        out.append("")
        main = [e for e in evs if e.category not in COMPACT]
        compact = [e for e in evs if e.category in COMPACT]
        if not evs:
            out += ["_Nothing listed._", ""]
            continue
        out += [_line(e, categories) for e in main]
        if compact:
            mics = ", ".join(f"{fmt_time(e)} {e.venue}" for e in compact)
            out.append(f"- **Open mics:** {mics}")
        out.append("")
    if warnings or any(not r.ok for r in results):
        out += ["## Heads up", ""]
        out += [f"- {w}" for w in warnings]
        out.append("")
    out += ["## Sources", "", "| Source | Status | Events |", "|---|---|---|"]
    for r in results:
        status = "ok" if r.ok else (r.error if r.error.startswith("skipped") else f"**failed**: {r.error}")
        out.append(f"| {r.name} | {status} | {r.count} |")
    out.append("")
    return "\n".join(out)
