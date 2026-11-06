"""Any web page -> events, via Claude with a strict schema.

Hallucination guards (an event is dropped unless all pass):
  * start parses and falls inside the target week
  * `evidence` (a verbatim snippet the model must copy) actually appears in the page text
  * relevance >= interests.min_relevance
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..http import html_to_text
from ..models import TZ, Event, Week
from . import Skip

TOOL = {
    "name": "record_events",
    "description": "Record every qualifying event found on the page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {"type": "string", "description": "Local Philadelphia time, 'YYYY-MM-DD HH:MM', or 'YYYY-MM-DD' if no time is given"},
                        "end": {"type": "string", "description": "Same format, or empty"},
                        "venue": {"type": "string"},
                        "address": {"type": "string"},
                        "url": {"type": "string", "description": "Most specific link for this event that appears on the page, else empty"},
                        "price": {"type": "string"},
                        "summary": {"type": "string", "description": "One sentence, plain description"},
                        "category": {"type": "string"},
                        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
                        "evidence": {"type": "string", "description": "A short verbatim quote (5-15 words) copied exactly from the page text about this event"},
                    },
                    "required": ["title", "start", "category", "relevance", "evidence"],
                },
            }
        },
        "required": ["events"],
    },
}


def build_prompt(week: Week, interests: dict, categories: dict, default_category: str | None) -> str:
    cats = "\n".join(f"- {k}: {v}" for k, v in categories.items())
    return f"""You extract events from a Philadelphia events web page.

Target week: {week.start:%A %Y-%m-%d} through {week.end:%A %Y-%m-%d} (America/New_York).
Only include events with an occurrence inside that week. For multi-day runs (exhibits, festivals,
theater runs), include one entry on the first day it is on within the week, with the run noted in summary.

Who this is for: {interests.get('profile', '').strip()}

Score relevance 1-5 for that person (5 = clearly their thing, 3 = plausibly interesting, 1 = not for them).
Category must be one of:
{cats}
{f'If unsure, use "{default_category}".' if default_category else ''}

Rules: never invent details. If the page doesn't state a time, give the date only. The evidence field
must be copied character-for-character from the page. Call record_events once with all events (empty list if none)."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[‘’“”]", "'", s)).strip().lower()


def _parse_local(s: str) -> tuple[datetime | None, bool]:
    s = (s or "").strip().replace("T", " ")
    for fmt, all_day in (("%Y-%m-%d %H:%M", False), ("%Y-%m-%d %H:%M:%S", False), ("%Y-%m-%d", True)):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ), all_day
        except ValueError:
            pass
    return None, False


def validate(raw: list[dict], page_text: str, src: dict, week: Week, min_rel: int, categories: dict) -> tuple[list[Event], list[str]]:
    page = _norm(page_text)
    out, dropped = [], []
    for r in raw:
        title = (r.get("title") or "").strip()
        start, all_day = _parse_local(r.get("start", ""))
        ev = _norm(r.get("evidence", ""))
        why = None
        if not title or not start:
            why = "unparseable date"
        elif not week.contains(start):
            why = "outside week"
        elif len(ev) < 8 or ev not in page:
            why = "evidence not found on page"
        elif int(r.get("relevance") or 0) < min_rel:
            why = "low relevance"
        if why:
            dropped.append(f"{title or '?'} ({why})")
            continue
        end, _ = _parse_local(r.get("end", ""))
        cat = r.get("category") if r.get("category") in categories else src.get("category", "other")
        url = (r.get("url") or "").strip()
        if url and url not in page_text:
            url = ""
        out.append(Event(
            title=title, start=start, all_day=all_day,
            end=end if end and end > start else (None if all_day else start + timedelta(hours=2)),
            venue=(r.get("venue") or "").strip(), address=(r.get("address") or "").strip(),
            url=url or src.get("link") or src["url"], price=(r.get("price") or "").strip(),
            description=(r.get("summary") or "").strip(), category=cat,
            relevance=int(r.get("relevance")), source=src["id"], source_name=src.get("name", src["id"]),
        ))
    return out, dropped


def call_claude(client, model: str, system: str, page_text: str) -> list[dict]:
    import anthropic
    kwargs = dict(model=model, max_tokens=8000, system=system, tools=[TOOL],
                  messages=[{"role": "user", "content": f"<page>\n{page_text}\n</page>"}])
    try:
        resp = client.messages.create(tool_choice={"type": "tool", "name": "record_events"}, **kwargs)
    except anthropic.BadRequestError:
        resp = client.messages.create(**kwargs)  # some models reject forced tool choice
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "record_events":
            return block.input.get("events", [])
    raise RuntimeError("model did not return events")


def fetch(src, week: Week, ctx):
    llm_cfg = ctx.config.interests.get("llm") or {}
    if ctx.llm is None:
        if not ctx.env.get("ANTHROPIC_API_KEY"):
            raise Skip("ANTHROPIC_API_KEY not set")
        import anthropic
        client = anthropic.Anthropic(api_key=ctx.env["ANTHROPIC_API_KEY"])
        ctx.llm = lambda system, text: call_claude(client, llm_cfg.get("model", "claude-haiku-5-5"), system, text)

    url = src["url"]
    html = ctx.get(url).text
    if src.get("follow_link"):
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
        hit = next((h for h in hrefs if re.search(src["follow_link"], h)), None)
        if not hit:
            raise RuntimeError(f"no link matching {src['follow_link']!r} on {url}")
        url = hit if hit.startswith("http") else requests_join(url, hit)
        html = ctx.get(url).text
    text = html_to_text(html, url)[: int(llm_cfg.get("max_page_chars", 60000))]
    system = build_prompt(week, ctx.config.interests, ctx.config.categories, src.get("category"))
    raw = ctx.llm(system, text)
    events, dropped = validate(raw, text, {**src, "link": src.get("link") or url}, week,
                               int(ctx.config.interests.get("min_relevance", 3)), ctx.config.categories)
    bad = [d for d in dropped if "evidence" in d or "unparseable" in d]
    if bad:
        ctx.warnings.append(f"{src.get('name', src['id'])}: discarded {len(bad)} unverifiable item(s): " + "; ".join(bad[:5]))
    return events


def requests_join(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href)
