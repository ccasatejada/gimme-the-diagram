from __future__ import annotations

from pathlib import Path

from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.schema.layout import (
    DiagramLayout,
    build_layout,
    layout_path_for_file,
    layout_path_for_key,
    load_layout,
    save_layout,
)

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY);
CREATE TABLE books (id INTEGER PRIMARY KEY, author_id INTEGER REFERENCES authors(id));
"""


def test_build_layout_positions_every_table() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    assert set(layout.positions) == {"authors", "books"}
    assert all(p.visible for p in layout.positions.values())


def test_build_layout_preserves_existing_positions_and_drops_stale_ones() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    existing = DiagramLayout()
    existing.ensure_table("authors", (42, 42))
    existing.positions["authors"].visible = False
    existing.ensure_table("ghost_table", (1, 1))

    layout = build_layout(schema, existing=existing)

    assert layout.positions["authors"].x == 42
    assert layout.positions["authors"].visible is False
    assert "books" in layout.positions
    assert "ghost_table" not in layout.positions


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    layout.set_zoom(1)
    path = tmp_path / "diagram.layout.json"

    save_layout(path, layout)
    loaded = load_layout(path)

    assert loaded is not None
    assert loaded.zoom_level == 1
    assert loaded.positions.keys() == layout.positions.keys()
    assert loaded.positions["authors"].x == layout.positions["authors"].x


def test_load_layout_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_layout(tmp_path / "missing.layout.json") is None


def test_layout_path_for_file() -> None:
    path = layout_path_for_file(Path("/tmp/schema.sql"))
    assert path == Path("/tmp/schema.sql.layout.json")


def test_layout_path_for_key_is_stable() -> None:
    first = layout_path_for_key("same-source")
    second = layout_path_for_key("same-source")
    other = layout_path_for_key("different-source")
    assert first == second
    assert first != other
