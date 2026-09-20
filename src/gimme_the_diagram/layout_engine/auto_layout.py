from __future__ import annotations

from collections import defaultdict, deque

from gimme_the_diagram.schema.model import Schema, Table

HORIZONTAL_GAP = 4
VERTICAL_GAP = 3


def estimate_box_size(table: Table) -> tuple[int, int]:
    """Rough (width, height) in character cells for a fully-detailed table box.

    Mirrors render.grid's box content format ("PK "/"FK "/"  " marker + "name: TYPE")
    closely enough that auto-placed boxes don't overlap once actually rendered.
    """
    lines = [table.name, *(f"   {c.name}: {c.data_type}" for c in table.columns)]
    content_width = max(len(line) for line in lines)
    width = content_width + 4
    height = len(table.columns) + 4
    return width, height


def _compute_layers(schema: Schema) -> dict[str, int]:
    """Longest-path layering over the FK graph (parent -> child), cycle-safe."""
    names = [t.name for t in schema.tables]
    children: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = dict.fromkeys(names, 0)

    for rel in schema.relationships:
        if rel.left_table == rel.right_table:
            continue
        if rel.left_table not in indegree or rel.right_table not in indegree:
            continue
        children[rel.left_table].append(rel.right_table)
        indegree[rel.right_table] += 1

    layer: dict[str, int] = dict.fromkeys(names, 0)
    remaining_indegree = dict(indegree)
    queue: deque[str] = deque(n for n in names if indegree[n] == 0)
    visited = set(queue)

    while queue:
        node = queue.popleft()
        for child in children[node]:
            layer[child] = max(layer[child], layer[node] + 1)
            remaining_indegree[child] -= 1
            if remaining_indegree[child] == 0 and child not in visited:
                visited.add(child)
                queue.append(child)

    return layer


def compute_auto_layout(schema: Schema) -> dict[str, tuple[int, int]]:
    """Compute an initial (x, y) top-left position per table, laid out in layers."""
    layers = _compute_layers(schema)
    by_layer: dict[int, list[str]] = defaultdict(list)
    for name, level in layers.items():
        by_layer[level].append(name)
    for names in by_layer.values():
        names.sort()

    positions: dict[str, tuple[int, int]] = {}
    y = 1
    for level in sorted(by_layer):
        x = 1
        row_height = 0
        for name in by_layer[level]:
            table = schema.get_table(name)
            width, height = estimate_box_size(table) if table else (20, 5)
            positions[name] = (x, y)
            x += width + HORIZONTAL_GAP
            row_height = max(row_height, height)
        y += row_height + VERTICAL_GAP

    return positions
