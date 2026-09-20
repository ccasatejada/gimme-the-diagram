from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    TabbedContent,
    TabPane,
    TextArea,
)

from gimme_the_diagram.export.mermaid import to_mermaid
from gimme_the_diagram.export.pdf import export_schema_to_pdf
from gimme_the_diagram.parsing.ddl_parser import DDLParseError, parse_ddl
from gimme_the_diagram.parsing.introspector import (
    IntrospectionError,
    build_postgres_url,
    build_sqlite_url,
    create_engine_for_url,
    introspect_schema,
)
from gimme_the_diagram.schema.layout import (
    DiagramLayout,
    build_layout,
    layout_path_for_file,
    layout_path_for_key,
    load_layout,
)
from gimme_the_diagram.schema.model import Schema


class SourceScreen(Screen[None]):
    """Lets the user choose how to load a schema: paste DDL, a DDL file, or a live DB."""

    CSS = """
    SourceScreen {
        align: center middle;
    }
    #source-panel {
        width: 90%;
        height: 90%;
        border: round $accent;
        padding: 1 2;
    }
    .field-row {
        height: 3;
        margin-bottom: 1;
    }
    .field-row Label {
        width: 16;
        content-align: left middle;
    }
    #ddl-input {
        height: 1fr;
        margin-bottom: 1;
    }
    #error-label {
        color: $error;
        height: auto;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="source-panel"):
            with TabbedContent():
                with TabPane("Coller du DDL", id="tab-paste"):
                    yield TextArea(id="ddl-input", language="sql")
                    yield Button(
                        "Charger le DDL collé", id="load-paste", variant="primary"
                    )
                with TabPane("Fichier DDL", id="tab-file"):
                    with Horizontal(classes="field-row"):
                        yield Label("Chemin du fichier")
                        yield Input(
                            placeholder="/chemin/vers/schema.sql", id="ddl-file-path"
                        )
                    yield Button(
                        "Charger le fichier", id="load-file", variant="primary"
                    )
                with TabPane("Connexion base de données", id="tab-db"):
                    yield RadioSet(
                        RadioButton("PostgreSQL", value=True, id="dialect-postgres"),
                        RadioButton("SQLite", id="dialect-sqlite"),
                        id="dialect-choice",
                    )
                    with Horizontal(classes="field-row"):
                        yield Label("Hôte")
                        yield Input(value="localhost", id="db-host")
                    with Horizontal(classes="field-row"):
                        yield Label("Port")
                        yield Input(value="5432", id="db-port")
                    with Horizontal(classes="field-row"):
                        yield Label("Utilisateur")
                        yield Input(id="db-user")
                    with Horizontal(classes="field-row"):
                        yield Label("Mot de passe")
                        yield Input(id="db-password", password=True)
                    with Horizontal(classes="field-row"):
                        yield Label("Base / fichier")
                        yield Input(
                            placeholder="ma_base ou /chemin/vers/base.sqlite3",
                            id="db-name",
                        )
                    yield Button("Se connecter", id="load-db", variant="primary")
            yield Label("", id="error-label")
        yield Footer()

    def _show_error(self, message: str) -> None:
        self.query_one("#error-label", Label).update(message)

    def _open_schema(self, schema: Schema, layout_path: Path) -> None:
        existing = load_layout(layout_path)
        layout = build_layout(schema, existing)
        self.app.open_diagram(schema, layout, layout_path)  # type: ignore[attr-defined]

    @on(Button.Pressed, "#load-paste")
    def _load_pasted_ddl(self) -> None:
        ddl_text = self.query_one("#ddl-input", TextArea).text
        if not ddl_text.strip():
            self._show_error("Veuillez coller un DDL SQL.")
            return
        try:
            schema = parse_ddl(ddl_text)
        except DDLParseError as exc:
            self._show_error(f"Erreur de parsing DDL : {exc}")
            return
        self._open_schema(schema, layout_path_for_key(ddl_text))

    @on(Button.Pressed, "#load-file")
    def _load_ddl_file(self) -> None:
        raw_path = self.query_one("#ddl-file-path", Input).value.strip()
        if not raw_path:
            self._show_error("Veuillez indiquer un chemin de fichier.")
            return
        path = Path(raw_path).expanduser()
        try:
            ddl_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self._show_error(f"Impossible de lire le fichier : {exc}")
            return
        try:
            schema = parse_ddl(ddl_text)
        except DDLParseError as exc:
            self._show_error(f"Erreur de parsing DDL : {exc}")
            return
        self._open_schema(schema, layout_path_for_file(path))

    @on(Button.Pressed, "#load-db")
    def _load_from_database(self) -> None:
        is_sqlite = self.query_one("#dialect-sqlite", RadioButton).value
        database = self.query_one("#db-name", Input).value.strip()
        if not database:
            self._show_error("Veuillez indiquer une base (nom ou chemin).")
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
                self._show_error("Le port doit être un nombre.")
                return
            url = build_postgres_url(host, port, user, password, database)
            layout_key = f"postgres:{host}:{port}:{database}"

        try:
            engine = create_engine_for_url(url)
            schema = introspect_schema(engine)
        except IntrospectionError as exc:
            self._show_error(f"Échec de connexion/introspection : {exc}")
            return

        self._open_schema(schema, layout_path_for_key(layout_key))


class ExportDialog(ModalScreen[None]):
    """Modal asking for export scope (current view / full diagram) and a destination path."""

    CSS = """
    ExportDialog {
        align: center middle;
    }
    #export-panel {
        width: 70;
        height: auto;
        border: round $accent;
        padding: 1 2;
    }
    .field-row {
        height: 3;
        margin-bottom: 1;
    }
    .field-row Label {
        width: 16;
        content-align: left middle;
    }
    #export-error {
        color: $error;
        height: auto;
    }
    #export-buttons {
        height: 3;
        align: right middle;
    }
    """

    def __init__(
        self,
        kind: str,
        schema: Schema,
        diagram_layout: DiagramLayout,
        viewport: tuple[int, int, int, int],
        default_path: str,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.schema = schema
        self.diagram_layout = diagram_layout
        self.viewport = viewport
        self.default_path = default_path

    def compose(self) -> ComposeResult:
        title = "Export Mermaid" if self.kind == "mermaid" else "Export PDF"
        with Vertical(id="export-panel"):
            yield Label(title)
            yield RadioSet(
                RadioButton(
                    "Vue actuelle (tables visibles à l'écran)",
                    value=True,
                    id="scope-current",
                ),
                RadioButton("Diagramme complet (toutes les tables)", id="scope-full"),
                id="export-scope",
            )
            with Horizontal(classes="field-row"):
                yield Label("Destination")
                yield Input(value=self.default_path, id="export-path")
            with Horizontal(id="export-buttons"):
                yield Button("Annuler", id="export-cancel")
                yield Button("Exporter", id="export-confirm", variant="primary")
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
                "Veuillez indiquer un chemin de destination."
            )
            return
        path = Path(raw_path).expanduser()

        try:
            if self.kind == "mermaid":
                visible = (
                    None
                    if full_diagram
                    else {
                        name
                        for name, position in self.diagram_layout.positions.items()
                        if position.visible
                    }
                )
                path.write_text(to_mermaid(self.schema, visible), encoding="utf-8")
            else:
                export_schema_to_pdf(
                    self.schema,
                    self.diagram_layout,
                    path,
                    full_diagram=full_diagram,
                    viewport=None if full_diagram else self.viewport,
                )
        except OSError as exc:
            self.query_one("#export-error", Label).update(f"Échec de l'export : {exc}")
            return

        self.dismiss(None)
