from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Checkbox, Label, SelectionList

from gimme_the_diagram.schema.layout import DiagramLayout
from gimme_the_diagram.schema.model import Schema


class _TableSelectionList(SelectionList[str]):
    """A SelectionList where double-clicking a row navigates instead of toggling it.

    OptionList's own click handler toggles the row on every click. Left alone, a
    double-click would toggle the row twice (once per click) while racing against the
    canvas navigating to a table that a stray intermediate toggle just hid. Instead,
    a single click's toggle is deferred by the same window Textual itself uses to
    detect double-clicks (`App.CLICK_CHAIN_TIME_THRESHOLD`); if a second click arrives
    in that window, the toggle is skipped entirely and the row is activated instead.
    """

    class TableActivated(Message):
        """Posted when the user double-clicks a table's name."""

        def __init__(self, table_name: str) -> None:
            super().__init__()
            self.table_name = table_name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pending_toggle_index: int | None = None

    async def _on_click(self, event: events.Click) -> None:
        option_index = event.style.meta.get("option")
        if option_index is None or self._options[option_index].disabled:
            return
        # OptionList's own `_on_click` (which selects/toggles) is a separate handler
        # that Textual calls regardless of this override - prevent_default() is the
        # only way to stop it from also firing for this event.
        event.prevent_default()
        if event.chain == 2:
            self._pending_toggle_index = None
            option = self.get_option_at_index(option_index)
            self.post_message(self.TableActivated(option.value))
            event.stop()
            return
        self.highlighted = option_index
        self._pending_toggle_index = option_index
        self.set_timer(
            self.app.CLICK_CHAIN_TIME_THRESHOLD,
            self._make_toggle_callback(option_index),
        )
        event.stop()

    def _make_toggle_callback(self, option_index: int) -> Callable[[], None]:
        def _toggle_if_still_pending() -> None:
            if self._pending_toggle_index == option_index:
                self._pending_toggle_index = None
                self.toggle(self.get_option_at_index(option_index).value)

        return _toggle_if_still_pending


class TableListPanel(Vertical):
    """Sidebar listing every table in the schema.

    Clicking a table's checkbox shows/hides it on the canvas. Double-clicking its name
    scrolls the canvas to that table instead. The checkbox above the list shows/hides
    every table at once.
    """

    class VisibilityChanged(Message):
        """Posted whenever the user toggles a table's visibility."""

    class TableActivated(Message):
        """Posted when the user double-clicks a table's name."""

        def __init__(self, table_name: str) -> None:
            super().__init__()
            self.table_name = table_name

    def __init__(self, schema: Schema, diagram_layout: DiagramLayout) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout

    def compose(self) -> ComposeResult:
        yield Label("Tables", classes="sidebar-title")
        yield Checkbox("Show all", value=True, id="toggle-all")
        selections = [
            (
                table.name,
                table.name,
                self.diagram_layout.positions.get(table.name) is None
                or self.diagram_layout.positions[table.name].visible,
            )
            for table in self.schema.tables
        ]
        yield _TableSelectionList(*selections, id="table-selection")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != "toggle-all":
            return
        selection_list = self.query_one(_TableSelectionList)
        if event.value:
            selection_list.select_all()
        else:
            selection_list.deselect_all()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged[str]
    ) -> None:
        selected = set(event.selection_list.selected)
        for table in self.schema.tables:
            position = self.diagram_layout.positions.get(table.name)
            if position is not None:
                position.visible = table.name in selected
        self.post_message(self.VisibilityChanged())

    def on__table_selection_list_table_activated(
        self, event: _TableSelectionList.TableActivated
    ) -> None:
        self.post_message(self.TableActivated(event.table_name))
