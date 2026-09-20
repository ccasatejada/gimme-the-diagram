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


def test_column_type_with_commas_and_spaces_is_sanitized() -> None:
    sql = "CREATE TABLE invoices (id INTEGER PRIMARY KEY, montant NUMERIC(9, 2));"
    schema = parse_ddl(sql)
    output = to_mermaid(schema)
    # no raw comma/space/parens must leak into an attribute line - that breaks mermaid's parser
    for line in output.splitlines():
        stripped = line.strip()
        if (
            stripped
            and stripped not in ("erDiagram", "}")
            and not stripped.endswith("{")
        ):
            tokens = stripped.split()
            assert "," not in tokens[0] and "(" not in tokens[0]
    assert "montant" in output


def test_junction_table_column_gets_comma_separated_pk_fk_markers() -> None:
    sql = """
    CREATE TABLE books (id INTEGER PRIMARY KEY);
    CREATE TABLE tags (id INTEGER PRIMARY KEY);
    CREATE TABLE book_tags (
        book_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (book_id, tag_id),
        FOREIGN KEY (book_id) REFERENCES books(id),
        FOREIGN KEY (tag_id) REFERENCES tags(id)
    );
    """
    schema = parse_ddl(sql)
    output = to_mermaid(schema)
    assert "book_id PK, FK" in output


def test_order_controls_entity_declaration_order() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    output = to_mermaid(schema, order=["books", "authors"])
    assert output.index("books {") < output.index("authors {")
