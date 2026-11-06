#!/usr/bin/env python3
"""Build this week's digest and calendar feeds.

  python run.py                     # normal run (Sunday -> next week; other days -> this week)
  python run.py --date 2026-11-08   # pretend today is that date
  python run.py --no-pdf
"""
import argparse
import logging
import os
import sys
from datetime import date

from eventcal.pipeline import run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config")
    p.add_argument("--out", default="docs")
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("--no-pdf", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    feed_base = os.environ.get("FEED_BASE_URL", "")
    res = run(a.config, a.out, today=a.date, feed_base=feed_base, write_pdf=not a.no_pdf)
    failed = [r for r in res["results"] if not r.ok and not r.error.startswith("skipped")]
    print(f"\nWeek of {res['week'].label()}: {len(res['events'])} events, {len(failed)} failed source(s)")
    for w in res["warnings"]:
        print("  !", w)
    # fail the job only if every real source failed (likely a network or code problem)
    real = [r for r in res["results"] if r.source_id != "manual" and not r.error.startswith("skipped")]
    sys.exit(1 if real and len(failed) == len(real) else 0)


if __name__ == "__main__":
    main()
