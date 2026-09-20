from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.pdfgen.canvas import Canvas

from gimme_the_diagram.render.grid import (
    CharGrid,
    crop_grid,
    iter_row_runs,
    render_diagram,
)
from gimme_the_diagram.schema.layout import DiagramLayout, TablePosition
from gimme_the_diagram.schema.model import Schema

FONT_NAME = "Courier"
FONT_NAME_BOLD = "Courier-Bold"
FONT_SIZE = 10.0
CHAR_WIDTH = FONT_SIZE * 0.6
LINE_HEIGHT = FONT_SIZE * 1.2
MARGIN = 20.0

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


def _all_visible(layout: DiagramLayout) -> DiagramLayout:
    positions = {
        name: TablePosition(x=position.x, y=position.y, visible=True)
        for name, position in layout.positions.items()
    }
    return DiagramLayout(positions=positions, zoom_level=layout.zoom_level)


def export_schema_to_pdf(
    schema: Schema,
    layout: DiagramLayout,
    path: Path,
    *,
    full_diagram: bool = False,
    viewport: tuple[int, int, int, int] | None = None,
) -> None:
    """Export a schema to PDF.

    - `full_diagram=False` (default): only tables currently visible via the sidebar.
      If `viewport` (x, y, width, height) is given, the export is further cropped to
      exactly what is on screen right now.
    - `full_diagram=True`: every table in the schema, ignoring sidebar visibility and
      any viewport.
    """
    render_layout = _all_visible(layout) if full_diagram else layout
    grid = render_diagram(schema, render_layout)

    if not full_diagram and viewport is not None:
        x, y, width, height = viewport
        grid = crop_grid(grid, x, y, width, height)

    render_grid_to_pdf(grid, path)
