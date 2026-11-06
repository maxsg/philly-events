import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import icalendar
import pytest

from eventcal import dedupe, filters, manual
from eventcal.config import Config
from eventcal.fetchers import Context
from eventcal.fetchers import badslava, ics, llm_page, ticketmaster
from eventcal.models import TZ, Event, Week
from eventcal.pipeline import run

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
WEEK = Week.for_run_date(date(2026, 11, 8))  # Sunday -> Nov 9-15


def resp(content: bytes):
    return SimpleNamespace(content=content, text=content.decode())


def test_week_rules():
    assert WEEK.start == date(2026, 11, 9) and WEEK.end == date(2026, 11, 15)
    assert Week.for_run_date(date(2026, 11, 11)).start == date(2026, 11, 9)   # Wed -> this week
    assert Week.for_run_date(date(2026, 11, 9)).start == date(2026, 11, 9)    # Mon -> this week


def test_real_config_loads():
    cfg = Config.load(ROOT / "config")
    assert {s["type"] for s in cfg.sources} <= {"ics", "badslava", "llm_page", "ticketmaster"}
    evs = manual.expand(cfg.manual, WEEK, [])
    chess = sorted((e.local_start.strftime("%a %H:%M"), e.venue) for e in evs if e.category == "chess")
    assert chess == [("Sun 13:00", "Rittenhouse Square"), ("Wed 18:00", "Rittenhouse Square")]


def test_manual_rules_and_staleness():
    m = {"recurring": [
        {"title": "A", "days": ["tue", "thu"], "time": "19:30", "last_verified": "2026-08-01"},
        {"title": "Paused", "days": ["mon"], "time": "10:00", "paused": True},
        {"title": "Biweekly", "days": ["mon"], "time": "10:00", "every": 2, "start_date": "2026-11-02"},
        {"title": "Ended", "days": ["mon"], "time": "10:00", "until": "2026-11-01"},
        {"title": "Broken", "days": ["xyz"], "time": "10:00"},
    ], "one_off": [
        {"title": "In", "start": "2026-11-12 20:00"},
        {"title": "AllDay", "start": "2026-11-14"},
        {"title": "Out", "start": "2026-12-01 20:00"},
    ]}
    warn = []
    evs = manual.expand(m, WEEK, warn)
    titles = sorted(e.title for e in evs)
    assert titles == ["A", "A", "AllDay", "In"]          # biweekly is off this week
    assert all("Not verified" in e.notes[0] for e in evs if e.title == "A")
    assert any("Broken" in w for w in warn)
    assert [e for e in evs if e.title == "AllDay"][0].all_day


def test_badslava_parse():
    src = {"id": "bs", "name": "Badslava", "url": "u", "category": "open-mic"}
    ctx = Context(config=None, get=lambda u: resp((FIX / "badslava.html").read_bytes()))
    evs = badslava.fetch(src, WEEK, ctx)
    got = [(e.local_start.strftime("%a %H:%M"), e.venue, e.address) for e in evs]
    assert ("Tue 19:00", "Ortlieb’s Lounge", "847 North 3rd St Philadelphia PA") in got
    assert ("Mon 16:45", "Punch Line Philly", "33 E Laurel St Philadelphia PA") in got
    assert len(evs) == 5                                   # footer "Monday 12:00pm Fake" ignored
    assert any("stale" in w for w in ctx.warnings)


def test_badslava_empty_page_raises():
    ctx = Context(config=None, get=lambda u: resp(b"<html>redesigned</html>"))
    with pytest.raises(RuntimeError):
        badslava.fetch({"id": "bs", "url": "u"}, WEEK, ctx)


def test_ics_dsa():
    src = {"id": "dsa", "name": "DSA", "category": "dsa", "link": "https://www.phillydsa.org/events"}
    evs = ics.parse_ics((FIX / "dsa.ics").read_bytes(), src, WEEK)
    by = {e.title: e for e in evs}
    assert set(by) == {"General Meeting", "Housing Committee Meeting", "Day of Action"}
    gm = by["General Meeting"]
    assert gm.local_start == datetime(2026, 11, 12, 19, 0, tzinfo=TZ)
    assert gm.venue == "Friends Center" and gm.address.startswith("1501 Cherry")
    assert by["Housing Committee Meeting"].local_start.date() == date(2026, 11, 11)  # RRULE expanded
    assert by["Day of Action"].all_day


