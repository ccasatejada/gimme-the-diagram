from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


class GraphvizProcessError(RuntimeError):
    """Raised when the isolated Graphviz worker fails or times out."""


def run_graphviz_job(payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    """Run a PyGraphviz operation outside the UI process.

    Graphviz occasionally aborts at the C level for large orthogonal graphs. A child
    process turns that fatal abort into a normal error that callers can recover from.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "gimme_the_diagram.layout_engine.graphviz_worker"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GraphvizProcessError(f"Graphviz timed out after {timeout:g}s") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        message = detail[-1] if detail else f"exit code {completed.returncode}"
        raise GraphvizProcessError(f"Graphviz failed: {message}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GraphvizProcessError("Graphviz returned invalid output") from exc
    if not isinstance(result, dict):
        raise GraphvizProcessError("Graphviz returned an invalid result")
    return result
