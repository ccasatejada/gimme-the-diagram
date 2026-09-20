from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.expressions import ColumnDef, Expression

from gimme_the_diagram.schema.model import Column, Schema, Table
from gimme_the_diagram.schema.relationships import (
    FKEdge,
    apply_foreign_keys,
    detect_relationships,
)

# With error_level=WARN, sqlglot logs every statement it can't parse via logger.error()
# (straight to stderr, through the logging "last resort" handler). That's expected/frequent
# with real pg_dump files (psql meta-commands, PL/pgSQL function bodies, etc.) and would
# otherwise corrupt the Textual full-screen display, so it's silenced here.
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)


class DDLParseError(ValueError):
    pass


@dataclass
class _TableBuilder:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    primary_key: set[str] = field(default_factory=set)
    unique_sets: list[frozenset[str]] = field(default_factory=list)


def parse_ddl(sql: str, dialect: str | None = "postgres") -> Schema:
    """Parse raw SQL DDL text (one or more CREATE/ALTER TABLE statements) into a Schema.

    Real-world dumps (e.g. `pg_dump` output) routinely contain statements this parser
    doesn't need to understand (`SET ...`, `COMMENT ON ...`, PL/pgSQL function bodies,
    psql-only meta-commands like `\\restrict`, ...). Rather than aborting on the first
    one it can't parse, individual unparseable statements are skipped (`ErrorLevel.WARN`)
    and only the CREATE/ALTER TABLE statements that *did* parse are used. Parsing only
    fails outright if no table could be recovered at all.
    """
    try:
        statements = sqlglot.parse(sql, dialect=dialect, error_level=ErrorLevel.WARN)
    except ParseError as exc:
        raise DDLParseError(str(exc)) from exc

    tables: dict[str, _TableBuilder] = {}
    fk_edges: list[FKEdge] = []

    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, exp.Create) and stmt.args.get("kind") == "TABLE":
            _consume_create_table(stmt, tables, fk_edges)
        elif isinstance(stmt, exp.Alter):
            _consume_alter_table(stmt, fk_edges)

    if not tables:
        raise DDLParseError("no CREATE TABLE statement could be parsed")

    return _build_schema(tables, fk_edges)


_AUTO_DETECT_DIALECTS = ("postgres", "sqlite")


def parse_ddl_auto(sql: str) -> Schema:
    """Parse DDL without asking the user for a dialect: try each supported dialect and
    keep whichever one recovers the most tables."""
    best: Schema | None = None
    last_error: DDLParseError | None = None
    for dialect in _AUTO_DETECT_DIALECTS:
        try:
            schema = parse_ddl(sql, dialect=dialect)
        except DDLParseError as exc:
            last_error = exc
            continue
        if best is None or len(schema.tables) > len(best.tables):
            best = schema
    if best is None:
        assert last_error is not None
        raise last_error
    return best


def _extract_ref(reference: exp.Reference | None) -> tuple[str, tuple[str, ...]]:
    if reference is None:
        return "", ()
    target = reference.this
    if isinstance(target, exp.Schema):
        ref_table = target.this.name
        ref_columns = tuple(c.name for c in target.expressions)
    else:
        ref_table = target.name
        ref_columns = ()
    return ref_table, ref_columns


def _build_column(item: exp.ColumnDef) -> Column:
    kind = item.args.get("kind")
    data_type = kind.sql() if kind is not None else ""
    nullable = True
    is_pk = False
    for constraint in item.constraints or []:
        constraint_kind = constraint.kind
        if isinstance(constraint_kind, exp.NotNullColumnConstraint):
            nullable = False
        elif isinstance(constraint_kind, exp.PrimaryKeyColumnConstraint):
            is_pk = True
            nullable = False
    return Column(
        name=item.name, data_type=data_type, nullable=nullable, is_primary_key=is_pk
    )


def _consume_create_table(
    stmt: exp.Create, tables: dict[str, _TableBuilder], fk_edges: list[FKEdge]
) -> None:
    schema_expr = stmt.this
    table_expr = (
        schema_expr.this if isinstance(schema_expr, exp.Schema) else schema_expr
    )
    table_name = table_expr.name
    builder = tables.setdefault(table_name, _TableBuilder(name=table_name))

    if not isinstance(schema_expr, exp.Schema):
        return

    for item in schema_expr.expressions:
        if isinstance(item, exp.ColumnDef):
            column = _build_column(item)
            builder.columns[column.name] = column
            _handle_constraints(builder, column, fk_edges, item, table_name)
        elif isinstance(item, exp.PrimaryKey):
            builder.primary_key.update(c.name for c in item.expressions)
        elif isinstance(item, exp.ForeignKey):
            columns = tuple(c.name for c in item.expressions)
            ref_table, ref_columns = _extract_ref(item.args.get("reference"))
            fk_edges.append(FKEdge(table_name, columns, ref_table, ref_columns))
        elif isinstance(item, exp.UniqueColumnConstraint) and item.this is not None:
            columns = tuple(c.name for c in item.this.expressions)
            if columns:
                builder.unique_sets.append(frozenset(columns))


def _handle_constraints(
    builder: _TableBuilder,
    column: Column,
    fk_edges: list[FKEdge],
    item: ColumnDef,
    table_name: str,
) -> None:
    for constraint in item.constraints or []:
        constraint_kind = constraint.kind
        if isinstance(constraint_kind, exp.PrimaryKeyColumnConstraint):
            builder.primary_key.add(column.name)
        elif isinstance(constraint_kind, exp.UniqueColumnConstraint):
            builder.unique_sets.append(frozenset({column.name}))
        elif isinstance(constraint_kind, exp.Reference):
            ref_table, ref_columns = _extract_ref(constraint_kind)
            fk_edges.append(FKEdge(table_name, (column.name,), ref_table, ref_columns))


def _consume_alter_table(stmt: exp.Alter, fk_edges: list[FKEdge]) -> None:
    table_name = stmt.this.name
    for action in stmt.args.get("actions") or []:
        constraints: list[exp.Expression] = []
        if isinstance(action, exp.AddConstraint):
            for entry in action.expressions:
                if isinstance(entry, exp.Constraint):
                    constraints.extend(entry.expressions)
                else:
                    constraints.append(entry)
        _append_foreign_keys(constraints, fk_edges, table_name)


def _append_foreign_keys(
    constraints: list[Expression], fk_edges: list[FKEdge], table_name: str
) -> None:
    for constraint in constraints:
        if isinstance(constraint, exp.ForeignKey):
            columns = tuple(c.name for c in constraint.expressions)
            ref_table, ref_columns = _extract_ref(constraint.args.get("reference"))
            fk_edges.append(FKEdge(table_name, columns, ref_table, ref_columns))


def _build_schema(tables: dict[str, _TableBuilder], fk_edges: list[FKEdge]) -> Schema:
    schema_tables: dict[str, Table] = {}
    for name, builder in tables.items():
        columns = []
        for column in builder.columns.values():
            if column.name in builder.primary_key:
                column.is_primary_key = True
                column.nullable = False
            columns.append(column)
        schema_tables[name] = Table(
            name=name,
            columns=columns,
            primary_key=tuple(sorted(builder.primary_key)),
            unique_constraints=tuple(builder.unique_sets),
        )

    valid_edges = [edge for edge in fk_edges if edge.ref_table]
    apply_foreign_keys(schema_tables, valid_edges)
    relationships = detect_relationships(schema_tables, valid_edges)

    return Schema(tables=list(schema_tables.values()), relationships=relationships)
