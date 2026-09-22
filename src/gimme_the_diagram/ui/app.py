from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from gimme_the_diagram.render.geometry import Rect
from gimme_the_diagram.render.grid import CharGrid, compute_table_boxes
from gimme_the_diagram.schema.layout import DiagramLayout, save_layout
from gimme_the_diagram.schema.model import Schema
from gimme_the_diagram.ui.canvas import DiagramCanvas
from gimme_the_diagram.ui.dialogs import ExportDialog, SourceScreen
from gimme_the_diagram.ui.sidebar import TableListPanel


class DiagramScreen(Screen[None]):
    """Main screen: sidebar (table visibility) + pannable canvas + toolbar."""

    CSS = """
    #toolbar {
        height: 3;
        dock: top;
    }
    #back-button {
        width: auto;
        min-width: 5;
    }
    #toolbar-spacer {
        width: 1fr;
    }
    #toolbar-actions {
        width: auto;
    }
    #body {
        height: 1fr;
    }
    TableListPanel {
        width: 28;
        border-right: solid $accent;
    }
    """

    def __init__(
        self,
        schema: Schema,
        diagram_layout: DiagramLayout,
        layout_path: Path,
        fallback_layout_path: Path | None = None,
        initial_grid: CharGrid | None = None,
    ) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.layout_path = layout_path
        self.fallback_layout_path = fallback_layout_path
        self.sidebar = TableListPanel(schema, diagram_layout)
        self.canvas = DiagramCanvas(schema, diagram_layout, initial_grid)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Button("←", id="back-button")
            yield Static(id="toolbar-spacer")
            with Horizontal(id="toolbar-actions"):
                yield Button("Detail −", id="detail-down")
                yield Button("Detail +", id="detail-up")
                yield Button("Export Mermaid", id="export-mermaid")
                yield Button("Export SVG", id="export-svg")
                yield Button("Export PDF", id="export-pdf")
        with Horizontal(id="body"):
            yield self.sidebar
            yield self.canvas
        yield Footer()

    def _save(self) -> None:
        try:
            save_layout(self.layout_path, self.diagram_layout)
        except OSError:
            # e.g. the DDL file's directory isn't writable (owned by another user,
            # read-only mount, ...) - fall back once to the app's own data directory,
            # and remember that choice for the rest of the session.
            if self.fallback_layout_path is not None:
                self.layout_path = self.fallback_layout_path
                self.fallback_layout_path = None
                self._save()

    def on_diagram_canvas_layout_changed(
        self, message: DiagramCanvas.LayoutChanged
    ) -> None:
        self._save()

    def on_table_list_panel_visibility_changed(
        self, message: TableListPanel.VisibilityChanged
    ) -> None:
        self.canvas.refresh_diagram()
        self._save()

    def on_table_list_panel_table_activated(
        self, message: TableListPanel.TableActivated
    ) -> None:
        self.canvas.scroll_to_table(message.table_name)

    @on(Button.Pressed, "#back-button")
    def _go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#detail-up")
    def _detail_up(self) -> None:
        self.canvas.detail_up()

    @on(Button.Pressed, "#detail-down")
    def _detail_down(self) -> None:
        self.canvas.detail_down()

    @on(Button.Pressed, "#export-mermaid")
    def _export_mermaid(self) -> None:
        self._open_export("mermaid", "diagram.mmd")

    @on(Button.Pressed, "#export-pdf")
    def _export_pdf(self) -> None:
        self._open_export("pdf", "diagram.pdf")

    @on(Button.Pressed, "#export-svg")
    def _export_svg(self) -> None:
        self._open_export("svg", "diagram.svg")

    def _open_export(self, kind: str, default_name: str) -> None:
        scroll = self.canvas.scroll_offset
        size = self.canvas.size
        viewport = (int(scroll.x), int(scroll.y), size.width, size.height)
        viewport_rect = Rect(*viewport)
        boxes = compute_table_boxes(
            self.schema, self.diagram_layout, self.diagram_layout.zoom_level
        )
        visible_in_viewport = {
            name for name, box in boxes.items() if box.rect.overlaps(viewport_rect)
        }
        self.app.push_screen(
            ExportDialog(
                kind,
                self.schema,
                self.diagram_layout,
                viewport,
                visible_in_viewport,
                default_name,
            )
        )


class MainApp(App[None]):
    """Entry-point Textual application: pick a source, then browse the diagram."""

    TITLE = "Gimme The Diagram"

    def on_mount(self) -> None:
        self.push_screen(SourceScreen())

    def open_diagram(
        self,
        schema: Schema,
        diagram_layout: DiagramLayout,
        layout_path: Path,
        fallback_layout_path: Path | None = None,
        initial_grid: CharGrid | None = None,
    ) -> None:
        self.push_screen(
            DiagramScreen(
                schema,
                diagram_layout,
                layout_path,
                fallback_layout_path,
                initial_grid,
            )
        )
