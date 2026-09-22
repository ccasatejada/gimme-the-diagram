from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from gimme_the_diagram.schema.model import Column, RelationshipKind, Schema

_CARDINALITY = {
    RelationshipKind.ONE_TO_ONE: "||--||",
    RelationshipKind.ONE_TO_MANY: "||--o{",
    RelationshipKind.MANY_TO_MANY: "}o--o{",
}

# Mermaid's erDiagram grammar only accepts plain "word" tokens (no spaces, commas or
# parens) for entity names, attribute types and attribute names - e.g. a column typed
# "NUMERIC(9, 2)" must become "NUMERIC_9_2", not be passed through as-is.
# re.ASCII keeps \W equivalent to the previous [^A-Za-z0-9_] (i.e. accented/Unicode
# letters are still folded to "_" rather than kept, since Mermaid identifiers should
# stay plain ASCII regardless of what Python's default Unicode-aware \w would accept).
_NON_WORD_RUN = re.compile(r"\W+", re.ASCII)


def _identifier(name: str) -> str:
    sanitized = _NON_WORD_RUN.sub("_", name).strip("_")
    return sanitized or "unknown"


def _column_line(column: Column) -> str:
    type_token = _identifier(column.data_type)
    markers = []
    if column.is_primary_key:
        markers.append("PK")
    if column.is_foreign_key:
        markers.append("FK")
    line = f"        {type_token} {_identifier(column.name)}"
    if markers:
        line += " " + ", ".join(markers)
    return line


def to_mermaid(
    schema: Schema,
    visible_tables: set[str] | None = None,
    order: list[str] | None = None,
    *,
    include_columns: bool = True,
) -> str:
    """Render a Schema as a Mermaid `erDiagram` block.

    If `visible_tables` is given, only those tables (and relationships between them)
    are included; otherwise every table in the schema is rendered.

    Mermaid's erDiagram format has no notion of manual entity positioning - it always
    lays the diagram out itself. `order` (typically tables sorted by their on-canvas
    position) only controls the order entities are *declared* in the output, which is
    the closest available hint towards the user's own arrangement.
    """
    tables = [
        t for t in schema.tables if visible_tables is None or t.name in visible_tables
    ]
    if order is not None:
        rank = {name: index for index, name in enumerate(order)}
        tables.sort(key=lambda t: rank.get(t.name, len(rank)))
    table_names = {t.name for t in tables}

    lines = ["erDiagram"]
    for relationship in schema.relationships:
        if (
            relationship.left_table not in table_names
            or relationship.right_table not in table_names
        ):
            continue
        cardinality = _CARDINALITY[relationship.kind]
        label = relationship.via_table or "has"
        lines.append(
            f"    {_identifier(relationship.left_table)} {cardinality} "
            f'{_identifier(relationship.right_table)} : "{label}"'
        )

    for table in tables:
        if include_columns:
            lines.append(f"    {_identifier(table.name)} {{")
            lines.extend(_column_line(column) for column in table.columns)
            lines.append("    }")
        else:
            # Declaring an empty entity keeps isolated tables in compact exports.
            lines.append(f"    {_identifier(table.name)} {{}}")

    return "\n".join(lines) + "\n"


def export_mermaid_bundle(
    schema: Schema,
    path: Path,
    visible_tables: set[str] | None = None,
    order: list[str] | None = None,
    *,
    tables_per_part: int = 40,
) -> None:
    """Write a ZIP containing a compact overview and bounded detailed Mermaid parts."""
    selected = [
        table.name
        for table in schema.tables
        if visible_tables is None or table.name in visible_tables
    ]
    if order is not None:
        rank = {name: index for index, name in enumerate(order)}
        selected.sort(key=lambda name: rank.get(name, len(rank)))
    else:
        selected.sort()

    overview = to_mermaid(schema, set(selected), order, include_columns=False)
    chunks = [
        selected[index : index + tables_per_part]
        for index in range(0, len(selected), tables_per_part)
    ]
    index_lines = ["# Mermaid schema export", "", "- [Overview](overview.mmd)"]
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("overview.mmd", overview)
        for number, names in enumerate(chunks, start=1):
            filename = f"parts/diagram-{number:03d}.mmd"
            archive.writestr(
                filename,
                to_mermaid(schema, set(names), names, include_columns=True),
            )
            index_lines.append(
                f"- [Part {number:03d} ({len(names)} tables)]({filename})"
            )
        archive.writestr("README.md", "\n".join(index_lines) + "\n")
