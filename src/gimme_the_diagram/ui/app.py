from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header

from gimme_the_diagram.schema.layout import DiagramLayout, save_layout
from gimme_the_diagram.schema.model import Schema
from gimme_the_diagram.ui.canvas import DiagramCanvas
from gimme_the_diagram.ui.dialogs import ExportDialog, SourceScreen
from gimme_the_diagram.ui.sidebar import TableListPanel


class DiagramScreen(Screen[None]):
    """Main screen: sidebar (table visibility) + zoomable/pannable canvas + toolbar."""

    CSS = """
    #toolbar {
        height: 3;
        dock: top;
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
        self, schema: Schema, diagram_layout: DiagramLayout, layout_path: Path
    ) -> None:
        super().__init__()
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.layout_path = layout_path
        self.sidebar = TableListPanel(schema, diagram_layout)
        self.canvas = DiagramCanvas(schema, diagram_layout)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Button("Zoom -", id="zoom-out")
            yield Button("Zoom +", id="zoom-in")
            yield Button("Export Mermaid", id="export-mermaid")
            yield Button("Export PDF", id="export-pdf")
        with Horizontal(id="body"):
            yield self.sidebar
            yield self.canvas
        yield Footer()

    def _save(self) -> None:
        save_layout(self.layout_path, self.diagram_layout)

    def on_diagram_canvas_layout_changed(
        self, message: DiagramCanvas.LayoutChanged
    ) -> None:
        self._save()

    def on_table_list_panel_visibility_changed(
        self, message: TableListPanel.VisibilityChanged
    ) -> None:
        self.canvas.refresh_diagram()
        self._save()

    @on(Button.Pressed, "#zoom-in")
    def _zoom_in(self) -> None:
        self.canvas.zoom_in()

    @on(Button.Pressed, "#zoom-out")
    def _zoom_out(self) -> None:
        self.canvas.zoom_out()

    @on(Button.Pressed, "#export-mermaid")
    def _export_mermaid(self) -> None:
        self._open_export("mermaid", "diagram.mmd")

    @on(Button.Pressed, "#export-pdf")
    def _export_pdf(self) -> None:
        self._open_export("pdf", "diagram.pdf")

    def _open_export(self, kind: str, default_name: str) -> None:
        scroll = self.canvas.scroll_offset
        size = self.canvas.size
        viewport = (int(scroll.x), int(scroll.y), size.width, size.height)
        self.app.push_screen(
            ExportDialog(kind, self.schema, self.diagram_layout, viewport, default_name)
        )


class MainApp(App[None]):
    """Entry-point Textual application: pick a source, then browse the diagram."""

    TITLE = "Gimme The Diagram"

    def on_mount(self) -> None:
        self.push_screen(SourceScreen())

    def open_diagram(
        self, schema: Schema, diagram_layout: DiagramLayout, layout_path: Path
    ) -> None:
        self.switch_screen(DiagramScreen(schema, diagram_layout, layout_path))
