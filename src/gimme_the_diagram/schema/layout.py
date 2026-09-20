from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gimme_the_diagram.layout_engine.auto_layout import compute_auto_layout
from gimme_the_diagram.schema.model import Schema

DEFAULT_ZOOM_LEVEL = 3
MIN_ZOOM_LEVEL = 1
MAX_ZOOM_LEVEL = 3

LAYOUT_DIR = Path.home() / ".local" / "share" / "gimme-the-diagram" / "layouts"


@dataclass
class TablePosition:
    x: int
    y: int
    visible: bool = True


@dataclass
class DiagramLayout:
    positions: dict[str, TablePosition] = field(default_factory=dict)
    zoom_level: int = DEFAULT_ZOOM_LEVEL

    def ensure_table(self, name: str, default_xy: tuple[int, int]) -> TablePosition:
        if name not in self.positions:
            x, y = default_xy
            self.positions[name] = TablePosition(x=x, y=y)
        return self.positions[name]

    def set_zoom(self, level: int) -> None:
        self.zoom_level = max(MIN_ZOOM_LEVEL, min(MAX_ZOOM_LEVEL, level))

    def to_dict(self) -> dict[str, Any]:
        return {
            "zoom_level": self.zoom_level,
            "tables": {
                name: {"x": pos.x, "y": pos.y, "visible": pos.visible}
                for name, pos in self.positions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagramLayout:
        positions = {
            name: TablePosition(
                x=entry["x"], y=entry["y"], visible=entry.get("visible", True)
            )
            for name, entry in data.get("tables", {}).items()
        }
        zoom_level = data.get("zoom_level", DEFAULT_ZOOM_LEVEL)
        return cls(positions=positions, zoom_level=zoom_level)


def layout_path_for_file(source_path: Path) -> Path:
    """Sidecar path next to a DDL file, e.g. schema.sql -> schema.sql.layout.json."""
    return source_path.with_name(source_path.name + ".layout.json")


def layout_path_for_key(key: str) -> Path:
    """Sidecar path for a pasted DDL or a DB connection, keyed by a stable hash."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return LAYOUT_DIR / f"{digest}.layout.json"


def load_layout(path: Path) -> DiagramLayout | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return DiagramLayout.from_dict(data)


def save_layout(path: Path, layout: DiagramLayout) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(layout.to_dict(), indent=2), encoding="utf-8")


def build_layout(
    schema: Schema, existing: DiagramLayout | None = None
) -> DiagramLayout:
    """Merge an auto-computed layout with any previously persisted positions."""
    layout = existing if existing is not None else DiagramLayout()
    auto_positions = compute_auto_layout(schema)
    for table in schema.tables:
        layout.ensure_table(table.name, auto_positions.get(table.name, (1, 1)))

    known_tables = {table.name for table in schema.tables}
    layout.positions = {
        name: position
        for name, position in layout.positions.items()
        if name in known_tables
    }
    return layout
