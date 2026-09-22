from __future__ import annotations

from gimme_the_diagram.layout_engine.auto_layout import (
    compute_auto_layout,
    estimate_box_size,
)
from gimme_the_diagram.layout_engine.graphviz_process import GraphvizProcessError
from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.render.geometry import Rect

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


def test_parent_table_is_left_of_child_table() -> None:
    schema = parse_ddl(SAMPLE_DDL)
    positions = compute_auto_layout(schema)
    authors_x, _ = positions["authors"]
    books_x, _ = positions["books"]
    assert authors_x < books_x


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


def test_many_unrelated_tables_wrap_into_multiple_component_rows() -> None:
    """Many tables with no relationship at all (e.g. lookup tables) are each their own
    single-table cluster; those clusters must still wrap into multiple rows instead of
    lining up as one indefinitely wide row - both for usability and because an
    unbounded width makes relationship-line rendering very expensive (see render.grid)."""
    sql = "\n".join(f"CREATE TABLE t{i} (id INTEGER PRIMARY KEY);" for i in range(30))
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)

    max_x = max(x for x, _ in positions.values())
    distinct_y = {y for _, y in positions.values()}

    assert max_x < 300
    assert len(distinct_y) > 1


def test_many_children_of_one_parent_wrap_within_their_shared_layer() -> None:
    """Many *related* tables (all children of the same parent) land in a single FK
    layer of a single cluster - that layer must also wrap instead of spanning an
    unbounded width."""
    statements = ["CREATE TABLE parent (id INTEGER PRIMARY KEY);"]
    statements += [
        f"CREATE TABLE child{i} ("
        f"id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));"
        for i in range(30)
    ]
    schema = parse_ddl("\n".join(statements))
    positions = compute_auto_layout(schema)

    child_positions = [positions[f"child{i}"] for i in range(30)]
    max_child_x = max(x for x, _ in child_positions)
    distinct_child_y = {y for _, y in child_positions}

    assert max_child_x < 300
    assert len(distinct_child_y) > 1


def test_each_parent_precedes_its_child_regardless_of_alphabetical_order() -> None:
    sql = """
    CREATE TABLE alpha (id INTEGER PRIMARY KEY);
    CREATE TABLE zulu (id INTEGER PRIMARY KEY);
    CREATE TABLE last_born (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES alpha(id));
    CREATE TABLE first_born (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES zulu(id));
    """
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)

    alpha_x, _ = positions["alpha"]
    last_born_x, _ = positions["last_born"]
    zulu_x, _ = positions["zulu"]
    first_born_x, _ = positions["first_born"]

    assert alpha_x < last_born_x
    assert zulu_x < first_born_x


def test_many_to_many_junction_table_is_grouped_with_the_tables_it_connects() -> None:
    """Regression test: a many-to-many junction table's two foreign keys get collapsed
    by schema.relationships into a single direct relationship between the two tables
    it connects (films <-> tags), so the junction table itself never appears as either
    side of a Relationship. Deriving proximity from that collapsed representation made
    every junction table look unrelated to anything and land far away, isolated - even
    though `\\d films_tags` in psql plainly shows two real foreign keys."""
    sql = """
    CREATE TABLE films (id_film INTEGER PRIMARY KEY);
    CREATE TABLE tags (id_tags INTEGER PRIMARY KEY);
    CREATE TABLE films_tags (
        id_film INTEGER NOT NULL REFERENCES films(id_film),
        id_tags INTEGER NOT NULL REFERENCES tags(id_tags),
        PRIMARY KEY (id_film, id_tags)
    );
    """
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)

    # With a left-to-right layout, both referenced tables precede the junction.
    assert positions["films_tags"][0] > positions["films"][0]
    assert positions["films_tags"][0] > positions["tags"][0]


def test_unrelated_tables_are_kept_apart_from_a_connected_cluster() -> None:
    """Tables with no relationship path to a connected cluster shouldn't be placed as
    if they belonged to it."""
    sql = """
    CREATE TABLE parent (id INTEGER PRIMARY KEY);
    CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
    CREATE TABLE loner_a (id INTEGER PRIMARY KEY);
    CREATE TABLE loner_b (id INTEGER PRIMARY KEY);
    """
    schema = parse_ddl(sql)
    positions = compute_auto_layout(schema)

    assert positions["loner_a"] != positions["loner_b"]

    rectangles = []
    for table in schema.tables:
        width, height = estimate_box_size(table)
        x, y = positions[table.name]
        rectangles.append((table.name, Rect(x, y, width, height)))
    for index, (left_name, left) in enumerate(rectangles):
        for right_name, right in rectangles[index + 1 :]:
            assert not left.overlaps(right), f"{left_name} overlaps {right_name}"


def test_layout_falls_back_if_graphviz_process_crashes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    schema = parse_ddl(SAMPLE_DDL)

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise GraphvizProcessError("native crash")

    monkeypatch.setattr(
        "gimme_the_diagram.layout_engine.graphviz_layout.run_graphviz_job", fail
    )

    positions = compute_auto_layout(schema)

    assert set(positions) == {"authors", "books"}
    assert positions["authors"] != positions["books"]
