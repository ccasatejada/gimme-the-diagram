from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from gimme_the_diagram.schema.model import Schema, Table

HORIZONTAL_GAP = 4
VERTICAL_GAP = 3
COMPONENT_GAP = 8
# Without a wrap width, a layer with many tables (e.g. every table with no incoming FK)
# is laid out as one indefinitely wide row. Besides being unusable to browse, relationship
# lines between distant tables then span thousands of columns, which is very expensive to
# render (see render.grid) - so layers wrap into multiple sub-rows past this width.
MAX_ROW_WIDTH = 200
# Sugiyama-style barycenter sweeps: alternating top-down/bottom-up passes that reorder
# each layer by the average position of its neighbors in the layer just visited, so
# related tables drift towards each other instead of sitting in whatever order they
# were first seen in. A handful of passes is enough for this to converge in practice.
BARYCENTER_PASSES = 4

FKEdge = tuple[str, str]  # (table holding the FK column, table it references)


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


def _fk_edges(schema: Schema) -> list[FKEdge]:
    """Every (table, referenced_table) pair straight from column-level FK metadata.

    Deliberately *not* derived from schema.relationships: a many-to-many junction
    table's two foreign keys are collapsed there into a single direct relationship
    between the two tables it connects (for rendering one clean line instead of
    routing through the junction table), which would make the junction table itself
    look unrelated to anything for layout purposes even though it clearly isn't.
    """
    table_names = {t.name for t in schema.tables}
    edges: list[FKEdge] = []
    for table in schema.tables:
        for column in table.columns:
            if not column.is_foreign_key or column.fk_target is None:
                continue
            ref_table = column.fk_target[0]
            if ref_table == table.name or ref_table not in table_names:
                continue
            edges.append((table.name, ref_table))
    return edges


def _build_neighbors(
    table_names: Iterable[str], fk_edges: Iterable[FKEdge]
) -> dict[str, set[str]]:
    """Undirected adjacency: which tables are directly related to which - used for
    clustering and proximity, not layering (see _compute_layers for the direction)."""
    neighbors: dict[str, set[str]] = {name: set() for name in table_names}
    for table, ref_table in fk_edges:
        if table not in neighbors or ref_table not in neighbors:
            continue
        neighbors[table].add(ref_table)
        neighbors[ref_table].add(table)
    return neighbors


def _connected_components(
    schema: Schema, neighbors: dict[str, set[str]]
) -> list[list[str]]:
    """Group tables into clusters connected (directly or transitively) by a
    relationship, so unrelated tables aren't laid out side by side as if they were."""
    visited: set[str] = set()
    components: list[list[str]] = []
    for table in schema.tables:
        if table.name in visited:
            continue
        component: list[str] = []
        queue: deque[str] = deque([table.name])
        visited.add(table.name)
        while queue:
            name = queue.popleft()
            component.append(name)
            for neighbor in neighbors[name]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    # Largest cluster first (the "core" of the schema), smaller/unrelated ones after.
    components.sort(key=lambda component: (-len(component), min(component)))
    return components


def _compute_layers(
    table_names: set[str], fk_edges: Iterable[FKEdge]
) -> dict[str, int]:
    """Longest-path layering over the FK graph (referenced table -> table with the FK
    column), cycle-safe. A table with two FKs (e.g. a many-to-many junction table)
    naturally lands one layer below the deeper of the two tables it references."""
    children: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = dict.fromkeys(table_names, 0)

    for table, ref_table in fk_edges:
        if table == ref_table:
            continue
        if table not in indegree or ref_table not in indegree:
            continue
        children[ref_table].append(table)
        indegree[table] += 1

    layer: dict[str, int] = dict.fromkeys(table_names, 0)
    remaining_indegree = dict(indegree)
    queue: deque[str] = deque(n for n in table_names if indegree[n] == 0)
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


