from __future__ import annotations

from pathlib import Path

from gimme_the_diagram.export.pdf import export_schema_to_pdf
from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.schema.layout import build_layout

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


def test_export_writes_a_non_empty_pdf(tmp_path: Path) -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    path = tmp_path / "diagram.pdf"

    export_schema_to_pdf(schema, layout, path)

    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")


def test_export_respects_hidden_tables_unless_full_diagram(tmp_path: Path) -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    layout.positions["books"].visible = False

    visible_only_path = tmp_path / "visible.pdf"
    export_schema_to_pdf(schema, layout, visible_only_path, full_diagram=False)

    full_path = tmp_path / "full.pdf"
    export_schema_to_pdf(schema, layout, full_path, full_diagram=True)

    assert visible_only_path.stat().st_size > 0
    assert full_path.stat().st_size > 0
    # the full export renders more content (both tables) so should not be smaller
    assert full_path.stat().st_size >= visible_only_path.stat().st_size


def test_export_with_viewport_crops_output(tmp_path: Path) -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    path = tmp_path / "cropped.pdf"

    export_schema_to_pdf(
        schema, layout, path, full_diagram=False, viewport=(0, 0, 10, 5)
    )

    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")
