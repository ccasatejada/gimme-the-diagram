from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen.canvas import Canvas

from gimme_the_diagram.export.vector import ExportGeometry, build_export_geometry
from gimme_the_diagram.render.grid import (
    CharGrid,
    iter_row_runs,
)
from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import RelationshipKind, Schema

FONT_NAME = "Courier"
FONT_NAME_BOLD = "Courier-Bold"
FONT_SIZE = 10.0
CHAR_WIDTH = FONT_SIZE * 0.6
LINE_HEIGHT = FONT_SIZE * 1.2
MARGIN = 20.0
VECTOR_CELL_WIDTH = 6.0
VECTOR_CELL_HEIGHT = 11.0
PAGE_MARGIN = 28.0
TILE_OVERLAP = 3

_COLORS: dict[str, Color] = {
    "": black,
    "box": Color(0.4, 0.4, 0.4),
    "title": black,
    "pk": Color(0.6, 0.4, 0.0),
    "fk": Color(0.0, 0.3, 0.6),
    "line": Color(0.5, 0.5, 0.5),
}


def render_grid_to_pdf(grid: CharGrid, path: Path) -> None:
    """Render a CharGrid to a monospace, terminal-faithful PDF page."""
    width = MARGIN * 2 + grid.width * CHAR_WIDTH
    height = MARGIN * 2 + grid.height * LINE_HEIGHT
    canvas = Canvas(str(path), pagesize=(width, height))

    for y, row in enumerate(grid.rows):
        baseline_y = height - MARGIN - (y + 1) * LINE_HEIGHT
        x = MARGIN
        for text, style in iter_row_runs(row):
            if text.strip():
                canvas.setFont(FONT_NAME_BOLD if style.bold else FONT_NAME, FONT_SIZE)
                canvas.setFillColor(_COLORS.get(style.kind, black))
                canvas.drawString(x, baseline_y, text)
            x += len(text) * CHAR_WIDTH

    canvas.showPage()
    canvas.save()


_CARDINALITY = {
    RelationshipKind.ONE_TO_ONE: ("1", "1"),
    RelationshipKind.ONE_TO_MANY: ("1", "N"),
    RelationshipKind.MANY_TO_MANY: ("N", "N"),
}


