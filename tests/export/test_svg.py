from __future__ import annotations

import xml.etree.ElementTree as ElementTree

from gimme_the_diagram.export.svg import export_schema_to_svg
from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.schema.layout import build_layout


def test_svg_export_is_valid_and_contains_tables(tmp_path) -> None:  # type: ignore[no-untyped-def]
    schema = parse_ddl(
        "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
        "CREATE TABLE child (id INTEGER, parent_id INTEGER REFERENCES parent(id));"
    )
    layout = build_layout(schema)
    path = tmp_path / "diagram.svg"

    export_schema_to_svg(schema, layout, path, full_diagram=True)

    root = ElementTree.parse(path).getroot()
    assert root.tag.endswith("svg")
    content = path.read_text(encoding="utf-8")
    assert "parent" in content
    assert "child" in content
    assert "polyline" in content
