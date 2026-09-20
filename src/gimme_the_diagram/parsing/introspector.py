from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from gimme_the_diagram.schema.model import Column, Schema, Table
from gimme_the_diagram.schema.relationships import (
    FKEdge,
    apply_foreign_keys,
    detect_relationships,
)


class IntrospectionError(RuntimeError):
    pass


def build_postgres_url(
    host: str, port: int, user: str, password: str, database: str
) -> str:
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def build_sqlite_url(path: str) -> str:
    return f"sqlite:///{path}"


def create_engine_for_url(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def introspect_schema(engine: Engine) -> Schema:
    """Reflect every table of a live database (Postgres/SQLite) into a Schema."""
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        tables: dict[str, Table] = {}
        for name in table_names:
            pk_constraint = inspector.get_pk_constraint(name)
            primary_key = tuple(pk_constraint.get("constrained_columns") or ())
            unique_constraints = tuple(
                frozenset(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(name)
                if constraint.get("column_names")
            )

            columns = [
                Column(
                    name=column["name"],
                    data_type=str(column["type"]),
                    nullable=column.get("nullable", True),
                    is_primary_key=column["name"] in primary_key,
                )
                for column in inspector.get_columns(name)
            ]
            tables[name] = Table(
                name=name,
                columns=columns,
                primary_key=primary_key,
                unique_constraints=unique_constraints,
            )

        fk_edges: list[FKEdge] = []
        for name in table_names:
            for fk in inspector.get_foreign_keys(name):
                ref_table = fk.get("referred_table")
                constrained_columns = tuple(fk.get("constrained_columns") or ())
                referred_columns = tuple(fk.get("referred_columns") or ())
                if not ref_table or not constrained_columns:
                    continue
                fk_edges.append(
                    FKEdge(name, constrained_columns, ref_table, referred_columns)
                )
    except SQLAlchemyError as exc:
        raise IntrospectionError(str(exc)) from exc

    apply_foreign_keys(tables, fk_edges)
    relationships = detect_relationships(tables, fk_edges)
    return Schema(tables=list(tables.values()), relationships=relationships)
