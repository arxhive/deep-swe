"""Small filesystem helpers for writing run artifacts (JSON and text)."""

import json
from pathlib import Path


def write_json_file(path: Path, data: dict) -> None:
    """Write ``data`` as pretty-printed UTF-8 JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text_file(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` as UTF-8, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
