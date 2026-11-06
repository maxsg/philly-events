"""Rule-based keep/drop/recategorize, driven by config/filters.yaml.

Extension point: for logic YAML can't express, add a function to CUSTOM below. Each gets
(event) and returns "drop", "keep", or None (no opinion). They run after the YAML rules
for events no YAML rule matched.
"""
from __future__ import annotations

import re
from typing import Callable

from .models import Event

CUSTOM: list[Callable[[Event], str | None]] = []


def _field(e: Event, f: str) -> str:
    if f == "any":
        return " ".join([e.title, e.description, e.venue])
    return getattr(e, f, "") or ""


def _applies(rule: dict, e: Event) -> bool:
    src = rule.get("source", "*")
    srcs = src if isinstance(src, list) else [src]
    if "*" not in srcs and e.source not in srcs:
        return False
    return bool(re.search(rule["match"], _field(e, rule.get("field", "title")), re.I))


def apply(events: list[Event], rules: list[dict]) -> tuple[list[Event], list[Event]]:
    kept, dropped = [], []
    for e in events:
        decision = None
        for rule in rules:
            if _applies(rule, e):
                act = rule.get("action", "drop")
                if act == "category":
                    e.category = rule["set"]
                    continue  # recategorizing doesn't end evaluation
                decision = act
                break
        if decision is None:
            for fn in CUSTOM:
                decision = fn(e)
                if decision:
                    break
        (dropped if decision == "drop" else kept).append(e)
    return kept, dropped
