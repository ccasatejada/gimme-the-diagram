from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Select,
    TextArea,
)

from gimme_the_diagram.export.mermaid import export_mermaid_bundle, to_mermaid
from gimme_the_diagram.export.pdf import export_schema_to_pdf
from gimme_the_diagram.export.svg import export_schema_to_svg
from gimme_the_diagram.parsing.ddl_parser import parse_ddl_auto
from gimme_the_diagram.parsing.introspector import (
    build_postgres_url,
    build_sqlite_url,
    create_engine_for_url,
    introspect_schema,
)
from gimme_the_diagram.render.grid import CharGrid, render_diagram
from gimme_the_diagram.schema.layout import (
    DiagramLayout,
    build_layout,
    layout_fallback_path_for_file,
    layout_path_for_file,
    layout_path_for_key,
    load_layout,
)
from gimme_the_diagram.schema.model import Schema

_MODE_OPTIONS: list[tuple[str, str]] = [
    ("Paste DDL", "paste"),
    ("Import a DDL file", "file"),
    ("Database connection", "db"),
]
_DB_DIALECT_OPTIONS: list[tuple[str, str]] = [
    ("PostgreSQL", "postgres"),
    ("SQLite", "sqlite"),
]
_MERMAID_MODE_OPTIONS: list[tuple[str, str]] = [
    ("Detailed (.mmd)", "detailed"),
    ("Compact, no columns (.mmd)", "compact"),
    ("Split bundle (.zip)", "bundle"),
]

# The Select widget draws its own border + internal padding around its value, which
# a plain Label doesn't have. This left-pads field labels so their text lines up with
# a Select's text above them instead of sitting further left.
_LABEL_LEFT_INSET = 3


