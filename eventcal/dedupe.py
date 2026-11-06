from __future__ import annotations

from .models import Event, norm_title

PRIORITY = {"manual": 0, "ics": 1, "ticketmaster": 2, "badslava": 3, "llm_page": 4}
STOP = {"the", "a", "an", "at", "and", "of", "in", "with", "for", "on", "to", "2026", "2027"}


def _tokens(t: str) -> set[str]:
    return {w for w in norm_title(t).split() if w not in STOP}


def same_event(a: Event, b: Event) -> bool:
    if a.day != b.day:
        return False
    if not (a.all_day or b.all_day) and abs((a.start - b.start).total_seconds()) > 3600:
        return False
    ta, tb = _tokens(a.title), _tokens(b.title)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def dedupe(events: list[Event], source_types: dict[str, str]) -> list[Event]:
    rank = lambda e: (PRIORITY.get(source_types.get(e.source, "llm_page"), 9),
                      -sum(bool(x) for x in (e.venue, e.url, e.description, e.price)), e.all_day)
    kept: list[Event] = []
    for e in sorted(events, key=rank):
        dup = next((k for k in kept if same_event(k, e)), None)
        if dup is None:
            kept.append(e)
            continue
        if e.source_name not in dup.also_listed_by and e.source_name != dup.source_name:
            dup.also_listed_by.append(e.source_name)
        for f in ("venue", "address", "price", "description"):
            if not getattr(dup, f) and getattr(e, f):
                setattr(dup, f, getattr(e, f))
        if dup.relevance is None and e.relevance is not None:
            dup.relevance = e.relevance
    return sorted(kept, key=lambda e: (e.local_start, e.title))
