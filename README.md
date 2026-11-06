# philly-events

Every Sunday evening this builds a digest of the coming week's Philadelphia events (Markdown + PDF)
and a calendar feed you subscribe to once in Google Calendar. It pulls from public calendars,
event pages, and a hand-kept list of your own recurring events.

```
config/sources.yaml   where events come from (feeds, pages, APIs)
config/manual.yaml    your own recurring + one-off events
config/filters.yaml   keep/drop/recategorize rules (e.g. hide committee meetings)
config/interests.yaml who it's for, categories, LLM settings
docs/                 output, served by GitHub Pages
  calendar.ics          everything (subscribe to this, or to individual feeds below)
  feeds/<category>.ics  one feed per category
  weekly.md / .pdf      this week's digest;  archive/ has past weeks;  data/ is raw JSON
```

## One-time setup

1. Create a public repo `philly-events` under your account and push this folder to `main`.
2. **Secrets** (Settings → Secrets and variables → Actions → New repository secret):
   - `ANTHROPIC_API_KEY`: from console.anthropic.com. Powers the `llm_page` sources. Without it,
     those sources are skipped and everything else still runs.
   - `TICKETMASTER_API_KEY` (optional): free "Consumer Key" from developer.ticketmaster.com.
     Covers Live Nation/Ticketmaster venues.
3. **Pages**: Settings → Pages → Source: *Deploy from a branch* → `main` / `/docs`.
4. **First run**: Actions → *Build weekly events* → *Run workflow*.
5. **Subscribe**: Google Calendar on the web → *Other calendars* + → *From URL* →
   `https://maxsg.github.io/philly-events/calendar.ics`
   Or subscribe to individual feeds like `.../feeds/chess.ics`, `.../feeds/dsa.ics`. Separate
   feeds let you color them differently and hide the ~35 weekly open mics when you don't want them.

Google re-fetches subscribed calendars on its own schedule, typically every several hours and
sometimes up to a day. Expect Sunday's build to appear by Monday. Use *From URL*, not *Import*:
an import is a one-time copy that goes stale and duplicates on re-import.

## Day-to-day

**Add an event or a recurring thing.** Edit `config/manual.yaml`. GitHub's web editor or mobile app
is enough. Pushing a change to `config/` rebuilds immediately.

**Add a source.** Add an entry to `config/sources.yaml`. Prefer, in order:
1. `ics`: if the site has a calendar feed. Look for "Subscribe", "iCal", "Add to Google Calendar",
   or a Google Calendar embed (the DSA feed was found inside their embedded calendar).
2. `llm_page`: any page that lists events. Claude extracts them. Use `follow_link` when the page
   gets a new URL every week (see Billy Penn).
3. A new fetcher type in `eventcal/fetchers/`, for sites with an API.

**Filter.** Add rules to `config/filters.yaml`. A commented example shows how to hide DSA committee
meetings except your own. For logic YAML can't express, add a function to `CUSTOM` in
`eventcal/filters.py`.

## Trust and failure behavior

- **One broken source never sinks the run.** Failures are listed under *Heads up* and in the
  *Sources* table at the bottom of each digest. The Action itself fails (and GitHub emails you) only
  if every source fails, which usually means a network or code problem.
- **LLM-extracted events are checked.** Claude must quote a verbatim snippet from the page for each
  event. Anything whose quote isn't actually on the page, whose date falls outside the week, or whose
  date doesn't parse is dropped and reported. Links not present on the page are replaced with the
  page URL. Relevance below `min_relevance` is dropped too. Times can still be misread, so every event
  links back to its source.
- **Badslava is probably stale.** When this was set up, its Philadelphia page carried dates from
  January 2025. Mics are placed by weekday, and the digest warns while the page stays old. Confirm a
  mic before you go.
- **Manual events go stale too.** Set `last_verified:`. After 60 days the digest notes it.

## Local run

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
ANTHROPIC_API_KEY=... python run.py --date 2026-11-08   # pretend it's that Sunday
```

Week rule: a Sunday run builds Monday–Sunday of the coming week. A run on any other day rebuilds the
current week. Feeds keep the past 4 weeks so recent events don't vanish from your calendar. Event IDs
are stable across reruns, so updates replace events instead of duplicating them.

Cost: the LLM step reads about four pages a week with a small model, typically well under $1/month.
GitHub Actions and Pages are free for public repos.