def export_schema_to_pdf(
    schema: Schema,
    layout: DiagramLayout,
    path: Path,
    *,
    full_diagram: bool = False,
    viewport: tuple[int, int, int, int] | None = None,
) -> None:
    """Export a vector PDF: overview first, then readable A3 detail tiles."""
    geometry = build_export_geometry(
        schema, layout, full_diagram=full_diagram, viewport=viewport
    )
    page_width, page_height = landscape(A3)
    canvas = Canvas(str(path), pagesize=(page_width, page_height))
    usable_width = page_width - 2 * PAGE_MARGIN
    usable_height = page_height - 2 * PAGE_MARGIN

    overview_scale = min(
        usable_width / max(1.0, geometry.width * VECTOR_CELL_WIDTH),
        usable_height / max(1.0, geometry.height * VECTOR_CELL_HEIGHT),
        1.0,
    )
    _draw_vector_page(
        canvas,
        schema,
        geometry,
        (geometry.x, geometry.y, geometry.width, geometry.height),
        overview_scale,
        details=False,
        title="Diagram overview",
        page_height=page_height,
    )
    canvas.showPage()

    if not full_diagram and viewport is not None:
        detail_scale = min(
            usable_width / max(1.0, geometry.width * VECTOR_CELL_WIDTH),
            usable_height / max(1.0, geometry.height * VECTOR_CELL_HEIGHT),
            1.0,
        )
        _draw_vector_page(
            canvas,
            schema,
            geometry,
            (geometry.x, geometry.y, geometry.width, geometry.height),
            detail_scale,
            details=True,
            title="Current view",
            page_height=page_height,
        )
        canvas.showPage()
    else:
        tile_width = max(1, int(usable_width // VECTOR_CELL_WIDTH))
        tile_height = max(1, int(usable_height // VECTOR_CELL_HEIGHT))
        step_x = max(1, tile_width - TILE_OVERLAP)
        step_y = max(1, tile_height - TILE_OVERLAP)
        tile_number = 0
        y = geometry.y
        while y < geometry.y + geometry.height:
            x = geometry.x
            while x < geometry.x + geometry.width:
                tile_number += 1
                _draw_vector_page(
                    canvas,
                    schema,
                    geometry,
                    (x, y, tile_width, tile_height),
                    1.0,
                    details=True,
                    title=f"Detail tile {tile_number} — origin ({x}, {y})",
                    page_height=page_height,
                )
                canvas.showPage()
                x += step_x
            y += step_y
    canvas.save()


def _draw_vector_page(
    canvas: Canvas,
    schema: Schema,
    geometry: ExportGeometry,
    region: tuple[int, int, int, int],
    scale: float,
    *,
    details: bool,
    title: str,
    page_height: float,
) -> None:
    region_x, region_y, region_width, region_height = region

    def page_x(x: float) -> float:
        return PAGE_MARGIN + (x - region_x) * VECTOR_CELL_WIDTH * scale

    def page_y(y: float) -> float:
        return page_height - PAGE_MARGIN - (y - region_y) * VECTOR_CELL_HEIGHT * scale

    canvas.saveState()
    clip = canvas.beginPath()
    clip.rect(
        PAGE_MARGIN,
        PAGE_MARGIN,
        region_width * VECTOR_CELL_WIDTH * scale,
        region_height * VECTOR_CELL_HEIGHT * scale,
    )
    canvas.clipPath(clip, stroke=0, fill=0)

    canvas.setStrokeColor(_COLORS["line"])
    canvas.setLineWidth(max(0.5, scale))
    for index, relationship in enumerate(schema.relationships):
        route = geometry.routes.get(index)
        if not route:
            continue
        path = canvas.beginPath()
        path.moveTo(page_x(route[0][0]), page_y(route[0][1]))
        for x, y in route[1:]:
            path.lineTo(page_x(x), page_y(y))
        canvas.drawPath(path)
        if details:
            start, end = _CARDINALITY[relationship.kind]
            canvas.setFont(FONT_NAME_BOLD, max(5.0, 8.0 * scale))
            canvas.drawString(page_x(route[0][0]), page_y(route[0][1]), start)
            canvas.drawString(page_x(route[-1][0]), page_y(route[-1][1]), end)

    for box in geometry.boxes.values():
        rect = box.rect
        left = page_x(rect.x)
        bottom = page_y(rect.bottom)
        width = rect.width * VECTOR_CELL_WIDTH * scale
        height = rect.height * VECTOR_CELL_HEIGHT * scale
        canvas.setStrokeColor(_COLORS["box"])
        canvas.setFillColor(Color(1, 1, 1))
        canvas.rect(left, bottom, width, height, stroke=1, fill=1)
        canvas.setFillColor(black)
        canvas.setFont(FONT_NAME_BOLD, max(3.0, 8.0 * scale))
        canvas.drawString(page_x(rect.x + 1), page_y(rect.y + 1.4), box.table.name)
        if not details or not box.content_lines:
            continue
        separator_y = page_y(rect.y + 2)
        canvas.line(left, separator_y, left + width, separator_y)
        for row, (text, style) in enumerate(box.content_lines):
            canvas.setFillColor(_COLORS.get(style, black))
            canvas.setFont(
                FONT_NAME_BOLD if style == "pk" else FONT_NAME,
                max(5.0, 7.5 * scale),
            )
            canvas.drawString(page_x(rect.x + 1), page_y(rect.y + 3.2 + row), text)
    canvas.restoreState()
    canvas.setFillColor(black)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(PAGE_MARGIN, 12, title)
