from __future__ import annotations

from gimme_the_diagram.export.mermaid import to_mermaid
from gimme_the_diagram.parsing.ddl_parser import parse_ddl

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


def test_starts_with_er_diagram_header() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    output = to_mermaid(schema)
    assert output.startswith("erDiagram\n")


def test_includes_every_table_by_default() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    output = to_mermaid(schema)
    assert "authors {" in output
    assert "books {" in output
    assert "id PK" in output
    assert "author_id FK" in output


def test_includes_relationship_line() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    output = to_mermaid(schema)
    assert "authors ||--o{ books" in output


def test_visible_tables_filter_excludes_hidden_table_and_its_relationship() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    output = to_mermaid(schema, visible_tables={"authors"})
    assert "authors {" in output
    assert "books {" not in output
    assert "||--o{" not in output
