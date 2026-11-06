from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from . import dedupe, filters, manual
from .config import Config
from .fetchers import Context, Skip, registry
from .models import TZ, Event, SourceResult, Week
from .output import ics_out, markdown, pdf

log = logging.getLogger("eventcal")
FEED_WEEKS_BACK = 4  # past weeks kept in the subscribed calendar so history doesn't vanish


def collect(cfg: Config, week: Week, ctx: Context) -> tuple[list[Event], list[SourceResult]]:
    fetchers = registry()
    events, results = [], []
    for src in cfg.sources:
        name = src.get("name", src["id"])
        if src.get("enabled") is False:
            continue
        fn = fetchers.get(src["type"])
        if fn is None:
            results.append(SourceResult(src["id"], name, False, error=f"unknown type {src['type']!r}"))
            continue
        try:
            evs = fn(src, week, ctx)
            events += evs
            results.append(SourceResult(src["id"], name, True, len(evs)))
            log.info("%-28s %3d events", name, len(evs))
        except Skip as e:
            results.append(SourceResult(src["id"], name, False, error=f"skipped ({e})"))
            log.warning("%-28s skipped: %s", name, e)
        except Exception as e:  # one broken source must not sink the run
            msg = f"{type(e).__name__}: {str(e)[:200]}"
            results.append(SourceResult(src["id"], name, False, error=msg))
            ctx.warnings.append(f"{name} failed this week ({msg}).")
            log.exception("%s failed", name)
    mine = manual.expand(cfg.manual, week, ctx.warnings)
    events += mine
    results.append(SourceResult("manual", "Your list (manual.yaml)", True, len(mine)))
    return events, results


def run(config_dir: str, out_dir: str, today=None, ctx: Context | None = None,
        feed_base: str = "", write_pdf: bool = True) -> dict:
    cfg = Config.load(config_dir)
    today = today or datetime.now(TZ).date()
    week = Week.for_run_date(today)
    ctx = ctx or Context(config=cfg)
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "archive").mkdir(exist_ok=True)
    (out / "feeds").mkdir(exist_ok=True)

    raw, results = collect(cfg, week, ctx)
    kept, dropped = filters.apply(raw, cfg.filters)
    types = {s["id"]: s["type"] for s in cfg.sources} | {"manual": "manual"}
    events = dedupe.dedupe(kept, types)
    events = [e for e in events if week.contains(e.start)]
    warnings = list(dict.fromkeys(ctx.warnings))
    log.info("week %s: %d raw, %d filtered out, %d after dedupe", week.start, len(raw), len(dropped), len(events))

    # archive this week's events, then build feeds from a rolling window of archived weeks
    (out / "data" / f"{week.start}.json").write_text(json.dumps(
        {"week": str(week.start), "events": [e.to_dict() for e in events]}, indent=1))
    window: list[Event] = []
    for i in range(-FEED_WEEKS_BACK, 1):
        f = out / "data" / f"{week.start + timedelta(weeks=i)}.json"
        if f.exists():
            window += [Event.from_dict(d) for d in json.loads(f.read_text())["events"]]
    (out / "calendar.ics").write_bytes(ics_out.build(window, "Philly events"))
    for cat in cfg.categories:
        (out / "feeds" / f"{cat}.ics").write_bytes(
            ics_out.build([e for e in window if e.category == cat], f"Philly: {cat}"))

    md = markdown.render(week, events, results, warnings, cfg.categories, feed_base)
    (out / "archive" / f"{week.start}.md").write_text(md)
    (out / "weekly.md").write_text(md)
    if write_pdf:
        pdf.render(str(out / "archive" / f"{week.start}.pdf"), week, events, results, warnings)
        (out / "weekly.pdf").write_bytes((out / "archive" / f"{week.start}.pdf").read_bytes())
    weeks = sorted(p.stem for p in (out / "archive").glob("*.md"))[::-1]
    index = md + "\n## Past weeks\n\n" + "\n".join(f"- [{w}](archive/{w}.md) · [pdf](archive/{w}.pdf)" for w in weeks) + "\n"
    (out / "index.md").write_text(index)
    return {"week": week, "events": events, "results": results, "warnings": warnings, "dropped": dropped}
