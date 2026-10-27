"""Pictures of the pets, drawn off screen with Qt: `agentpet sheet` (every reaction of both pets),
the app icon, and the README's pictures and animations (see tools/readme_images.py). The
animations run the real pets (state, motion and looks) on a simulated clock."""

from __future__ import annotations

import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

from . import looks, sprites
from .frame import Frame
from .motion import Area
from .paint import draw_frame, draw_pet
from .pet import Pet, View

_KEEP = []


def _gui() -> None:
    """Qt needs an application object to draw text; off screen when there is no display."""
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _KEEP.append(QGuiApplication(["agentpet"]))


def canvas(w: int, h: int, colour: QColor | None = None) -> tuple[QImage, QPainter]:
    _gui()
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(colour or Qt.transparent)
    return img, QPainter(img)


def _label(p: QPainter, text: str, x: float, y: float, colour=QColor(60, 60, 70), size: int = 12, bold=False) -> None:
    f = QFont("sans")
    f.setPixelSize(size)
    f.setBold(bold)
    p.setFont(f)
    p.setPen(colour)
    p.drawText(QPointF(x, y), text)


def icon(path: str) -> None:
    img, p = canvas(128, 128)
    draw_frame(p, Frame(sprites.hermes()), 76, 112, 4)
    draw_frame(p, Frame(sprites.clawd()), 34, 124, 3)
    p.end()
    img.save(path)


SHEET = ("idle", "walk", "thinking", "working", "needs_you", "urgent", "thanks", "oops", "helper", "done",
         "flip", "rare", "failed", "compact", "sleeping", "poke", "held", "falling", "bonk", "dizzy", "land",
         "wall-left", "ceiling", "wall-right")
_TURNS = {"wall-left": "cw", "ceiling": "flip", "wall-right": "ccw"}


def _sheet_view(pet: Pet, st: str) -> tuple[View, str]:
    real = {"walk": "idle", "urgent": "needs_you"}.get(st, "idle" if st in _TURNS else st)
    age = {"rare": 0.5 if pet.kind == "clawd" else 0.6, "done": 0.5, "flip": 0.3, "thanks": 0.5, "bonk": 0.2}.get(st, 0.7)
    turn = _TURNS.get(st, "")
    return View(pet.kind, real, age, st == "walk" or st in _TURNS, 1, 3, pet.bubble(real, st == "urgent"),
                st == "urgent", turn), turn


