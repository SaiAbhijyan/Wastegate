"""Read the frozen route_quality label tables (markdown is the single source of truth)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROW = re.compile(r"^\|\s*([GH]\d{2})\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|\s*(.*?)\s*\|\s*$")


@dataclass(frozen=True)
class LabelRow:
    id: str
    prompt: str
    kind: str
    note: str

    @property
    def split(self) -> str:
        return "golden" if self.id.startswith("G") else "holdout"


def load_labels(path: Path) -> list[LabelRow]:
    rows = []
    for line in Path(path).read_text().splitlines():
        m = ROW.match(line)
        if m:
            rows.append(LabelRow(*m.groups()))
    return rows


POOL_ROW = re.compile(r"^\|\s*(P\d{2})\s*\|\s*(.+?)\s*\|\s*$")


@dataclass(frozen=True)
class PoolRow:
    id: str
    prompt: str


def load_pool(path: Path) -> list[PoolRow]:
    return [PoolRow(*m.groups()) for line in Path(path).read_text().splitlines()
            if (m := POOL_ROW.match(line))]
