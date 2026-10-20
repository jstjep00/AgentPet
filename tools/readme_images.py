"""Draws the README's pictures into docs/: run from the repository with Pillow installed.

    python tools/readme_images.py

The animations are the real pets (their state, movement and looks) on a simulated clock.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from agentpet import pictures  # noqa: E402
from agentpet.pet import Pet  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"


def pil(img: QImage) -> Image.Image:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    data = bytes(img.constBits())
    return Image.frombuffer("RGBA", (img.width(), img.height()), data, "raw", "RGBA", img.bytesPerLine(), 1).convert("RGB")


def gif(path: Path, frames: list[QImage], every: int = 1) -> None:
    images = [pil(f) for f in frames[::every]]
    images[0].save(path, save_all=True, append_images=images[1:], duration=80 * every, loop=0, optimize=True)
    print(f"{path.name}: {len(images)} frames, {path.stat().st_size // 1024} KB")


def climb() -> None:
    """Up the wall, along the top, a fall onto its head, dizzy; Hermes does the same."""
    m = pictures.Movie(640, 340, px=3)
    clawd = m.add("clawd", 150, seed=5)
    hermes = m.add("hermes", 480, seed=8)
    m.run(1.0)
    clawd.motion.adventure(m.t)
    m.run(2.5)
    hermes.motion.adventure(m.t)
    m.run(26)
    gif(DOCS / "climb.gif", m.frames)


def reactions() -> None:
    """Both pets through a turn of their agents, each on its own: thinking, working, needing you,
    thanks, done; then the rare surprise."""
    m = pictures.Movie(640, 250, px=4)
    clawd = m.add("clawd", 190)
    hermes = m.add("hermes", 450)
    for pet in (clawd, hermes):
        pet.motion.pause_until = 1e9                  # stay put: this one is about faces, not walks

    def both(event_c, event_h=None, tool_c=None, tool_h=None, wait=2.4):
        if event_c:
            clawd.handle(event_c, m.t, "movie-0", tool_c)
        if event_h:
            hermes.handle(event_h, m.t, "movie-1", tool_h)
        m.run(wait)

    m.run(0.6)
    both("UserPromptSubmit", None, wait=1.4)
    both("PreToolUse", "UserPromptSubmit", "Bash")
    both("PermissionRequest", "PreToolUse", "Bash", "web_search", wait=3.0)
    both("PostToolUse", "PreToolUse", None, "terminal", wait=2.0)
    both("PreToolUse", "PermissionRequest", "Edit", "terminal", wait=2.4)
    both("Stop", "PostToolUse", wait=2.8)
    both(None, "Stop", wait=3.0)
    both("Rare", "Rare", wait=3.2)
    gif(DOCS / "reactions.gif", m.frames)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    pictures.hero(str(DOCS / "hero.png"))
    pictures.sheet(str(DOCS / "sheet.png"))
    pictures.icon(str(DOCS / "icon.png"))
    print("hero.png, sheet.png, icon.png")
    reactions()
    climb()


if __name__ == "__main__":
    main()
