from __future__ import annotations

from gimme_the_diagram.render.geometry import Rect
from gimme_the_diagram.render.routing import route


def test_straight_vertical_route_when_boxes_share_center_x() -> None:
    source = Rect(0, 0, 10, 5)
    target = Rect(0, 10, 10, 5)
    path = route(source, target)
    assert len(path) == 2
    (x1, y1), (x2, y2) = path
    assert x1 == x2 == source.center_x
    assert y1 == source.bottom
    assert y2 == target.y - 1


def test_bent_route_when_boxes_are_offset_horizontally() -> None:
    source = Rect(0, 0, 10, 5)
    target = Rect(20, 10, 10, 5)
    path = route(source, target)
    assert len(path) == 4
    # every consecutive pair must be axis-aligned (pure horizontal or vertical)
    for (x1, y1), (x2, y2) in zip(path, path[1:], strict=False):
        assert x1 == x2 or y1 == y2


def test_route_stays_left_to_right_when_boxes_are_side_by_side() -> None:
    source = Rect(0, 0, 10, 5)
    target = Rect(20, 0, 10, 5)
    path = route(source, target)
    (x1, y1), (x2, y2) = path
    assert x1 == source.right
    assert x2 == target.x - 1
    assert y1 == y2 == source.center_y
