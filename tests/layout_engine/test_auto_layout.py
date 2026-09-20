from __future__ import annotations

from gimme_the_diagram.layout_engine.auto_layout import compute_auto_layout
from gimme_the_diagram.parsing.ddl_parser import parse_ddl

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


def test_every_table_gets_a_position() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    positions = compute_auto_layout(schema)
    assert set(positions) == {"authors", "books"}


def test_parent_table_is_above_child_table() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    positions = compute_auto_layout(schema)
    _, authors_y = positions["authors"]
    _, books_y = positions["books"]
    assert authors_y < books_y


def test_self_referential_fk_does_not_crash() -> None:
    sql = """
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        manager_id INTEGER REFERENCES employees(id)
    );
    """
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)
    assert "employees" in positions


def test_cyclic_fk_graph_does_not_crash() -> None:
    sql = """
    CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER);
    CREATE TABLE b (id INTEGER PRIMARY KEY, a_id INTEGER);
    ALTER TABLE a ADD CONSTRAINT fk_a FOREIGN KEY (b_id) REFERENCES b(id);
    ALTER TABLE b ADD CONSTRAINT fk_b FOREIGN KEY (a_id) REFERENCES a(id);
    """
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)
    assert set(positions) == {"a", "b"}
