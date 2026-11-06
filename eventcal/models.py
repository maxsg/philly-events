from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Event:
    title: str
    start: datetime            # timezone-aware; for all-day events, midnight local
    source: str                # source id
    source_name: str = ""
    end: datetime | None = None
    all_day: bool = False
    venue: str = ""
    address: str = ""
    url: str = ""
    description: str = ""
    price: str = ""
    category: str = "other"
    relevance: int | None = None
    recurring: bool = False
    notes: list[str] = field(default_factory=list)
    also_listed_by: list[str] = field(default_factory=list)
    uid: str = ""

    def __post_init__(self):
        if self.start.tzinfo is None:
            self.start = self.start.replace(tzinfo=TZ)
        if self.end is not None and self.end.tzinfo is None:
            self.end = self.end.replace(tzinfo=TZ)
        if not self.uid:
            key = f"{self.source}|{norm_title(self.title)}|{self.start.astimezone(TZ).isoformat()}"
            self.uid = hashlib.sha1(key.encode()).hexdigest()[:20] + "@philly-events"

    @property
    def local_start(self) -> datetime:
        return self.start.astimezone(TZ)

    @property
    def day(self) -> date:
        return self.local_start.date()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d["start"] = datetime.fromisoformat(d["start"])
        d["end"] = datetime.fromisoformat(d["end"]) if d.get("end") else None
        return cls(**d)


@dataclass
class Week:
    start: date  # a Monday

    @property
    def end(self) -> date:  # inclusive Sunday
        return self.start + timedelta(days=6)

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.start, datetime.min.time(), TZ)

    @property
    def end_dt(self) -> datetime:  # exclusive
        return datetime.combine(self.start + timedelta(days=7), datetime.min.time(), TZ)

    def contains(self, dt: datetime) -> bool:
        return self.start_dt <= dt.astimezone(TZ) < self.end_dt

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(7)]

    @classmethod
    def for_run_date(cls, today: date) -> "Week":
        """Sunday runs build the coming week; any other day rebuilds the current week."""
        d = today + timedelta(days=1)
        return cls(d - timedelta(days=d.weekday()))

    def label(self) -> str:
        s, e = self.start, self.end
        if s.month == e.month:
            return f"{s:%b} {s.day}–{e.day}, {e.year}"
        return f"{s:%b} {s.day} – {e:%b} {e.day}, {e.year}"


@dataclass
class SourceResult:
    source_id: str
    name: str
    ok: bool
    count: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)
