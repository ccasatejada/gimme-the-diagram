from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RelationshipKind(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    fk_target: tuple[str, str | None] | None = None


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    primary_key: tuple[str, ...] = field(default_factory=tuple)
    unique_constraints: tuple[frozenset[str], ...] = field(default_factory=tuple)

    def get_column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class Relationship:
    left_table: str
    right_table: str
    kind: RelationshipKind
    via_table: str | None = None


@dataclass
class Schema:
    tables: list[Table] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def get_table(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name == name), None)