def test_filters():
    mk = lambda t, s="dsa": Event(title=t, start=datetime(2026, 11, 10, 18, tzinfo=TZ), source=s)
    rules = [
        {"source": "dsa", "match": "housing", "action": "keep"},
        {"source": "dsa", "match": "committee.*meeting", "action": "drop"},
        {"match": "pierogi", "action": "category", "set": "food"},
    ]
    evs = [mk("Housing Committee Meeting"), mk("Labor Committee Meeting"), mk("Labor Committee Meeting", "x"),
           mk("Pierogi Fest", "x")]
    kept, dropped = filters.apply(evs, rules)
    assert [e.title for e in dropped] == ["Labor Committee Meeting"]
    assert len(kept) == 3 and kept[-1].category == "food"
    assert filters.apply(evs, [])[1] == []                 # no rules = keep everything


def test_dedupe_merges_cross_source():
    a = Event(title="Fiction Night at Harriett's Bookshop", start=datetime(2026, 11, 10, 19, tzinfo=TZ),
              source="bp", source_name="Billy Penn", venue="Harriett's", url="https://x")
    b = Event(title="Fiction Night", start=datetime(2026, 11, 10, 19, 30, tzinfo=TZ),
              source="vp", source_name="Visit Philly", price="Free")
    c = Event(title="Fiction Night", start=datetime(2026, 11, 11, 19, tzinfo=TZ), source="vp")
    out = dedupe.dedupe([b, a, c], {"bp": "llm_page", "vp": "llm_page"})
    assert len(out) == 2
    first = out[0]
    assert first.source_name == "Billy Penn" and first.price == "Free" and first.also_listed_by == ["Visit Philly"]


def test_llm_validation_drops_hallucinations():
    text = llm_page.html_to_text((FIX / "page.html").read_text(), "https://billypenn.com/x")
    raw = [
        {"title": "Fiction Night at Harriett's Bookshop", "start": "2026-11-10 19:00", "end": "2026-11-10 21:00",
         "url": "https://example.org/reading", "category": "literary", "relevance": 5,
         "evidence": "Three novelists read from new work."},
        {"title": "Invented Gala", "start": "2026-11-12 19:00", "category": "arts", "relevance": 5,
         "evidence": "A glamorous gala nobody wrote about"},
        {"title": "Philly Pierogi Pop-up", "start": "2026-11-11 12:00", "category": "food", "relevance": 4,
         "evidence": "Pierogi and kielbasa in Fishtown", "url": "https://made-up.example/pierogi"},
        {"title": "Old thing", "start": "2026-10-01 12:00", "category": "food", "relevance": 5,
         "evidence": "Pierogi and kielbasa in Fishtown"},
        {"title": "Meh", "start": "2026-11-11 12:00", "category": "food", "relevance": 2,
         "evidence": "Pierogi and kielbasa in Fishtown"},
    ]
    cats = {"literary": "", "food": "", "arts": "", "other": ""}
    evs, dropped = llm_page.validate(raw, text, {"id": "bp", "url": "https://billypenn.com/x"}, WEEK, 3, cats)
    assert [e.title for e in evs] == ["Fiction Night at Harriett's Bookshop", "Philly Pierogi Pop-up"]
    assert evs[0].url == "https://example.org/reading"
    assert evs[1].url == "https://billypenn.com/x"           # made-up URL replaced by the page URL
    assert len(dropped) == 3


