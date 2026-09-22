from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from gimme_the_diagram.render.geometry import Point, Rect
from gimme_the_diagram.render.routing import route_relationships
from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import RelationshipKind, Schema, Table

ZOOM_OVERVIEW = 1
ZOOM_COLUMNS = 2
ZOOM_DETAILED = 3
MIN_ZOOM = ZOOM_OVERVIEW
MAX_ZOOM = ZOOM_DETAILED

_CARDINALITY = {
    RelationshipKind.ONE_TO_ONE: ("1", "1"),
    RelationshipKind.ONE_TO_MANY: ("1", "N"),
    RelationshipKind.MANY_TO_MANY: ("N", "N"),
}

_BOX_STYLE = "box"
_LINE_STYLE = "line"
_TITLE_STYLE = "title"
_PK_STYLE = "pk"
_FK_STYLE = "fk"

# Direction bits, packed into a single int per cell instead of a set[str]: with large
# schemas a relationship can span thousands of cells, so avoiding a set() allocation
# and .add() call per cell (in favor of a dict lookup + int OR) meaningfully matters.
_BIT_UP, _BIT_DOWN, _BIT_LEFT, _BIT_RIGHT = 1, 2, 4, 8
_BIT = {"U": _BIT_UP, "D": _BIT_DOWN, "L": _BIT_LEFT, "R": _BIT_RIGHT}
_OPPOSITE_BIT = {"U": _BIT_DOWN, "D": _BIT_UP, "L": _BIT_RIGHT, "R": _BIT_LEFT}
_DELTA = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
_MASK_TO_CHAR = {
    _BIT_UP | _BIT_DOWN: "│",
    _BIT_LEFT | _BIT_RIGHT: "─",
    _BIT_DOWN | _BIT_RIGHT: "┌",
    _BIT_DOWN | _BIT_LEFT: "┐",
    _BIT_UP | _BIT_RIGHT: "└",
    _BIT_UP | _BIT_LEFT: "┘",
    _BIT_UP | _BIT_DOWN | _BIT_RIGHT: "├",
    _BIT_UP | _BIT_DOWN | _BIT_LEFT: "┤",
    _BIT_LEFT | _BIT_RIGHT | _BIT_DOWN: "┬",
    _BIT_LEFT | _BIT_RIGHT | _BIT_UP: "┴",
    _BIT_UP | _BIT_DOWN | _BIT_LEFT | _BIT_RIGHT: "┼",
    _BIT_UP: "│",
    _BIT_DOWN: "│",
    _BIT_LEFT: "─",
    _BIT_RIGHT: "─",
}


@dataclass(frozen=True)
class CellStyle:
    kind: str = ""
    bold: bool = False


@dataclass(frozen=True)
class Cell:
    char: str = " "
    style: CellStyle = field(default_factory=CellStyle)


EMPTY_CELL = Cell()


@dataclass
class CharGrid:
    width: int
    height: int
    rows: list[list[Cell]] = field(init=False)

    def __post_init__(self) -> None:
        self.rows = [
            [EMPTY_CELL for _ in range(self.width)] for _ in range(self.height)
        ]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def set(self, x: int, y: int, cell: Cell) -> None:
        if self.in_bounds(x, y):
            self.rows[y][x] = cell

    def get(self, x: int, y: int) -> Cell:
        if self.in_bounds(x, y):
            return self.rows[y][x]
        return EMPTY_CELL

    def row_text(self, y: int) -> str:
        return "".join(cell.char for cell in self.rows[y])


def iter_row_runs(row: list[Cell]) -> Iterator[tuple[str, CellStyle]]:
    """Group consecutive same-style cells of a row into (text, style) runs."""
    if not row:
        return
    current_text = row[0].char
    current_style = row[0].style
    for cell in row[1:]:
        if cell.style == current_style:
            current_text += cell.char
        else:
            yield current_text, current_style
            current_text = cell.char
            current_style = cell.style
    yield current_text, current_style


def crop_grid(grid: CharGrid, x: int, y: int, width: int, height: int) -> CharGrid:
    """Extract a sub-rectangle of a grid, e.g. to export exactly what is on screen."""
    cropped = CharGrid(width, height)
    for row_index in range(height):
        source_y = y + row_index
        if source_y >= grid.height:
            break
        for col_index in range(width):
            source_x = x + col_index
            if source_x >= grid.width:
                break
            cropped.rows[row_index][col_index] = grid.get(source_x, source_y)
    return cropped


@dataclass
class TableBox:
    table: Table
    rect: Rect
    content_lines: list[tuple[str, str]]  # (text, style_kind) per interior row


def _box_content(table: Table, zoom_level: int) -> list[tuple[str, str]]:
    if zoom_level <= ZOOM_OVERVIEW:
        return []
    lines: list[tuple[str, str]] = []
    for column in table.columns:
        _check_fk_marker = "FK" if column.is_foreign_key else "  "
        marker = "PK" if column.is_primary_key else _check_fk_marker
        _check_fk_style = _FK_STYLE if column.is_foreign_key else ""
        style = _PK_STYLE if column.is_primary_key else _check_fk_style
        if zoom_level >= ZOOM_DETAILED:
            text = f"{marker} {column.name}: {column.data_type}"
        else:
            text = f"{marker} {column.name}"
        lines.append((text, style))
    return lines


def _box_for_table(table: Table, x: int, y: int, zoom_level: int) -> TableBox:
    content_lines = _box_content(table, zoom_level)
    inner_width = max(
        [len(table.name), *(len(text) for text, _ in content_lines)], default=0
    )
    width = inner_width + 4
    # top border + title + (separator if there are content lines) + content lines + bottom border
    height = 3 + len(content_lines) + (1 if content_lines else 0)
    return TableBox(
        table=table, rect=Rect(x, y, width, height), content_lines=content_lines
    )