def _barycenter_reorder(
    by_layer: dict[int, list[str]], neighbors: dict[str, set[str]]
) -> dict[int, list[str]]:
    """Reorder each layer so tables end up horizontally close to the (already placed)
    related tables in the layer above/below them, instead of e.g. alphabetically."""
    order = {level: list(names) for level, names in by_layer.items()}
    levels = sorted(order)
    if len(levels) < 2:
        return order

    for pass_index in range(BARYCENTER_PASSES):
        sweep = levels if pass_index % 2 == 0 else list(reversed(levels))
        for index in range(1, len(sweep)):
            level = sweep[index]
            reference_level = sweep[index - 1]
            reference_position = {
                name: position for position, name in enumerate(order[reference_level])
            }
            current_position = {
                name: position for position, name in enumerate(order[level])
            }

            def barycenter(
                name: str,
                _reference: dict[str, int] = reference_position,
                _current: dict[str, int] = current_position,
            ) -> float:
                anchors = [_reference[n] for n in neighbors[name] if n in _reference]
                if not anchors:
                    return float(_current[name])
                return sum(anchors) / len(anchors)

            order[level].sort(key=barycenter)

    return order


def _place_component(
    schema: Schema,
    ordered_by_layer: dict[int, list[str]],
    positions: dict[str, tuple[int, int]],
    x_origin: int,
    y_origin: int,
) -> tuple[int, int]:
    """Place one connected component's already-ordered layers, starting at
    (x_origin, y_origin). Returns the component's (width, height) footprint, so the
    next one can be placed after it."""
    y = y_origin
    width_used = 0
    for level in sorted(ordered_by_layer):
        x = x_origin
        row_height = 0
        for name in ordered_by_layer[level]:
            table = schema.get_table(name)
            box_width, box_height = estimate_box_size(table) if table else (20, 5)
            if x > x_origin and x + box_width > x_origin + MAX_ROW_WIDTH:
                x = x_origin
                y += row_height + VERTICAL_GAP
                row_height = 0
            positions[name] = (x, y)
            x += box_width + HORIZONTAL_GAP
            width_used = max(width_used, x - x_origin - HORIZONTAL_GAP)
            row_height = max(row_height, box_height)
        y += row_height + VERTICAL_GAP

    return width_used, y - y_origin


def compute_auto_layout(schema: Schema) -> dict[str, tuple[int, int]]:
    """Compute an initial (x, y) top-left position per table.

    Tables are grouped into clusters of mutually related tables (so unrelated tables
    don't end up side by side), each cluster is layered top-to-bottom by FK direction,
    and within each layer, tables are ordered to sit close to the related tables in
    the layer above/below them (a barycenter sweep) rather than e.g. alphabetically.
    """
    table_names = {t.name for t in schema.tables}
    fk_edges = _fk_edges(schema)
    neighbors = _build_neighbors(table_names, fk_edges)
    components = _connected_components(schema, neighbors)

    positions: dict[str, tuple[int, int]] = {}
    x_origin = 1
    y_origin = 1
    component_row_height = 0
    for component in components:
        component_names = set(component)
        component_edges = [
            (table, ref_table)
            for table, ref_table in fk_edges
            if table in component_names and ref_table in component_names
        ]
        layers = _compute_layers(component_names, component_edges)

        by_layer: dict[int, list[str]] = defaultdict(list)
        for name, level in layers.items():
            by_layer[level].append(name)
        for names in by_layer.values():
            names.sort()  # deterministic starting order for the barycenter sweep

        ordered = _barycenter_reorder(by_layer, neighbors)

        # Many small/unrelated clusters (e.g. lookup tables with no FK at all) would
        # otherwise be placed side by side indefinitely, recreating the same unbounded
        # width that MAX_ROW_WIDTH prevents within a single layer - so component "rows"
        # wrap the same way.
        if x_origin > 1 and x_origin > MAX_ROW_WIDTH:
            x_origin = 1
            y_origin += component_row_height + COMPONENT_GAP
            component_row_height = 0

        component_width, component_height = _place_component(
            schema, ordered, positions, x_origin, y_origin
        )
        x_origin += component_width + COMPONENT_GAP
        component_row_height = max(component_row_height, component_height)

    return positions