def test_ticketmaster_parse():
    data = {"_embedded": {"events": [
        {"name": "Josh Johnson", "url": "https://tm/1", "dates": {"start": {"dateTime": "2026-11-14T22:00:00Z"}},
         "priceRanges": [{"min": 39.5}], "_embedded": {"venues": [{"name": "Academy of Music",
          "address": {"line1": "240 S Broad St"}, "city": {"name": "Philadelphia"}}]}},
        {"name": "Next week", "dates": {"start": {"localDate": "2026-11-20", "localTime": "20:00:00"}}},
    ]}}
    evs = ticketmaster.parse(data, {"id": "tm", "category": "comedy"}, WEEK)
    assert len(evs) == 1 and evs[0].local_start.hour == 17 and evs[0].price == "$40+"


def test_end_to_end(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    for f in ["manual.yaml", "interests.yaml", "filters.yaml"]:
        (cfg_dir / f).write_text((ROOT / "config" / f).read_text())
    (cfg_dir / "sources.yaml").write_text("""
sources:
  - {id: phillydsa, name: Philly DSA, type: ics, url: "dsa", category: dsa}
  - {id: badslava, name: Badslava, type: badslava, url: "bs", category: open-mic}
  - {id: bp, name: Billy Penn, type: llm_page, url: "https://billypenn.com/", follow_link: 'weekly-events'}
  - {id: tm, name: Ticketmaster, type: ticketmaster}
  - {id: broken, name: Broken site, type: ics, url: "boom"}
""")
    pages = {"dsa": FIX / "dsa.ics", "bs": FIX / "badslava.html",
             "https://billypenn.com/2026/11/09/philly-weekly-events-calendar": FIX / "page.html"}

    def fake_get(u):
        if u == "https://billypenn.com/":
            return resp(b'<a href="/2026/11/09/philly-weekly-events-calendar">wk</a>')
        if u not in pages:
            raise ConnectionError("down")
        return resp(pages[u].read_bytes())

    cfg = Config.load(cfg_dir)
    fake_llm = lambda system, text: [{"title": "Fiction Night at Harriett's Bookshop", "start": "2026-11-10 19:00",
                                      "category": "literary", "relevance": 5,
                                      "evidence": "Three novelists read from new work."}]
    ctx = Context(config=cfg, get=fake_get, env={}, llm=fake_llm)
    out = tmp_path / "docs"
    res = run(str(cfg_dir), str(out), today=date(2026, 11, 8), ctx=ctx, feed_base="https://maxsg.github.io/philly-events")

    status = {r.source_id: (r.ok, r.error.split(" ")[0]) for r in res["results"]}
    assert status["tm"] == (False, "skipped")
    assert status["broken"][0] is False and status["phillydsa"][0] and status["bp"][0]

    cal = icalendar.Calendar.from_ical((out / "calendar.ics").read_bytes())
    vevents = list(cal.walk("VEVENT"))
    uids = [str(v["UID"]) for v in vevents]
    assert len(uids) == len(set(uids)) == len(res["events"]) == 3 + 5 + 1 + 2
    md = (out / "weekly.md").read_text()
    assert "## Wednesday, Nov 11" in md and "Chess at Rittenhouse Square" in md
    assert "**Open mics:**" in md and "Broken site failed" in md
    assert (out / "weekly.pdf").read_bytes()[:4] == b"%PDF"
    assert (out / "feeds" / "chess.ics").exists()

    # rerun: same UIDs (stable), archive keeps one file per week
    run(str(cfg_dir), str(out), today=date(2026, 11, 8), ctx=Context(config=cfg, get=fake_get, env={}, llm=fake_llm))
    cal2 = icalendar.Calendar.from_ical((out / "calendar.ics").read_bytes())
    assert sorted(str(v["UID"]) for v in cal2.walk("VEVENT")) == sorted(uids)
    # next week's run keeps last week's events in the subscribed feed
    run(str(cfg_dir), str(out), today=date(2026, 11, 15), ctx=Context(config=cfg, get=fake_get, env={}, llm=fake_llm))
    cal3 = icalendar.Calendar.from_ical((out / "calendar.ics").read_bytes())
    assert set(uids) <= {str(v["UID"]) for v in cal3.walk("VEVENT")}
