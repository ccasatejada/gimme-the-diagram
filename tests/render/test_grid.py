from __future__ import annotations

import time

from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.render.grid import (
    ZOOM_COLUMNS,
    ZOOM_DETAILED,
    ZOOM_OVERVIEW,
    crop_grid,
    iter_row_runs,
    render_diagram,
)
from gimme_the_diagram.schema.layout import build_layout

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


def _grid_text(grid) -> list[str]:  # type: ignore[no-untyped-def]
    return [grid.row_text(y) for y in range(grid.height)]


def test_renders_a_box_per_visible_table() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    text = "\n".join(_grid_text(grid))
    assert "authors" in text
    assert "books" in text
    assert "author_id: INT" in text


def test_hidden_table_is_not_rendered() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    layout.positions["books"].visible = False
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    text = "\n".join(_grid_text(grid))
    assert "authors" in text
    assert "books" not in text


def test_overview_zoom_hides_columns() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_OVERVIEW)
    text = "\n".join(_grid_text(grid))
    assert "authors" in text
    assert "name" not in text


def test_columns_zoom_shows_names_without_types() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_COLUMNS)
    text = "\n".join(_grid_text(grid))
    assert "author_id" in text
    assert "INT" not in text


def test_relationship_line_is_drawn_between_boxes() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    text = "\n".join(_grid_text(grid))
    assert "│" in text or "─" in text
    assert "1" in text
    assert "N" in text


def test_iter_row_runs_groups_consecutive_same_style_cells() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    row = grid.rows[0]
    runs = list(iter_row_runs(row))
    assert "".join(text for text, _ in runs) == grid.row_text(0)


def test_crop_grid_extracts_sub_rectangle() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    cropped = crop_grid(grid, 0, 0, 5, 3)
    assert cropped.width == 5
    assert cropped.height == 3
    assert cropped.row_text(0) == grid.row_text(0)[:5]


def test_crop_grid_beyond_bounds_pads_with_blank() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    grid = render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    cropped = crop_grid(grid, grid.width - 2, grid.height - 2, 10, 10)
    assert cropped.width == 10
    assert cropped.height == 10


def test_large_schema_renders_within_a_bounded_time() -> None:
    """Regression guard: a ~150-table schema used to take hundreds of ms per render
    (relationship lines spanning thousands of columns of an unbounded-width layout),
    which froze the app while dragging a table (each mouse-move re-renders). This
    should stay comfortably fast even on slow CI machines."""
    table_count = 150
    statements = [
        f"CREATE TABLE t{i} (id INTEGER PRIMARY KEY, name VARCHAR(255));"
        for i in range(table_count)
    ]
    statements += [
        f"ALTER TABLE t{i} ADD CONSTRAINT fk_{i} FOREIGN KEY (id) REFERENCES t{i - 1}(id);"
        for i in range(1, table_count)
    ]
    schema = parse_ddl("\n".join(statements))
    layout = build_layout(schema)

    start = time.perf_counter()
    render_diagram(schema, layout, zoom_level=ZOOM_DETAILED)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
