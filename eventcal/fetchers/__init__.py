"""Fetcher registry. A fetcher is fn(src: dict, week: Week, ctx: Context) -> list[Event].

It may append human-readable warnings to ctx.warnings, and should raise on hard failure
(the pipeline catches it, records it in the digest, and carries on with other sources).
To add a new source type: write a module with a fetch() function and register it below.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from ..config import Config
from ..http import get as http_get


@dataclass
class Context:
    config: Config
    get: Callable = http_get
    env: dict = field(default_factory=lambda: dict(os.environ))
    llm: object | None = None          # injectable for tests; built lazily otherwise
    warnings: list[str] = field(default_factory=list)


def registry():
    from . import badslava, ics, llm_page, ticketmaster
    return {
        "ics": ics.fetch,
        "badslava": badslava.fetch,
        "llm_page": llm_page.fetch,
        "ticketmaster": ticketmaster.fetch,
    }


class Skip(Exception):
    """Raised when a source can't run for a benign reason (e.g. missing API key)."""
