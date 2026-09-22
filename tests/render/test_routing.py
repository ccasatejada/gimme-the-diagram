from __future__ import annotations

from gimme_the_diagram.render.geometry import Rect
from gimme_the_diagram.render.routing import route, route_relationships
from gimme_the_diagram.schema.model import Relationship, RelationshipKind


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


def test_graphviz_route_avoids_an_unrelated_table() -> None:
    boxes = {
        "source": Rect(0, 10, 10, 5),
        "obstacle": Rect(20, 8, 12, 9),
        "target": Rect(42, 10, 10, 5),
    }
    relationship = Relationship("source", "target", RelationshipKind.ONE_TO_MANY)

    path = route_relationships(boxes, [relationship])[0]

    assert path[0][1] == boxes["source"].bottom
    assert path[-1][1] == boxes["target"].bottom

    for (x1, y1), (x2, y2) in zip(path, path[1:], strict=False):
        assert x1 == x2 or y1 == y2
        if x1 == x2:
            assert not (
                boxes["obstacle"].x < x1 < boxes["obstacle"].right
                and max(min(y1, y2), boxes["obstacle"].y)
                < min(max(y1, y2), boxes["obstacle"].bottom)
            )
        else:
            assert not (
                boxes["obstacle"].y < y1 < boxes["obstacle"].bottom
                and max(min(x1, x2), boxes["obstacle"].x)
                < min(max(x1, x2), boxes["obstacle"].right)
            )


def test_graphviz_keeps_parallel_relationships_distinct() -> None:
    boxes = {"source": Rect(0, 0, 10, 8), "target": Rect(30, 0, 10, 8)}
    relationships = [
        Relationship("source", "target", RelationshipKind.ONE_TO_MANY),
        Relationship("source", "target", RelationshipKind.ONE_TO_MANY),
    ]

    routes = route_relationships(boxes, relationships)

    assert set(routes) == {0, 1}
    assert routes[0] != routes[1]


def test_graphviz_route_endpoints_are_outside_box_borders() -> None:
    boxes = {"source": Rect(0, 0, 10, 8), "target": Rect(30, 0, 10, 8)}
    relationship = Relationship("source", "target", RelationshipKind.ONE_TO_MANY)

    path = route_relationships(boxes, [relationship])[0]

    assert path[0] == (boxes["source"].right, boxes["source"].center_y)
    assert path[-1] == (boxes["target"].x - 1, boxes["target"].center_y)
