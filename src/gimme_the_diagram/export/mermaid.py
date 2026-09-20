from __future__ import annotations

from gimme_the_diagram.schema.model import Column, RelationshipKind, Schema

_CARDINALITY = {
    RelationshipKind.ONE_TO_ONE: "||--||",
    RelationshipKind.ONE_TO_MANY: "||--o{",
    RelationshipKind.MANY_TO_MANY: "}o--o{",
}


def _identifier(name: str) -> str:
    return name.replace(" ", "_")


def _column_line(column: Column) -> str:
    type_token = _identifier(column.data_type) or "unknown"
    markers = []
    if column.is_primary_key:
        markers.append("PK")
    if column.is_foreign_key:
        markers.append("FK")
    line = f"        {type_token} {column.name}"
    if markers:
        line += " " + " ".join(markers)
    return line


def to_mermaid(schema: Schema, visible_tables: set[str] | None = None) -> str:
    """Render a Schema as a Mermaid `erDiagram` block.

    If `visible_tables` is given, only those tables (and relationships between them)
    are included; otherwise every table in the schema is rendered.
    """
    tables = [
        t for t in schema.tables if visible_tables is None or t.name in visible_tables
    ]
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
        lines.append(f"    {_identifier(table.name)} {{")
        lines.extend(_column_line(column) for column in table.columns)
        lines.append("    }")

    return "\n".join(lines) + "\n"
