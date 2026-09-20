from __future__ import annotations

from gimme_the_diagram.render.geometry import Point, Rect


def route(source: Rect, target: Rect) -> list[Point]:
    """Compute an orthogonal (Manhattan) polyline connecting two boxes' facing edges.

    The path only ever travels through the gap between the two boxes, never through
    box interiors, so it never needs to know about any other box on the canvas.
    """
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
