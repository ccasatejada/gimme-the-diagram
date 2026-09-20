![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=astral&logoColor=white)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![mypy](https://img.shields.io/badge/type%20checker-mypy%20strict-blue?logo=python&logoColor=white)
![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)
![CI](https://github.com/ccasatejada/gimme-the-diagram/actions/workflows/ci.yml/badge.svg)      


## gimme-the-diagram

A terminal (Textual) SQL schema visualizer. Load a schema either by pasting/loading raw
DDL (`CREATE TABLE`/`ALTER TABLE`) or by connecting live to a PostgreSQL/SQLite database,
and browse it as an ERD: tables, columns with types, and one-to-one / one-to-many /
many-to-many relationships (auto-detected, including many-to-many junction tables).

- Show/hide tables from the sidebar checklist.
- Pan and drag tables to rearrange the diagram; the arrangement is persisted to a
  `<source>.layout.json` sidecar file and restored on the next run.
- Zoom in/out via the mouse wheel, the `+`/`-` keys, or the toolbar buttons (controls the
  level of detail shown per table).
- Export to Mermaid (`erDiagram`, embeddable in Markdown) or to a monospace, terminal-faithful
  PDF — either just what's currently visible or the whole diagram.

```bash
gimme-the-diagram
```

## boilerplate
- python3.14
- textual (tui)
- sqlalchemy (live PostgreSQL/SQLite schema introspection)
- uv
- mypy
- ruff
- pre-commit (run ruff and mypy)
- minimal github action for linting / test
- PyPA-compliant `src` layout, packaged with hatchling, installable as a `gimme-the-diagram` CLI

### Project layout

```
.
├── src/
│   └── gimme_the_diagram/          # the installable package
│       ├── schema/                 # domain model (Table/Column/Relationship) + layout persistence
│       ├── parsing/                 # DDL parsing (sqlglot) + live DB introspection
│       ├── layout_engine/           # automatic table placement
│       ├── render/                  # schema+layout -> character grid (shared by the TUI and PDF export)
│       ├── export/                  # Mermaid and PDF export
│       ├── ui/                      # Textual screens/widgets
│       └── main.py                  # Textual app + `run()` entry point
├── tests/                           # kept out of src/, per PyPA recommendations
└── pyproject.toml
```

### reminders
```
after cloning, run:
$ uv sync
$ uv run pre-commit install
```

### Install & run

During development, `uv sync` installs the project itself in editable mode alongside its
dependencies, so the `gimme-the-diagram` command is available in the venv without `uv run`:

```bash
uv sync
gimme-the-diagram
```

If the venv's `bin` directory isn't on your `PATH`, prefix with `uv run`:

```bash
uv run gimme-the-diagram
```

To install the CLI outside of a project venv (e.g. as a standalone tool):

```bash
uv tool install .
gimme-the-diagram
```

---

## Dev commands

### Run with Textual dev console (for debugging)

```bash
textual console [-v|-x]
textual run src/gimme_the_diagram/main.py --dev
```

### Linting & type checking

```bash
uv run pre-commit run --all-files
uv run mypy .
```

### Tests with coverage

```bash
uv run pytest
```

---
