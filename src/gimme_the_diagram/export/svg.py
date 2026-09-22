from __future__ import annotations

from html import escape
from pathlib import Path

from gimme_the_diagram.export.vector import build_export_geometry
from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import RelationshipKind, Schema

CELL_WIDTH = 8
CELL_HEIGHT = 16
FONT_SIZE = 12

_CARDINALITY = {
    RelationshipKind.ONE_TO_ONE: ("1", "1"),
    RelationshipKind.ONE_TO_MANY: ("1", "N"),
    RelationshipKind.MANY_TO_MANY: ("N", "N"),
}


def export_schema_to_svg(
    schema: Schema,
    layout: DiagramLayout,
    path: Path,
    *,
    full_diagram: bool = False,
    viewport: tuple[int, int, int, int] | None = None,
) -> None:
    """Export a scalable, searchable vector diagram that preserves the layout."""
    geometry = build_export_geometry(
        schema, layout, full_diagram=full_diagram, viewport=viewport
    )
    origin_x = geometry.x * CELL_WIDTH
    origin_y = geometry.y * CELL_HEIGHT
    width = geometry.width * CELL_WIDTH
    height = geometry.height * CELL_HEIGHT
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="{origin_x} {origin_y} {width} {height}">'
        ),
        "<style>text{font-family:monospace;font-size:12px}.title{font-weight:bold}"
        ".pk{font-weight:bold;fill:#996600}.fk{fill:#006699}"
        ".box{fill:white;stroke:#666}.edge{fill:none;stroke:#888;stroke-width:1.5}"
        ".marker{font-weight:bold;fill:#555}</style>",
        f'<rect x="{origin_x}" y="{origin_y}" width="{width}" height="{height}" fill="white"/>',
    ]

    for index, relationship in enumerate(schema.relationships):
        route = geometry.routes.get(index)
        if not route:
            continue
        points = " ".join(f"{x * CELL_WIDTH},{y * CELL_HEIGHT}" for x, y in route)
        lines.append(f'<polyline class="edge" points="{points}"/>')
        start, end = _CARDINALITY[relationship.kind]
        for marker, (x, y) in ((start, route[0]), (end, route[-1])):
            lines.append(
                f'<text class="marker" x="{x * CELL_WIDTH}" '
                f'y="{y * CELL_HEIGHT + FONT_SIZE / 3:g}">{marker}</text>'
            )

    for box in geometry.boxes.values():
        rect = box.rect
        x = rect.x * CELL_WIDTH
        y = rect.y * CELL_HEIGHT
        width_px = rect.width * CELL_WIDTH
        height_px = rect.height * CELL_HEIGHT
        lines.append(
            f'<rect class="box" x="{x}" y="{y}" width="{width_px}" height="{height_px}"/>'
        )
        lines.append(
            f'<text class="title" x="{x + CELL_WIDTH}" y="{y + FONT_SIZE + 3}">'
            f"{escape(box.table.name)}</text>"
        )
        if box.content_lines:
            separator_y = y + 2 * CELL_HEIGHT
            lines.append(
                f'<line class="box" x1="{x}" y1="{separator_y}" '
                f'x2="{x + width_px}" y2="{separator_y}"/>'
            )
            for row, (text, style) in enumerate(box.content_lines):
                css_class = style if style in {"pk", "fk"} else ""
                lines.append(
                    f'<text class="{css_class}" x="{x + CELL_WIDTH}" '
                    f'y="{separator_y + (row + 1) * CELL_HEIGHT - 3}">'
                    f"{escape(text)}</text>"
                )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
