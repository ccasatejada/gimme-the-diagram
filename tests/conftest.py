from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import gimme_the_diagram.schema.layout as layout_module
from gimme_the_diagram.model.model import Base


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


@pytest.fixture
def mock_session():
    """Provides a MagicMock pretending to be a SQLAlchemy Session."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_get_session(mock_session):
    """Returns a context-manager factory that yields mock_session."""

    @contextmanager
    def _get_session():
        yield mock_session

    return _get_session


@pytest.fixture
def in_memory_session():
    """Provides a real SQLite in-memory session with tables created."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
