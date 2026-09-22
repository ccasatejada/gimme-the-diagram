from __future__ import annotations

from dataclasses import dataclass

from gimme_the_diagram.render.geometry import Point
from gimme_the_diagram.render.grid import TableBox, compute_table_boxes
from gimme_the_diagram.render.routing import route_relationships
from gimme_the_diagram.schema.layout import DiagramLayout, TablePosition
from gimme_the_diagram.schema.model import Schema


@dataclass(frozen=True)
class ExportGeometry:
    boxes: dict[str, TableBox]
    routes: dict[int, list[Point]]
    x: int
    y: int
    width: int
    height: int


def all_visible_layout(layout: DiagramLayout) -> DiagramLayout:
    positions = {
        name: TablePosition(x=position.x, y=position.y, visible=True)
        for name, position in layout.positions.items()
    }
    return DiagramLayout(positions=positions, zoom_level=layout.zoom_level)


def build_export_geometry(
    schema: Schema,
    layout: DiagramLayout,
    *,
    full_diagram: bool,
    viewport: tuple[int, int, int, int] | None = None,
) -> ExportGeometry:
    render_layout = all_visible_layout(layout) if full_diagram else layout
    boxes = compute_table_boxes(schema, render_layout, render_layout.zoom_level)
    routes = route_relationships(
        {name: box.rect for name, box in boxes.items()}, schema.relationships
    )
    if viewport is not None and not full_diagram:
        x, y, width, height = viewport
        return ExportGeometry(boxes, routes, x, y, max(1, width), max(1, height))

    points = [point for route in routes.values() for point in route]
    min_x = min([box.rect.x for box in boxes.values()] + [p[0] for p in points] + [0])
    min_y = min([box.rect.y for box in boxes.values()] + [p[1] for p in points] + [0])
    max_x = max(
        [box.rect.right for box in boxes.values()] + [p[0] + 1 for p in points] + [1]
    )
    max_y = max(
        [box.rect.bottom for box in boxes.values()] + [p[1] + 1 for p in points] + [1]
    )
    return ExportGeometry(boxes, routes, min_x, min_y, max_x - min_x, max_y - min_y)
