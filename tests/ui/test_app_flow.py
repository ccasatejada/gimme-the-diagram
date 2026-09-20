from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, SelectionList, TextArea

from gimme_the_diagram.ui.app import DiagramScreen, MainApp
from gimme_the_diagram.ui.canvas import DiagramCanvas
from gimme_the_diagram.ui.dialogs import ExportDialog

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


@pytest.mark.asyncio
async def test_pasting_ddl_opens_diagram_screen() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#load-paste")
        await pilot.pause()

        assert isinstance(app.screen, DiagramScreen)
        assert {t.name for t in app.screen.schema.tables} == {"authors", "books"}


@pytest.mark.asyncio
async def test_zoom_buttons_change_zoom_level() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#load-paste")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        initial_zoom = screen.diagram_layout.zoom_level

        await pilot.click("#zoom-out")
        await pilot.pause()
        assert screen.diagram_layout.zoom_level == initial_zoom - 1

        await pilot.click("#zoom-in")
        await pilot.pause()
        assert screen.diagram_layout.zoom_level == initial_zoom


@pytest.mark.asyncio
async def test_hiding_table_via_sidebar_updates_canvas() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#load-paste")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        selection_list = screen.query_one("#table-selection", SelectionList)
        selection_list.deselect("books")
        await pilot.pause()

        assert screen.diagram_layout.positions["books"].visible is False
        canvas = screen.query_one(DiagramCanvas)
        assert canvas._grid is not None
        text = "\n".join(canvas._grid.row_text(y) for y in range(canvas._grid.height))
        assert "books" not in text


@pytest.mark.asyncio
async def test_export_mermaid_writes_file(tmp_path: Path) -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#load-paste")
        await pilot.pause()

        await pilot.click("#export-mermaid")
        await pilot.pause()

        assert isinstance(app.screen, ExportDialog)
        output_path = tmp_path / "out.mmd"
        app.screen.query_one("#export-path", Input).value = str(output_path)
        await pilot.click("#export-confirm")
        await pilot.pause()

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert content.startswith("erDiagram")
        assert "authors" in content
