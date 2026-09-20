from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from gimme_the_diagram.parsing.introspector import build_sqlite_url, introspect_schema
from gimme_the_diagram.schema.model import RelationshipKind


@pytest.fixture
def engine() -> Iterator[Engine]:
    sample_engine = create_engine(build_sqlite_url(":memory:"))
    with sample_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT)")
        )
        connection.execute(
            text(
                "CREATE TABLE books ("
                "id INTEGER PRIMARY KEY, "
                "author_id INTEGER NOT NULL REFERENCES authors(id))"
            )
        )
    try:
        yield sample_engine
    finally:
        sample_engine.dispose()


def test_introspects_tables_and_columns(engine: Engine) -> None:
    schema = introspect_schema(engine)
    assert {t.name for t in schema.tables} == {"authors", "books"}
    authors = schema.get_table("authors")
    assert authors is not None
    assert authors.primary_key == ("id",)


def test_introspects_foreign_key_relationship(engine: Engine) -> None:
    schema = introspect_schema(engine)
    assert len(schema.relationships) == 1
    relationship = schema.relationships[0]
    assert relationship.left_table == "authors"
    assert relationship.right_table == "books"
    assert relationship.kind == RelationshipKind.ONE_TO_MANY
