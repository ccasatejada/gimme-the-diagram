from __future__ import annotations

from gimme_the_diagram.layout_engine.graphviz_process import (
    GraphvizProcessError,
    run_graphviz_job,
)
from gimme_the_diagram.schema.model import Schema, Table

# Graphviz uses typographic points while the renderer uses terminal character cells.
# A typical monospace cell is approximately twice as tall as it is wide. Keeping the
# conversion explicit also makes the coordinates returned by Graphviz deterministic.
CELL_WIDTH_POINTS = 9.0
CELL_HEIGHT_POINTS = 18.0
CANVAS_MARGIN = 1


def estimate_box_size(table: Table) -> tuple[int, int]:
    """Return the detailed table-box size in terminal cells."""
    lines = [
        table.name,
        *(f"   {column.name}: {column.data_type}" for column in table.columns),
    ]
    content_width = max(len(line) for line in lines)
    return content_width + 4, len(table.columns) + 4


def _foreign_key_pairs(schema: Schema) -> set[tuple[str, str]]:
    """Return unique (referenced table, FK-owning table) layout edges."""
    table_names = {table.name for table in schema.tables}
    pairs: set[tuple[str, str]] = set()
    for table in schema.tables:
        for column in table.columns:
            if not column.is_foreign_key or column.fk_target is None:
                continue
            referenced_table = column.fk_target[0]
            if referenced_table in table_names and referenced_table != table.name:
                pairs.add((referenced_table, table.name))
    return pairs


def compute_graphviz_layout(schema: Schema) -> dict[str, tuple[int, int]]:
    """Place all tables with Graphviz's layered ``dot`` algorithm.

    Raw foreign keys are used instead of the rendered relationships so many-to-many
    junction tables remain part of the component they connect. Parallel FKs are
    deduplicated for placement; they are kept separate later during edge routing.
    """
    if not schema.tables:
        return {}

    sizes: dict[str, tuple[int, int]] = {}
    nodes = []
    for table in sorted(schema.tables, key=lambda item: item.name):
        width, height = estimate_box_size(table)
        sizes[table.name] = (width, height)
        nodes.append(
            {
                "name": table.name,
                "width": width * CELL_WIDTH_POINTS / 72,
                "height": height * CELL_HEIGHT_POINTS / 72,
            }
        )

    try:
        result = run_graphviz_job(
            {
                "operation": "layout",
                "nodes": nodes,
                "edges": sorted(_foreign_key_pairs(schema)),
            },
            timeout=30.0,
        )
    except GraphvizProcessError:
        return _fallback_layout(schema, sizes)

    placed: list[tuple[str, float, float]] = []
    for name, (width, height) in sizes.items():
        center_x, center_y = _parse_point(result["positions"][name])
        placed.append(
            (
                name,
                center_x - width * CELL_WIDTH_POINTS / 2,
                center_y + height * CELL_HEIGHT_POINTS / 2,
            )
        )

    min_left = min(left for _, left, _ in placed)
    max_top = max(top for _, _, top in placed)
    return {
        name: (
            round((left - min_left) / CELL_WIDTH_POINTS) + CANVAS_MARGIN,
            round((max_top - top) / CELL_HEIGHT_POINTS) + CANVAS_MARGIN,
        )
        for name, left, top in placed
    }


def _fallback_layout(
    schema: Schema, sizes: dict[str, tuple[int, int]]
) -> dict[str, tuple[int, int]]:
    """Deterministic bounded grid used when the isolated Graphviz process fails."""
    positions: dict[str, tuple[int, int]] = {}
    x = y = CANVAS_MARGIN
    row_height = 0
    for table in sorted(schema.tables, key=lambda item: item.name):
        width, height = sizes[table.name]
        if x > CANVAS_MARGIN and x + width > 200:
            x = CANVAS_MARGIN
            y += row_height + 3
            row_height = 0
        positions[table.name] = (x, y)
        x += width + 4
        row_height = max(row_height, height)
    return positions


def _parse_point(value: str) -> tuple[float, float]:
    x, y = value.rstrip("!").split(",")
    return float(x), float(y)
