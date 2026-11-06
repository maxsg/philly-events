from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    sources: list[dict]
    manual: dict
    interests: dict
    filters: list[dict]

    @classmethod
    def load(cls, config_dir: str | Path) -> "Config":
        d = Path(config_dir)

        def y(name):
            p = d / name
            return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}

        sources = y("sources.yaml").get("sources") or []
        ids = [s.get("id") for s in sources]
        missing = [s for s in sources if not s.get("id") or not s.get("type")]
        if missing:
            raise ValueError(f"sources.yaml: every source needs id and type: {missing}")
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"sources.yaml: duplicate source ids {sorted(dupes)}")
        return cls(
            sources=sources,
            manual=y("manual.yaml"),
            interests=y("interests.yaml"),
            filters=y("filters.yaml").get("rules") or [],
        )

    @property
    def categories(self) -> dict[str, str]:
        return self.interests.get("categories") or {"other": "Other"}
