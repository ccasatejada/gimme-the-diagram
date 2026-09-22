from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual import events
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
    """Pannable ERD canvas with drag & drop of tables.

    "Detail level" (`detail_up`/`detail_down`) controls how much information is shown
    inside each table (name only / columns / columns with types). It is persisted as
    part of the layout.
    """

    class LayoutChanged(Message):
        """Posted when the user drags a table or changes the detail level."""

    #: Cap on how often a drag re-renders the diagram. Re-rendering can take well over
    #: a mouse-move's worth of time for a large schema (hundreds of tables); without a
    #: cap, dragging would queue up a full re-render per pixel of movement and the
    #: whole app would appear to hang until it worked through the backlog.
    DRAG_REFRESH_INTERVAL = 1 / 20

    def __init__(
        self,
        schema: Schema,
        diagram_layout: DiagramLayout,
        initial_grid: CharGrid | None = None,
    ) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout
        self._grid: CharGrid | None = initial_grid
        self._row_strips: list[Strip] = []
        self._dragged_table: str | None = None
        self._drag_refresh_pending = False

    def on_mount(self) -> None:
        if self._grid is None:
            self.refresh_diagram()
        else:
            self._apply_grid(self._grid)

    def set_schema(self, schema: Schema, diagram_layout: DiagramLayout) -> None:
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.refresh_diagram()

    def refresh_diagram(self) -> None:
        self._apply_grid(render_diagram(self.schema, self.diagram_layout))

    def _apply_grid(self, grid: CharGrid) -> None:
        self._grid = grid
        self._row_strips = [
            _row_to_strip(grid.rows[y], grid.width) for y in range(grid.height)
        ]
        self.virtual_size = Size(grid.width, grid.height)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        if self._grid is None:
            return Strip.blank(self.size.width, Style())
        scroll_x, scroll_y = self.scroll_offset
        virtual_y = scroll_y + y
        if virtual_y >= len(self._row_strips):
            return Strip.blank(self.size.width, Style())
        strip = self._row_strips[virtual_y].crop(scroll_x, scroll_x + self.size.width)
        return strip.extend_cell_length(self.size.width, Style())

    def scroll_to_table(self, name: str) -> None:
        """Pan the canvas so the given table's top-left corner comes into view."""
        position = self.diagram_layout.positions.get(name)
        if position is None:
            return
        self.scroll_to(position.x, position.y, animate=False)

    # -- detail level (how much info is shown inside each table) -----------------

    def detail_up(self) -> None:
        self._set_detail_level(self.diagram_layout.zoom_level + 1)

    def detail_down(self) -> None:
        self._set_detail_level(self.diagram_layout.zoom_level - 1)

    def _set_detail_level(self, level: int) -> None:
        clamped = max(MIN_ZOOM, min(MAX_ZOOM, level))
        if clamped == self.diagram_layout.zoom_level:
            return
        self.diagram_layout.set_zoom(clamped)
        self.refresh_diagram()
        self.post_message(self.LayoutChanged())

    def _table_at(self, world_x: int, world_y: int) -> str | None:
        boxes = compute_table_boxes(
            self.schema, self.diagram_layout, self.diagram_layout.zoom_level
        )
        for name, box in boxes.items():
            if box.rect.contains(world_x, world_y):
                return name
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        world_x = event.x + self.scroll_offset.x
        world_y = event.y + self.scroll_offset.y
        self._dragged_table = self._table_at(world_x, world_y)
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragged_table is not None:
            position = self.diagram_layout.positions.get(self._dragged_table)
            if position is not None:
                position.x = max(0, position.x + event.delta_x)
                position.y = max(0, position.y + event.delta_y)
                self._request_throttled_refresh()
            event.stop()
            return
        if self.app.mouse_captured is self:
            self.scroll_relative(x=-event.delta_x, y=-event.delta_y, animate=False)
            event.stop()
            return
        # Hovering (not dragging/panning): hint that a table can be picked up.
        # Requires terminal support for the Kitty pointer-shape protocol.
        world_x = event.x + self.scroll_offset.x
        world_y = event.y + self.scroll_offset.y
        self.styles.pointer = (
            "grab" if self._table_at(world_x, world_y) is not None else "default"
        )

    def _request_throttled_refresh(self) -> None:
        if self._drag_refresh_pending:
            return
        self._drag_refresh_pending = True
        self.set_timer(self.DRAG_REFRESH_INTERVAL, self._run_throttled_refresh)

    def _run_throttled_refresh(self) -> None:
        self._drag_refresh_pending = False
        if self._dragged_table is not None:
            self.refresh_diagram()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.release_mouse()
        if self._dragged_table is not None:
            self._dragged_table = None
            self.refresh_diagram()  # make sure the final position is rendered exactly
            self.post_message(self.LayoutChanged())
        event.stop()
