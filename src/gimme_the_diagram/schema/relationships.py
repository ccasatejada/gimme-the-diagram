from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from gimme_the_diagram.schema.model import Relationship, RelationshipKind, Table


@dataclass(frozen=True)
class FKEdge:
    """A raw foreign-key constraint, before it has been turned into a Relationship."""

    table: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


def apply_foreign_keys(tables: dict[str, Table], fk_edges: list[FKEdge]) -> None:
    """Mark `is_foreign_key`/`fk_target` on the relevant columns, in place."""
    for edge in fk_edges:
        table = tables.get(edge.table)
        if table is None or not edge.ref_table:
            continue
        for index, column_name in enumerate(edge.columns):
            column = table.get_column(column_name)
            if column is None:
                continue
            column.is_foreign_key = True
            ref_column = (
                edge.ref_columns[index] if index < len(edge.ref_columns) else None
            )
            column.fk_target = (edge.ref_table, ref_column)


def _is_unique(table: Table, columns: tuple[str, ...]) -> bool:
    column_set = frozenset(columns)
    if column_set == frozenset(table.primary_key):
        return True
    return column_set in table.unique_constraints


def detect_relationships(
    tables: dict[str, Table], fk_edges: list[FKEdge]
) -> list[Relationship]:
    """Turn FK edges into one_to_one / one_to_many / many_to_many relationships.

    A table whose primary key is made up of exactly two FK columns is treated as a
    many-to-many junction table between the two tables it references.
    """
    fk_by_table: dict[str, list[FKEdge]] = defaultdict(list)
    for edge in fk_edges:
        if edge.ref_table:
            fk_by_table[edge.table].append(edge)

    relationships: list[Relationship] = []
    junction_tables: set[str] = set()

    _identify_cardinalities(fk_by_table, junction_tables, relationships, tables)

    for table_name, edges in fk_by_table.items():
        if table_name in junction_tables:
            continue
        table = tables.get(table_name)
        for edge in edges:
            is_unique = _is_unique(table, edge.columns) if table is not None else False
            kind = (
                RelationshipKind.ONE_TO_ONE
                if is_unique
                else RelationshipKind.ONE_TO_MANY
            )
            relationships.append(
                Relationship(
                    left_table=edge.ref_table, right_table=table_name, kind=kind
                )
            )

    return relationships


def _identify_cardinalities(
    fk_by_table: dict[str, list[FKEdge]],
    junction_tables: set[str],
    relationships: list[Relationship],
    tables: dict[str, Table],
) -> None:
    for table_name, edges in fk_by_table.items():
        table = tables.get(table_name)
        if table is None or len(edges) != 2 or not table.primary_key:
            continue
        fk_columns: set[str] = set()
        for edge in edges:
            fk_columns.update(edge.columns)
        if fk_columns == set(table.primary_key):
            left, right = edges
            relationships.append(
                Relationship(
                    left_table=left.ref_table,
                    right_table=right.ref_table,
                    kind=RelationshipKind.MANY_TO_MANY,
                    via_table=table_name,
                )
            )
            junction_tables.add(table_name)
