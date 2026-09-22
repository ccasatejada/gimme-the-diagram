from __future__ import annotations

from gimme_the_diagram.layout_engine.graphviz_layout import (
    compute_graphviz_layout,
    estimate_box_size,
)
from gimme_the_diagram.schema.model import Schema

__all__ = ["compute_auto_layout", "estimate_box_size"]


def compute_auto_layout(schema: Schema) -> dict[str, tuple[int, int]]:
    """Compute the initial table positions with Graphviz's layered layout."""
    return compute_graphviz_layout(schema)
