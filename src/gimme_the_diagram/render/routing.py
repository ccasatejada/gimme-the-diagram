from __future__ import annotations

from collections.abc import Iterable, Mapping

from gimme_the_diagram.layout_engine.graphviz_layout import (
    CELL_HEIGHT_POINTS,
    CELL_WIDTH_POINTS,
)
from gimme_the_diagram.layout_engine.graphviz_process import (
    GraphvizProcessError,
    run_graphviz_job,
)
from gimme_the_diagram.render.geometry import Point, Rect
from gimme_the_diagram.schema.model import Relationship

# The node rectangles must match the renderer exactly. Inflating them can make nearby
# pinned nodes touch, at which point Graphviz deliberately falls back to straight
# edges instead of obstacle-aware orthogonal routing.
ROUTE_CLEARANCE = 0
ORTHOGONAL_NODE_LIMIT = 150
ORTHOGONAL_EDGE_LIMIT = 200


def route_relationships(
    boxes: Mapping[str, Rect], relationships: Iterable[Relationship]
) -> dict[int, list[Point]]:
    """Route all visible relationships together around all visible table boxes.

    ``neato -n2`` preserves the supplied node positions and only routes the edges.
    This is what lets users drag tables without Graphviz undoing their arrangement.
    The dictionary keys are indices in ``relationships`` so parallel relationships
    between the same pair of tables remain distinct.
    """
    relationship_list = list(relationships)
    active = [
        (index, relationship)
        for index, relationship in enumerate(relationship_list)
        if relationship.left_table in boxes and relationship.right_table in boxes
    ]
    if not active:
        return {}

    intended_centers: dict[str, tuple[float, float]] = {}
    nodes = []
    for name, rect in sorted(boxes.items()):
        center_x = (rect.x + rect.width / 2) * CELL_WIDTH_POINTS
        # Graphviz's Y axis points upwards; terminal-grid Y points downwards.
        center_y = -(rect.y + rect.height / 2) * CELL_HEIGHT_POINTS
        intended_centers[name] = (center_x, center_y)
        nodes.append(
            {
                "name": name,
                "pos": f"{center_x / 72},{center_y / 72}!",
                "width": (rect.width + 2 * ROUTE_CLEARANCE) * CELL_WIDTH_POINTS / 72,
                "height": (rect.height + 2 * ROUTE_CLEARANCE) * CELL_HEIGHT_POINTS / 72,
            }
        )

    edges = [
        {
            "index": index,
            "source": relationship.left_table,
            "target": relationship.right_table,
        }
        for index, relationship in active
    ]
    splines = (
        "polyline"
        if len(nodes) > ORTHOGONAL_NODE_LIMIT or len(edges) > ORTHOGONAL_EDGE_LIMIT
        else "ortho"
    )
    try:
        result = run_graphviz_job(
            {
                "operation": "route",
                "nodes": nodes,
                "edges": edges,
                "splines": splines,
            }
        )
    except GraphvizProcessError:
        if splines != "ortho":
            return _fallback_routes(boxes, active)
        try:
            result = run_graphviz_job(
                {
                    "operation": "route",
                    "nodes": nodes,
                    "edges": edges,
                    "splines": "polyline",
                }
            )
        except GraphvizProcessError:
            return _fallback_routes(boxes, active)

    first_name = next(iter(sorted(boxes)))
    output_center = _parse_point(result["positions"][first_name])
    intended_center = intended_centers[first_name]
    offset_x = output_center[0] - intended_center[0]
    offset_y = output_center[1] - intended_center[1]

    routes: dict[int, list[Point]] = {}
    for edge in result["edges"]:
        index = int(edge["index"])
        graphviz_points = _parse_edge_points(edge["pos"])
        points = [
            (
                round((x - offset_x) / CELL_WIDTH_POINTS),
                round(-(y - offset_y) / CELL_HEIGHT_POINTS),
            )
            for x, y in graphviz_points
        ]
        simplified = _simplify_orthogonal(points)
        if len(simplified) >= 2:
            relationship = relationship_list[index]
            routes[index] = _place_endpoints_outside_boxes(
                simplified,
                boxes[relationship.left_table],
                boxes[relationship.right_table],
            )

    # A self-loop or degenerate Graphviz route may not produce a usable polyline.
    for index, relationship in active:
        if index not in routes:
            routes[index] = route(
                boxes[relationship.left_table], boxes[relationship.right_table]
            )
    return routes


def _fallback_routes(
    boxes: Mapping[str, Rect], active: list[tuple[int, Relationship]]
) -> dict[int, list[Point]]:
    return {
        index: route(boxes[relationship.left_table], boxes[relationship.right_table])
        for index, relationship in active
    }