def compute_table_boxes(
    schema: Schema, layout: DiagramLayout, zoom_level: int
) -> dict[str, TableBox]:
    """Compute the on-canvas rectangle of every visible table at a given zoom level."""
    boxes: dict[str, TableBox] = {}
    for table in schema.tables:
        position = layout.positions.get(table.name)
        if position is None or not position.visible:
            continue
        boxes[table.name] = _box_for_table(table, position.x, position.y, zoom_level)
    return boxes


def _draw_box(grid: CharGrid, box: TableBox) -> None:
    rect = box.rect
    left, top = rect.x, rect.y
    right, bottom = rect.right - 1, rect.bottom - 1
    inner_width = rect.width - 2

    grid.set(left, top, Cell("┌", CellStyle(_BOX_STYLE)))
    grid.set(right, top, Cell("┐", CellStyle(_BOX_STYLE)))
    grid.set(left, bottom, Cell("└", CellStyle(_BOX_STYLE)))
    grid.set(right, bottom, Cell("┘", CellStyle(_BOX_STYLE)))
    for x in range(left + 1, right):
        grid.set(x, top, Cell("─", CellStyle(_BOX_STYLE)))
        grid.set(x, bottom, Cell("─", CellStyle(_BOX_STYLE)))
    for y in range(top + 1, bottom):
        grid.set(left, y, Cell("│", CellStyle(_BOX_STYLE)))
        grid.set(right, y, Cell("│", CellStyle(_BOX_STYLE)))

    _draw_text_row(grid, left + 1, top + 1, inner_width, box.table.name, _TITLE_STYLE)
    if box.content_lines:
        separator_y = top + 2
        for x in range(left + 1, right):
            grid.set(x, separator_y, Cell("─", CellStyle(_BOX_STYLE)))
        for index, (text, style) in enumerate(box.content_lines):
            _draw_text_row(
                grid, left + 1, separator_y + 1 + index, inner_width, text, style
            )


def _draw_text_row(
    grid: CharGrid, x: int, y: int, width: int, text: str, style_kind: str
) -> None:
    padded = text[:width].ljust(width)
    for offset, char in enumerate(padded):
        style = CellStyle(style_kind, bold=style_kind in (_TITLE_STYLE, _PK_STYLE))
        grid.set(x + offset, y, Cell(char, style))


def _direction(delta_x: int, delta_y: int) -> str:
    if delta_x > 0:
        return "R"
    if delta_x < 0:
        return "L"
    if delta_y > 0:
        return "D"
    return "U"


def _walk_path_bits(points: list[Point], bits: dict[Point, int]) -> None:
    """Accumulate direction bits for every cell along a polyline, in place."""
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        if x1 == x2 and y1 == y2:
            continue
        direction = _direction(x2 - x1, y2 - y1)
        dbit = _BIT[direction]
        obit = _OPPOSITE_BIT[direction]
        dx, dy = _DELTA[direction]
        x, y = x1, y1
        while (x, y) != (x2, y2):
            nx, ny = x + dx, y + dy
            bits[(x, y)] = bits.get((x, y), 0) | dbit
            bits[(nx, ny)] = bits.get((nx, ny), 0) | obit
            x, y = nx, ny


def _draw_relationship_lines(
    grid: CharGrid,
    schema: Schema,
    routes: dict[int, list[Point]],
) -> None:
    all_bits: dict[Point, int] = {}
    endpoints: dict[Point, str] = {}

    for index, relationship in enumerate(schema.relationships):
        points = routes.get(index)
        if points is None:
            continue
        _walk_path_bits(points, all_bits)
        start_marker, end_marker = _CARDINALITY[relationship.kind]
        endpoints[points[0]] = start_marker
        endpoints[points[-1]] = end_marker

    line_style = CellStyle(_LINE_STYLE)
    for point, mask in all_bits.items():
        char = _MASK_TO_CHAR.get(mask)
        if char is None:
            continue
        grid.set(point[0], point[1], Cell(char, line_style))

    marker_style = CellStyle(_LINE_STYLE, bold=True)
    for point, marker in endpoints.items():
        grid.set(point[0], point[1], Cell(marker, marker_style))


def diagram_size(
    boxes: dict[str, TableBox], routes: dict[int, list[Point]] | None = None
) -> tuple[int, int]:
    if not boxes:
        return (1, 1)
    width = max(box.rect.right for box in boxes.values()) + 1
    height = max(box.rect.bottom for box in boxes.values()) + 1
    route_points = [point for points in (routes or {}).values() for point in points]
    if route_points:
        width = max(width, max(x for x, _ in route_points) + 1)
        height = max(height, max(y for _, y in route_points) + 1)
    return width, height


def render_diagram(
    schema: Schema, layout: DiagramLayout, zoom_level: int | None = None
) -> CharGrid:
    """Render the (visible) tables and relationships of a schema into a CharGrid."""
    level = zoom_level if zoom_level is not None else layout.zoom_level
    level = max(MIN_ZOOM, min(MAX_ZOOM, level))

    boxes = compute_table_boxes(schema, layout, level)
    routes = route_relationships(
        {name: box.rect for name, box in boxes.items()}, schema.relationships
    )
    width, height = diagram_size(boxes, routes)
    grid = CharGrid(width, height)

    _draw_relationship_lines(grid, schema, routes)
    for box in boxes.values():
        _draw_box(grid, box)

    return grid
