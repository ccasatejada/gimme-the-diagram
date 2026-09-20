from pathlib import Path

import pytest

import gimme_the_diagram.schema.layout as layout_module


@pytest.fixture(autouse=True)
def isolated_layout_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never let tests read/write the user's real layout sidecar directory.

    Without this, tests that hash the same DDL text to the same sidecar filename
    (e.g. repeated sample schemas across test files) leak state into each other via
    ~/.local/share/gimme-the-diagram/layouts/, and pollute that real directory too.
    """
    layout_dir = tmp_path / "layouts"
    monkeypatch.setattr(layout_module, "LAYOUT_DIR", layout_dir)
    return layout_dir
