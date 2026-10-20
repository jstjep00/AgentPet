"""config.json in the config folder (see places): {"pixel": 4}, the screen pixels per sprite pixel (2-8)."""

from __future__ import annotations

import json
from pathlib import Path

from . import places

DEFAULTS = {"pixel": 4}
SIZES = {"small": 3, "normal": 4, "large": 5, "huge": 6}


def path() -> Path:
    return places.config_dir() / "config.json"


def load() -> dict:
    out = dict(DEFAULTS)
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict) and isinstance(data.get("pixel"), int) and 2 <= data["pixel"] <= 8:
        out["pixel"] = data["pixel"]
    return out


def save(values: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**load(), **values}, indent=2) + "\n", encoding="utf-8")
