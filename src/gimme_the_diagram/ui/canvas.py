from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from gimme_the_diagram.render.grid import (
    MAX_ZOOM,
    MIN_ZOOM,
    Cell,
    CharGrid,
    compute_table_boxes,
    iter_row_runs,
    render_diagram,
)
from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import Schema

_STYLE_BASE: dict[str, Style] = {
    "": Style(),
    "box": Style(color="grey66"),
    "title": Style(bold=True),
    "pk": Style(bold=True, color="gold3"),
    "fk": Style(color="cyan"),
    "line": Style(color="grey50"),
}


def _rich_style(kind: str, bold: bool) -> Style:
    style = _STYLE_BASE.get(kind, Style())
    if bold and not style.bold:
        style += Style(bold=True)
    return style


def _row_to_strip(row: list[Cell], width: int) -> Strip:
    segments = [
        Segment(text, _rich_style(style.kind, style.bold))
        for text, style in iter_row_runs(row)
    ]
    return Strip(segments, width)


class DiagramCanvas(ScrollView, can_focus=True):
    """Pannable, zoomable ERD canvas with drag & drop of tables."""

    BINDINGS = [
        Binding("plus,equals_sign", "zoom_in", "Zoom in", show=False),
        Binding("minus", "zoom_out", "Zoom out", show=False),
    ]

    class LayoutChanged(Message):
        """Posted when the user drags a table or changes the zoom level."""

    def __init__(self, schema: Schema, diagram_layout: DiagramLayout) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout
        self._grid: CharGrid | None = None
        self._row_strips: list[Strip] = []
        self._dragged_table: str | None = None

    def on_mount(self) -> None:
        self.refresh_diagram()

    def set_schema(self, schema: Schema, diagram_layout: DiagramLayout) -> None:
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.refresh_diagram()

    def refresh_diagram(self) -> None:
        grid = render_diagram(self.schema, self.diagram_layout)
        self._grid = grid
        self._row_strips = [
            _row_to_strip(grid.rows[y], grid.width) for y in range(grid.height)
        ]
        self.virtual_size = Size(grid.width, grid.height)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        if self._grid is None:
            return Strip.blank(self.size.width)
        scroll_x, scroll_y = self.scroll_offset
        virtual_y = scroll_y + y
        if virtual_y >= len(self._row_strips):
            return Strip.blank(self.size.width)
        strip = self._row_strips[virtual_y].crop(scroll_x, scroll_x + self.size.width)
        return strip.extend_cell_length(self.size.width)

    def action_zoom_in(self) -> None:
        self.zoom_in()

    def action_zoom_out(self) -> None:
        self.zoom_out()

    def zoom_in(self) -> None:
        self._set_zoom(self.diagram_layout.zoom_level + 1)

    def zoom_out(self) -> None:
        self._set_zoom(self.diagram_layout.zoom_level - 1)

    def _set_zoom(self, level: int) -> None:
        clamped = max(MIN_ZOOM, min(MAX_ZOOM, level))
        if clamped == self.diagram_layout.zoom_level:
            return
        self.diagram_layout.set_zoom(clamped)
        self.refresh_diagram()
        self.post_message(self.LayoutChanged())

    def _table_at(self, virtual_x: int, virtual_y: int) -> str | None:
        boxes = compute_table_boxes(
            self.schema, self.diagram_layout, self.diagram_layout.zoom_level
        )
        for name, box in boxes.items():
            if box.rect.contains(virtual_x, virtual_y):
                return name
        return None

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.zoom_out()
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.zoom_in()
        event.stop()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        virtual_x = event.x + self.scroll_offset.x
        virtual_y = event.y + self.scroll_offset.y
        self._dragged_table = self._table_at(virtual_x, virtual_y)
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragged_table is not None:
            position = self.diagram_layout.positions.get(self._dragged_table)
            if position is not None:
                position.x = max(0, position.x + event.delta_x)
                position.y = max(0, position.y + event.delta_y)
                self.refresh_diagram()
            event.stop()
        elif self.app.mouse_captured is self:
            self.scroll_relative(x=-event.delta_x, y=-event.delta_y, animate=False)
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.release_mouse()
        if self._dragged_table is not None:
            self._dragged_table = None
            self.post_message(self.LayoutChanged())
        event.stop()
