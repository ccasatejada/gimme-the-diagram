from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, SelectionList

from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import Schema


class TableListPanel(Vertical):
    """Sidebar listing every table in the schema; toggling one shows/hides it on the canvas."""

    class VisibilityChanged(Message):
        """Posted whenever the user toggles a table's visibility."""

    def __init__(self, schema: Schema, diagram_layout: DiagramLayout) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout

    def compose(self) -> ComposeResult:
        yield Label("Tables", classes="sidebar-title")
        selections = [
            (
                table.name,
                table.name,
                self.diagram_layout.positions.get(table.name) is None
                or self.diagram_layout.positions[table.name].visible,
            )
            for table in self.schema.tables
        ]
        yield SelectionList[str](*selections, id="table-selection")

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged[str]
    ) -> None:
        selected = set(event.selection_list.selected)
        for table in self.schema.tables:
            position = self.diagram_layout.positions.get(table.name)
            if position is not None:
                position.visible = table.name in selected
        self.post_message(self.VisibilityChanged())