def sheet(path: str, states=SHEET, cols: int = 8, px: int = 4, kinds=("clawd", "hermes")) -> None:
    """Every reaction of both pets, one cell each, with the floor (or wall, or top) it is on."""
    cw, ch = 230, 190
    rows = -(-len(states) // cols)
    img, p = canvas(cw * cols, ch * rows * len(kinds), QColor(232, 233, 238))
    for band, kind in enumerate(kinds):
        pet = Pet(kind)
        pet.tool, pet.app, pet.where = "Bash", "Ptyxis", "~/projects/webapp"
        pet.poke_text = pet.label()
        for col, st in enumerate(states):
            view, turn = _sheet_view(pet, st)
            x0, y0 = (col % cols) * cw, (band * rows + col // cols) * ch
            f = looks.frame(view, 0.3)
            bw, bh = (f.height, f.width) if turn in ("cw", "ccw") else (f.width, f.height)
            cx = {"cw": x0 + 10 + bw * px / 2, "ccw": x0 + cw - 10 - bw * px / 2}.get(turn, x0 + cw / 2)
            cy = y0 + 40 + bh * px / 2 if turn == "flip" else y0 + ch - 26 - bh * px / 2
            edge = {"cw": (x0 + 10, y0 + 8, 1, ch - 34), "ccw": (x0 + cw - 11, y0 + 8, 1, ch - 34),
                    "flip": (x0 + 8, y0 + 40, cw - 16, 1)}.get(turn, (x0 + 8, y0 + ch - 26, cw - 16, 1))
            p.fillRect(QRectF(*edge), QColor(150, 150, 165))
            draw_pet(p, f, turn, cx, cy, px, (x0, x0 + cw))
            _label(p, st.replace("_", " "), x0 + 14, y0 + ch - 8)
    p.end()
    img.save(path)


# ---------------------------------------------------------------- the README

def _desktop(p: QPainter, w: int, h: int, bar: int) -> None:
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor(28, 33, 48))
    g.setColorAt(1, QColor(52, 60, 86))
    p.fillRect(QRectF(0, 0, w, h), g)
    p.fillRect(QRectF(0, h - bar, w, bar), QColor(16, 18, 24))
    for i in range(5):
        p.fillRect(QRectF(w / 2 - 70 + i * 30, h - bar + 6, 20, bar - 12), QColor(70, 76, 96))


def _terminal(p: QPainter, x: float, y: float, w: float, h: float, title: str, lines) -> None:
    p.fillRect(QRectF(x, y, w, h), QColor(20, 22, 28))
    p.fillRect(QRectF(x, y, w, 26), QColor(44, 48, 60))
    for i, c in enumerate((QColor(237, 106, 94), QColor(245, 191, 79), QColor(98, 197, 84))):
        p.fillRect(QRectF(x + 10 + i * 16, y + 9, 9, 9), c)
    _label(p, title, x + 66, y + 18, QColor(200, 204, 214), 12)
    f = QFont("monospace")
    f.setStyleHint(QFont.Monospace)
    f.setPixelSize(12)
    p.setFont(f)
    for i, (text, colour) in enumerate(lines):
        p.setPen(QColor(*colour))
        p.drawText(QPointF(x + 12, y + 48 + i * 18), text)


def hero(path: str) -> None:
    """A desktop with both pets out: Clawd busy, Hermes waiting for you, more Clawds about."""
    W, H, bar, px = 1100, 470, 34, 4
    img, p = canvas(W, H)
    _desktop(p, W, H, bar)
    _terminal(p, 70, 60, 430, 200, "claude — ~/projects/webapp", [
        ("> add dark mode to the settings page", (215, 119, 87)),
        ("● Reading src/settings.tsx", (170, 176, 190)),
        ("● Editing src/theme.ts", (170, 176, 190)),
        ("  +  export const dark = {", (98, 197, 84)),
        ("  +    background: '#1e1e24',", (98, 197, 84)),
        ("● Running npm test", (170, 176, 190))])
    _terminal(p, 600, 90, 430, 170, "hermes — ~/research", [
        ("> summarise the new papers on RL", (120, 130, 255)),
        ("● web_search  reinforcement learning 2026", (170, 176, 190)),
        ("⚠ Allow terminal: rm -rf ./cache ?", (245, 191, 79)),
        ("  [o]nce  [s]ession  [a]lways  [d]eny", (170, 176, 190))])
    floor = H - bar

    def put(kind, state, x, y, turn="", age=0.7, facing=1, bubble=None, urgent=False):
        v = View(kind, state, age, False, facing, 3, bubble, urgent, turn)
        f = looks.frame(v, 0.3)
        draw_pet(p, f, turn, x, y, px, (0, W))

    put("clawd", "working", 300, floor - sprites.CLAWD_H * px / 2, bubble="Editing code…")
    put("hermes", "needs_you", 820, floor - sprites.HERMES_H * px / 2, age=0.2, bubble="Needs you!")
    put("clawd", "idle", W - sprites.CLAWD_H * px / 2, 300, turn="ccw")
    put("clawd", "sleeping", 560, sprites.CLAWD_H * px / 2, turn="flip", age=0)
    p.end()
    img.save(path)


class Movie:
    """Frames of the real pets on a simulated clock, for an animation."""

    def __init__(self, w: int, h: int, px: int = 3, bar: int = 20) -> None:
        self.w, self.h, self.px, self.bar = w, h, px, bar
        self.area = Area(0, 0, w, h - bar)
        self.t = 0.0
        self.pets: list[Pet] = []
        self.frames: list[QImage] = []

    def add(self, kind: str, x: float, seed: int = 1) -> Pet:
        pet = Pet(kind, random.Random(seed), rare_chance=0)
        pet.handle("SessionStart", self.t, f"movie-{len(self.pets)}", app="Terminal", where="~/projects/webapp")
        w, h = self._size(kind)
        pet.motion.place(self.area, w, h, x)
        pet.short = None
        self.pets.append(pet)
        return pet

    def _size(self, kind: str) -> tuple[float, float]:
        return ((sprites.CLAWD_W, sprites.CLAWD_H) if kind == "clawd" else (sprites.HERMES_W, sprites.HERMES_H))[0] * self.px, \
            ((sprites.CLAWD_W, sprites.CLAWD_H) if kind == "clawd" else (sprites.HERMES_W, sprites.HERMES_H))[1] * self.px

    def run(self, seconds: float, record: bool = True, dt: float = 0.08) -> None:
        end = self.t + seconds
        while self.t < end - 1e-9:
            self.t += dt
            for pet in self.pets:
                w, h = self._size(pet.kind)
                pet.update(self.t, dt, self.area, w, h, (9.0 if pet.kind == "clawd" else 7.0) * self.px)
            if record:
                self.frames.append(self.snapshot())

    def snapshot(self) -> QImage:
        img, p = canvas(self.w, self.h)
        _desktop(p, self.w, self.h, self.bar)
        for pet in self.pets:
            if pet.state(self.t) == "hidden":
                continue
            view = pet.view(self.t, step_px=self.px)
            draw_pet(p, looks.frame(view, self.t), view.turn, pet.x, pet.y, self.px, (0, self.w))
        p.end()
        return img