class FileBrowserDialog(ModalScreen[str | None]):
    """A simple in-app file picker (there is no native OS file dialog in a terminal)."""

    CSS = """
    FileBrowserDialog {
        align: center middle;
    }
    #browser-panel {
        width: 80%;
        height: 80%;
        border: round $accent;
        padding: 1 2;
    }
    #browser-tree {
        height: 1fr;
        margin-bottom: 1;
    }
    #browser-buttons {
        height: 3;
        align: right middle;
    }
    """

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self.start_path = start_path

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-panel"):
            yield Label(f"Choose a file ({self.start_path})")
            yield DirectoryTree(self.start_path, id="browser-tree")
            with Horizontal(id="browser-buttons"):
                yield Button("Cancel", id="browser-cancel")

    @on(Button.Pressed, "#browser-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(DirectoryTree.FileSelected)
    def _file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(str(event.path))


class SourceScreen(Screen[None]):
    """Lets the user choose how to load a schema: paste DDL, a DDL file, or a live DB."""

    DDL_FILEPATH_TAG = "#ddl-file-path"
    LOADING_PANEL_TAG = "#loading-panel"
    GENERATE_TAG = "#generate"
    CSS = f"""
    SourceScreen {{
        align: center middle;
    }}
    #source-panel {{
        width: 90%;
        height: 90%;
        border: round $accent;
        padding: 1 2;
    }}
    #mode-switcher {{
        height: 1fr;
        margin-top: 1;
    }}
    #mode-paste, #mode-file, #mode-db {{
        height: 1fr;
    }}
    #db-dialect {{
        width: 100%;
    }}
    .field-row {{
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }}
    .field-row Label {{
        width: 16;
        content-align: left middle;
        padding-left: {_LABEL_LEFT_INSET};
    }}
    .field-row Input {{
        width: 1fr;
    }}
    #ddl-input {{
        height: 1fr;
        margin-bottom: 1;
    }}
    #bottom-bar {{
        height: auto;
        dock: bottom;
    }}
    #error-label {{
        color: $error;
        height: auto;
    }}
    {LOADING_PANEL_TAG} {{
        display: none;
        height: auto;
        border: round $accent;
        padding: 1 2;
    }}
    #loading-status {{ margin-bottom: 1; }}
    #generate-row {{
        height: 3;
        align: right middle;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="source-panel"):
            yield Label("Schema source")
            yield Select(
                _MODE_OPTIONS, value="paste", allow_blank=False, id="mode-select"
            )
            with ContentSwitcher(initial="mode-paste", id="mode-switcher"):
                with Vertical(id="mode-paste"):
                    yield TextArea(id="ddl-input", language="sql")
                with Vertical(id="mode-file"), Horizontal(classes="field-row"):
                    yield Label("File")
                    yield Input(
                        placeholder="Enter a file path",
                        id="ddl-file-path",
                    )
                    yield Button("Browse…", id="browse-file")
                with Vertical(id="mode-db"):
                    yield Select(
                        _DB_DIALECT_OPTIONS,
                        value="postgres",
                        allow_blank=False,
                        id="db-dialect",
                    )
                    with Horizontal(classes="field-row"):
                        yield Label("Host")
                        yield Input(value="localhost", id="db-host")
                    with Horizontal(classes="field-row"):
                        yield Label("Port")
                        yield Input(value="5432", id="db-port")
                    with Horizontal(classes="field-row"):
                        yield Label("User")
                        yield Input(id="db-user")
                    with Horizontal(classes="field-row"):
                        yield Label("Password")
                        yield Input(id="db-password", password=True)
                    with Horizontal(classes="field-row"):
                        yield Label("Database / file")
                        yield Input(
                            placeholder="my_database or /path/to/database.sqlite3",
                            id="db-name",
                        )
            with Vertical(id="bottom-bar"):
                yield Label("", id="error-label")
                with Vertical(id="loading-panel"):
                    yield Label("Preparing…", id="loading-status")
                    yield ProgressBar(total=5, show_eta=False, id="loading-progress")
                with Horizontal(id="generate-row"):
                    yield Button("Generate diagram", id="generate", variant="primary")
        yield Footer()

    def _show_error(self, message: str) -> None:
        self.query_one("#error-label", Label).update(message)

    def _start_loading(
        self,
        schema_loader: Callable[[], Schema],
        layout_path: Path,
        fallback_layout_path: Path | None = None,
    ) -> None:
        self.query_one(self.LOADING_PANEL_TAG, Vertical).display = True
        self.query_one(self.GENERATE_TAG, Button).disabled = True
        self._load_schema_job(schema_loader, layout_path, fallback_layout_path)

    def _set_loading_stage(self, step: int, status: str) -> None:
        self.query_one("#loading-status", Label).update(status)
        self.query_one("#loading-progress", ProgressBar).update(progress=step)

    @work(exclusive=True, group="schema-loading", exit_on_error=False)
    async def _load_schema_job(
        self,
        schema_loader: Callable[[], Schema],
        layout_path: Path,
        fallback_layout_path: Path | None,
    ) -> None:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gtd-loader")
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                executor,
                self._run_loading_pipeline,
                schema_loader,
                layout_path,
                fallback_layout_path,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in the source screen
            self._loading_failed(str(exc))
            return
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        schema, layout, grid = result
        self._loading_finished(schema, layout, layout_path, fallback_layout_path, grid)

    def _run_loading_pipeline(
        self,
        schema_loader: Callable[[], Schema],
        layout_path: Path,
        fallback_layout_path: Path | None,
    ) -> tuple[Schema, DiagramLayout, CharGrid]:
        self.app.call_from_thread(self._set_loading_stage, 1, "1/5 — Reading source…")
        schema = schema_loader()
        if not schema.tables:
            raise ValueError("the schema contains no table")
        self.app.call_from_thread(self._set_loading_stage, 2, "2/5 — Schema validated")
        existing = load_layout(layout_path)
        if existing is None and fallback_layout_path is not None:
            existing = load_layout(fallback_layout_path)
        self.app.call_from_thread(self._set_loading_stage, 3, "3/5 — Placing tables…")
        layout = build_layout(schema, existing)
        self.app.call_from_thread(
            self._set_loading_stage, 4, "4/5 — Routing relationships…"
        )
        grid = render_diagram(schema, layout)
        self.app.call_from_thread(
            self._set_loading_stage, 5, "5/5 — Preparing diagram…"
        )
        return schema, layout, grid

    def _loading_failed(self, message: str) -> None:
        self.query_one(self.LOADING_PANEL_TAG, Vertical).display = False
        self.query_one(self.GENERATE_TAG, Button).disabled = False
        self._show_error(f"Loading failed: {message}")

    def _loading_finished(
        self,
        schema: Schema,
        layout: DiagramLayout,
        layout_path: Path,
        fallback_layout_path: Path | None,
        grid: CharGrid,
    ) -> None:
        self.query_one(self.LOADING_PANEL_TAG, Vertical).display = False
        self.query_one(self.GENERATE_TAG, Button).disabled = False
        self.app.open_diagram(  # type: ignore[attr-defined]
            schema, layout, layout_path, fallback_layout_path, grid
        )

    @on(Select.Changed, "#mode-select")
    def _switch_mode(self, event: Select.Changed) -> None:
        mode = event.value
        self.query_one("#mode-switcher", ContentSwitcher).current = f"mode-{mode}"
        self._show_error("")
        if mode == "file":
            self.query_one(self.DDL_FILEPATH_TAG, Input).focus()
        elif mode == "paste":
            self.query_one("#ddl-input", TextArea).focus()

    @on(Button.Pressed, "#browse-file")
    def _browse_file(self) -> None:
        raw_path = self.query_one(self.DDL_FILEPATH_TAG, Input).value.strip()
        start_path = Path(raw_path).expanduser().parent if raw_path else Path.cwd()
        if not start_path.is_dir():
            start_path = Path.cwd()
        self.app.push_screen(FileBrowserDialog(start_path), self._set_file_path)

    def _set_file_path(self, path: str | None) -> None:
        if path is not None:
            self.query_one(self.DDL_FILEPATH_TAG, Input).value = path

    @on(Button.Pressed, GENERATE_TAG)
    def _generate(self) -> None:
        mode = self.query_one("#mode-select", Select).value
        self._show_error("")
        if mode == "paste":
            self._load_pasted_ddl()
        elif mode == "file":
            self._load_ddl_file()
        elif mode == "db":
            self._load_from_database()

    def _load_pasted_ddl(self) -> None:
        ddl_text = self.query_one("#ddl-input", TextArea).text
        if not ddl_text.strip():
            self._show_error("Please paste some SQL DDL.")
            return
        self._start_loading(
            lambda: parse_ddl_auto(ddl_text), layout_path_for_key(ddl_text)
        )

    def _load_ddl_file(self) -> None:
        raw_path = self.query_one(self.DDL_FILEPATH_TAG, Input).value.strip()
        if not raw_path:
            self._show_error("Please enter a file path.")
            return
        path = Path(raw_path).expanduser()
        self._start_loading(
            lambda: parse_ddl_auto(path.read_text(encoding="utf-8")),
            layout_path_for_file(path),
            layout_fallback_path_for_file(path),
        )

    def _load_from_database(self) -> None:
        is_sqlite = self.query_one("#db-dialect", Select).value == "sqlite"
        database = self.query_one("#db-name", Input).value.strip()
        if not database:
            self._show_error("Please enter a database (name or file path).")
            return

        if is_sqlite:
            url = build_sqlite_url(database)
            layout_key = f"sqlite:{database}"
        else:
            host = self.query_one("#db-host", Input).value.strip() or "localhost"
            port_text = self.query_one("#db-port", Input).value.strip() or "5432"
            user = self.query_one("#db-user", Input).value.strip()
            password = self.query_one("#db-password", Input).value
            try:
                port = int(port_text)
            except ValueError:
                self._show_error("Port must be a number.")
                return
            url = build_postgres_url(host, port, user, password, database)
            layout_key = f"postgres:{host}:{port}:{database}"

        def load_database() -> Schema:
            engine = create_engine_for_url(url)
            return introspect_schema(engine)

        self._start_loading(load_database, layout_path_for_key(layout_key))


class ExportDialog(ModalScreen[None]):
    """Modal asking for export scope (current view / full diagram) and a destination path."""

    CSS = f"""
    ExportDialog {{
        align: center middle;
    }}
    #export-panel {{
        width: 70;
        height: auto;
        border: round $accent;
        padding: 1 2;
    }}
    .field-row {{
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }}
    .field-row Label {{
        width: 16;
        content-align: left middle;
        padding-left: {_LABEL_LEFT_INSET};
    }}
    .field-row Input {{
        width: 1fr;
    }}
    #export-error {{
        color: $error;
        height: auto;
    }}
    #export-buttons {{
        height: 3;
        align: right middle;
    }}
    """

    def __init__(
        self,
        kind: str,
        schema: Schema,
        diagram_layout: DiagramLayout,
        viewport: tuple[int, int, int, int],
        viewport_table_names: set[str],
        default_path: str,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.viewport = viewport
        self.viewport_table_names = viewport_table_names
        self.default_path = default_path

    def compose(self) -> ComposeResult:
        titles = {
            "mermaid": "Export Mermaid",
            "svg": "Export SVG",
            "pdf": "Export PDF",
        }
        with Vertical(id="export-panel"):
            yield Label(titles[self.kind])
            if self.kind == "mermaid":
                yield Select(
                    _MERMAID_MODE_OPTIONS,
                    value="detailed",
                    allow_blank=False,
                    id="mermaid-mode",
                )
            yield RadioSet(
                RadioButton(
                    "Current view (tables visible on screen)",
                    value=True,
                    id="scope-current",
                ),
                RadioButton("Full diagram (all tables)", id="scope-full"),
                id="export-scope",
            )
            with Horizontal(classes="field-row"):
                yield Label("Destination")
                yield Input(value=self.default_path, id="export-path")
            with Horizontal(id="export-buttons"):
                yield Button("Cancel", id="export-cancel")
                yield Button("Export", id="export-confirm", variant="primary")
            yield Label("", id="export-error")

    @on(Button.Pressed, "#export-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#export-confirm")
    def _confirm(self) -> None:
        full_diagram = self.query_one("#scope-full", RadioButton).value
        raw_path = self.query_one("#export-path", Input).value.strip()
        if not raw_path:
            self.query_one("#export-error", Label).update(
                "Please enter a destination path."
            )
            return
        path = Path(raw_path).expanduser()

        try:
            order = [
                name
                for name, _ in sorted(
                    self.diagram_layout.positions.items(),
                    key=lambda item: (item[1].y, item[1].x),
                )
            ]
            if full_diagram:
                visible = None
            else:
                sidebar_visible = {
                    name
                    for name, position in self.diagram_layout.positions.items()
                    if position.visible
                }
                visible = sidebar_visible & self.viewport_table_names
            if self.kind == "mermaid":
                mode = self.query_one("#mermaid-mode", Select).value
                if mode == "bundle":
                    export_mermaid_bundle(self.schema, path, visible, order)
                else:
                    path.write_text(
                        to_mermaid(
                            self.schema,
                            visible,
                            order,
                            include_columns=mode == "detailed",
                        ),
                        encoding="utf-8",
                    )
            elif self.kind == "svg":
                export_schema_to_svg(
                    self.schema,
                    self.diagram_layout,
                    path,
                    full_diagram=full_diagram,
                    viewport=None if full_diagram else self.viewport,
                )
            else:
                export_schema_to_pdf(
                    self.schema,
                    self.diagram_layout,
                    path,
                    full_diagram=full_diagram,
                    viewport=None if full_diagram else self.viewport,
                )
        except Exception as exc:  # noqa: BLE001 - never let a bad export crash the app
            self.query_one("#export-error", Label).update(f"Export failed: {exc}")
            return

        self.dismiss(None)