def _parse_point(value: str) -> tuple[float, float]:
    x, y = value.rstrip("!").split(",")
    return float(x), float(y)


def _parse_edge_points(value: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for token in value.replace(";", " ").split():
        fields = token.split(",")
        if fields[0] in {"e", "s"}:
            fields = fields[1:]
        if len(fields) == 2:
            points.append((float(fields[0]), float(fields[1])))
    return points


def _simplify_orthogonal(points: list[Point]) -> list[Point]:
    """Remove Graphviz control-point repetitions after terminal-cell rounding."""
    orthogonal: list[Point] = []
    for point in points:
        if orthogonal and point == orthogonal[-1]:
            continue
        if (
            orthogonal
            and point[0] != orthogonal[-1][0]
            and point[1] != orthogonal[-1][1]
        ):
            bend = (orthogonal[-1][0], point[1])
            if bend != orthogonal[-1]:
                orthogonal.append(bend)
        orthogonal.append(point)

    simplified: list[Point] = []
    for point in orthogonal:
        if len(simplified) >= 2:
            before, previous = simplified[-2], simplified[-1]
            if (before[0] == previous[0] == point[0]) or (
                before[1] == previous[1] == point[1]
            ):
                simplified[-1] = point
                continue
        simplified.append(point)
    return simplified


def _place_endpoints_outside_boxes(
    points: list[Point], source: Rect, target: Rect
) -> list[Point]:
    """Move rounded Graphviz endpoints to the cells just outside each box.

    Graphviz terminates an edge on the geometric outline of a node. After conversion
    to integer terminal cells that point may land either on the box border or on the
    adjacent cell. The renderer draws boxes after relationships, so a marker on the
    border would disappear. Normalizing only along the first and last segment keeps
    the route orthogonal while making both cardinality markers visible.
    """
    start, after_start = points[0], points[1]
    if after_start[0] > start[0]:
        start_marker = (
            source.right,
            _clamp(start[1], source.y, source.bottom - 1),
        )
        start_bridge = (start_marker[0], start[1])
    elif after_start[0] < start[0]:
        start_marker = (
            source.x - 1,
            _clamp(start[1], source.y, source.bottom - 1),
        )
        start_bridge = (start_marker[0], start[1])
    elif after_start[1] > start[1]:
        start_marker = (
            _clamp(start[0], source.x, source.right - 1),
            source.bottom,
        )
        start_bridge = (start[0], start_marker[1])
    else:
        start_marker = (
            _clamp(start[0], source.x, source.right - 1),
            source.y - 1,
        )
        start_bridge = (start[0], start_marker[1])

    before_end, end = points[-2], points[-1]
    if end[0] > before_end[0]:
        end_marker = (
            target.x - 1,
            _clamp(end[1], target.y, target.bottom - 1),
        )
        end_bridge = (end_marker[0], end[1])
    elif end[0] < before_end[0]:
        end_marker = (
            target.right,
            _clamp(end[1], target.y, target.bottom - 1),
        )
        end_bridge = (end_marker[0], end[1])
    elif end[1] > before_end[1]:
        end_marker = (
            _clamp(end[0], target.x, target.right - 1),
            target.y - 1,
        )
        end_bridge = (end[0], end_marker[1])
    else:
        end_marker = (
            _clamp(end[0], target.x, target.right - 1),
            target.bottom,
        )
        end_bridge = (end[0], end_marker[1])

    adjusted = [start_marker, start_bridge, *points[1:-1], end_bridge, end_marker]
    return _simplify_orthogonal(adjusted)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def route(source: Rect, target: Rect) -> list[Point]:
    """Fallback Manhattan route used if Graphviz cannot route an edge."""
    if source.bottom <= target.y:
        start = (source.center_x, source.bottom)
        end = (target.center_x, target.y - 1)
    elif target.bottom <= source.y:
        start = (source.center_x, source.y - 1)
        end = (target.center_x, target.bottom)
    elif source.right <= target.x:
        start = (source.right, source.center_y)
        end = (target.x - 1, target.center_y)
    elif target.right <= source.x:
        start = (source.x - 1, source.center_y)
        end = (target.right, target.center_y)
    else:
        start = (source.center_x, source.center_y)
        end = (target.center_x, target.center_y)
    return _bend(start, end)


def _bend(start: Point, end: Point) -> list[Point]:
    (sx, sy), (ex, ey) = start, end
    if sx == ex or sy == ey:
        return [start, end]
    mid_y = sy + (ey - sy) // 2
    return [start, (sx, mid_y), (ex, mid_y), end]
