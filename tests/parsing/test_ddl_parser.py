from __future__ import annotations

import pytest

from gimme_the_diagram.parsing.ddl_parser import (
    DDLParseError,
    parse_ddl,
    parse_ddl_auto,
)
from gimme_the_diagram.schema.model import RelationshipKind

SAMPLE_DDL = """
CREATE TABLE authors (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    bio TEXT
);

CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    profile_id INTEGER UNIQUE,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    label VARCHAR(50)
);

CREATE TABLE book_tags (
    book_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (book_id, tag_id),
    FOREIGN KEY (book_id) REFERENCES books(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
"""


def test_parses_all_tables() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    assert {t.name for t in schema.tables} == {
        "authors",
        "profiles",
        "books",
        "tags",
        "book_tags",
    }


def test_columns_and_primary_keys() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    authors = schema.get_table("authors")
    assert authors is not None
    assert authors.primary_key == ("id",)
    id_column = authors.get_column("id")
    assert id_column is not None
    assert id_column.is_primary_key
    assert not id_column.nullable

    book_tags = schema.get_table("book_tags")
    assert book_tags is not None
    assert book_tags.primary_key == ("book_id", "tag_id")


def test_one_to_many_relationship_detected() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    one_to_many = [
        r for r in schema.relationships if r.kind == RelationshipKind.ONE_TO_MANY
    ]
    assert len(one_to_many) == 1
    rel = one_to_many[0]
    assert rel.left_table == "authors"
    assert rel.right_table == "books"

    books = schema.get_table("books")
    assert books is not None
    author_id = books.get_column("author_id")
    assert author_id is not None
    assert author_id.is_foreign_key
    assert author_id.fk_target == ("authors", "id")


def test_one_to_one_relationship_from_unique_fk() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    one_to_one = [
        r for r in schema.relationships if r.kind == RelationshipKind.ONE_TO_ONE
    ]
    assert len(one_to_one) == 1
    rel = one_to_one[0]
    assert rel.left_table == "profiles"
    assert rel.right_table == "books"


def test_many_to_many_relationship_via_junction_table() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    many_to_many = [
        r for r in schema.relationships if r.kind == RelationshipKind.MANY_TO_MANY
    ]
    assert len(many_to_many) == 1
    rel = many_to_many[0]
    assert {rel.left_table, rel.right_table} == {"books", "tags"}
    assert rel.via_table == "book_tags"


def test_alter_table_add_foreign_key() -> None:
    sql = """
    CREATE TABLE authors (id INTEGER PRIMARY KEY);
    CREATE TABLE books (id INTEGER PRIMARY KEY, author_id INTEGER);
    ALTER TABLE books ADD CONSTRAINT fk_author FOREIGN KEY (author_id) REFERENCES authors(id);
    """
    schema = parse_ddl(sql)
    rel = schema.relationships[0]
    assert rel.left_table == "authors"
    assert rel.right_table == "books"
    assert rel.kind == RelationshipKind.ONE_TO_MANY


def test_invalid_sql_raises_ddl_parse_error() -> None:
    with pytest.raises(DDLParseError):
        parse_ddl("CREATE TABLE (((( invalid")


def test_empty_sql_raises_ddl_parse_error() -> None:
    with pytest.raises(DDLParseError):
        parse_ddl("-- just a comment, no tables")


def test_parse_ddl_auto_does_not_require_a_dialect_choice() -> None:
    sql = "CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));"
    schema = parse_ddl_auto(sql)
    assert {t.name for t in schema.tables} == {"authors"}


def test_parse_ddl_auto_raises_when_no_dialect_can_parse_it() -> None:
    with pytest.raises(DDLParseError):
        parse_ddl_auto("this is not sql at all !!!")


def test_parse_ddl_recovers_tables_from_a_realistic_pg_dump() -> None:
    """`pg_dump` output routinely mixes real DDL with statements this parser doesn't
    need (psql meta-commands, PL/pgSQL function bodies, SET/COMMENT statements, ...).
    A single unparseable line must not prevent every other table from loading."""
    sql = """
    \\restrict abc123
    SET statement_timeout = 0;
    SELECT pg_catalog.set_config('search_path', '', false);

    CREATE TYPE public.stock_format AS ENUM ('swift', 's3');

    CREATE FUNCTION public.touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$;

    CREATE TABLE public.authors (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL
    );

    CREATE TABLE public.books (
        id INTEGER PRIMARY KEY,
        author_id INTEGER NOT NULL REFERENCES public.authors(id),
        price NUMERIC(9, 2)
    );

    COMMENT ON TABLE public.books IS 'catalog of books';
    \\unrestrict abc123
    """
    schema = parse_ddl_auto(sql)
    assert {t.name for t in schema.tables} == {"authors", "books"}
    assert len(schema.relationships) == 1
