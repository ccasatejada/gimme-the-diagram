from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, Select, SelectionList, TextArea

from gimme_the_diagram.parsing.ddl_parser import parse_ddl
from gimme_the_diagram.schema.layout import build_layout, load_layout
from gimme_the_diagram.ui.app import DiagramScreen, MainApp
from gimme_the_diagram.ui.canvas import DiagramCanvas
from gimme_the_diagram.ui.dialogs import ExportDialog, FileBrowserDialog

SAMPLE_DDL = """
CREATE TABLE authors (id INTEGER PRIMARY KEY, name VARCHAR(255));
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id)
);
"""


class _FakeMouseMove:
    """A minimal stand-in for events.MouseMove, for calling on_mouse_move directly."""

    def __init__(self, delta_x: int = 1, delta_y: int = 1) -> None:
        self.x = 5
        self.y = 5
        self.delta_x = delta_x
        self.delta_y = delta_y

    def stop(self) -> None:
        # mock mouse
        pass


def test_layout_save_falls_back_when_primary_path_is_not_writable(
    tmp_path: Path,
) -> None:
    schema = parse_ddl(SAMPLE_DDL)
    layout = build_layout(schema)
    fallback_path = tmp_path / "fallback.layout.json"
    # tmp_path is a directory: writing a file "at" it raises OSError, standing in for
    # a source file whose directory isn't writable (owned by another user, read-only, ...)
    screen = DiagramScreen(schema, layout, tmp_path, fallback_path)

    screen._save()

    assert screen.layout_path == fallback_path
    assert load_layout(fallback_path) is not None


@pytest.mark.asyncio
async def test_pasting_ddl_opens_diagram_screen() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        assert isinstance(app.screen, DiagramScreen)
        assert {t.name for t in app.screen.schema.tables} == {"authors", "books"}


@pytest.mark.asyncio
async def test_detail_level_buttons_change_detail_level() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        initial_level = screen.diagram_layout.zoom_level

        await pilot.click("#detail-down")
        await pilot.pause()
        assert screen.diagram_layout.zoom_level == initial_level - 1

        await pilot.click("#detail-up")
        await pilot.pause()
        assert screen.diagram_layout.zoom_level == initial_level


@pytest.mark.asyncio
async def test_back_button_returns_to_source_screen() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()
        assert isinstance(app.screen, DiagramScreen)

        await pilot.click("#back-button")
        await pilot.pause()
        assert not isinstance(app.screen, DiagramScreen)


@pytest.mark.asyncio
async def test_toggle_all_checkbox_shows_and_hides_every_table() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        assert all(p.visible for p in screen.diagram_layout.positions.values())

        await pilot.click("#toggle-all")
        await pilot.pause()
        assert all(not p.visible for p in screen.diagram_layout.positions.values())

        await pilot.click("#toggle-all")
        await pilot.pause()
        assert all(p.visible for p in screen.diagram_layout.positions.values())


@pytest.mark.asyncio
async def test_hiding_table_via_sidebar_updates_canvas() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
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
async def test_single_click_on_a_row_still_toggles_visibility() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        assert screen.diagram_layout.positions["books"].visible is True

        # a genuine single click (not a double-click) still toggles, after the
        # same delay Textual uses to decide whether a second click is coming
        await pilot.click("#table-selection", offset=(2, 2))
        await pilot.pause(app.CLICK_CHAIN_TIME_THRESHOLD + 0.1)

        assert screen.diagram_layout.positions["books"].visible is False


@pytest.mark.asyncio
async def test_dragging_a_table_throttles_diagram_refresh() -> None:
    """Regression guard for the app appearing to hang while dragging: without
    throttling, every mouse-move during a drag re-renders the whole diagram
    synchronously, which for a large schema can take far longer than the time
    between two mouse-move events."""
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        canvas = screen.canvas

        refresh_calls = 0
        original_refresh = canvas.refresh_diagram

        def counting_refresh() -> None:
            nonlocal refresh_calls
            refresh_calls += 1
            original_refresh()

        canvas.refresh_diagram = counting_refresh  # type: ignore[method-assign]

        # mouse-down on the "authors" table box, near its top-left corner
        await pilot.mouse_down(canvas, offset=(2, 1))
        assert canvas._dragged_table == "authors"
        refresh_calls = 0

        # Simulate 10 rapid mouse-move events back-to-back, with no idle time in
        # between (unlike pilot.hover(), which pauses before each event and would
        # let the throttle timer fire in between, defeating the point of this test).
        for _ in range(10):
            canvas.on_mouse_move(_FakeMouseMove())
        # none of these should have triggered a synchronous refresh yet
        assert refresh_calls == 0

        await pilot.pause(canvas.DRAG_REFRESH_INTERVAL + 0.05)
        # throttled to exactly one refresh, instead of one per mouse-move
        assert refresh_calls == 1

        await pilot.mouse_up(canvas, offset=(2, 1))


@pytest.mark.asyncio
async def test_double_click_table_name_scrolls_canvas_to_it() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        screen.diagram_layout.positions["books"].x = 500
        screen.diagram_layout.positions["books"].y = 500
        screen.canvas.refresh_diagram()
        await pilot.pause()
        assert screen.canvas.scroll_offset.x == 0
        assert screen.canvas.scroll_offset.y == 0

        # "books" is the second row in the sidebar list; y=0 is the list's own border
        await pilot.click("#table-selection", offset=(2, 2), times=2)
        await pilot.pause()

        # scroll_to clamps to the canvas's max scroll, so it won't be exactly (500, 500)
        assert screen.canvas.scroll_offset.x > 400
        assert screen.canvas.scroll_offset.y > 400
        # the double-click's first click shouldn't have left "books" toggled off
        assert screen.diagram_layout.positions["books"].visible is True


@pytest.mark.asyncio
async def test_export_mermaid_writes_file(tmp_path: Path) -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
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


@pytest.mark.asyncio
async def test_export_mermaid_current_view_excludes_tables_scrolled_out_of_sight(
    tmp_path: Path,
) -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#ddl-input", TextArea).text = SAMPLE_DDL
        await pilot.click("#generate")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, DiagramScreen)
        # "books" stays checked in the sidebar, but is moved far out of the viewport
        screen.diagram_layout.positions["books"].x = 5000
        screen.diagram_layout.positions["books"].y = 5000
        screen.canvas.refresh_diagram()
        await pilot.pause()

        await pilot.click("#export-mermaid")
        await pilot.pause()

        assert isinstance(app.screen, ExportDialog)
        output_path = tmp_path / "current_view.mmd"
        app.screen.query_one("#export-path", Input).value = str(output_path)
        await pilot.click("#export-confirm")
        await pilot.pause()

        content = output_path.read_text(encoding="utf-8")
        assert "authors {" in content
        assert "books {" not in content


@pytest.mark.asyncio
async def test_browse_button_opens_file_browser_dialog() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#mode-select", Select).value = "file"
        await pilot.pause()

        await pilot.click("#browse-file")
        await pilot.pause()

        assert isinstance(app.screen, FileBrowserDialog)

        await pilot.click("#browser-cancel")
        await pilot.pause()
        assert not isinstance(app.screen, FileBrowserDialog)


@pytest.mark.asyncio
async def test_db_mode_uses_a_dialect_select_not_radio_buttons() -> None:
    app = MainApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#mode-select", Select).value = "db"
        await pilot.pause()

        dialect = app.screen.query_one("#db-dialect", Select)
        assert dialect.value == "postgres"
