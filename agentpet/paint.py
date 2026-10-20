"""Drawing a pet frame with Qt's QPainter: the sprite at a whole number of screen pixels per sprite
pixel, its effects, turned to lie on whatever surface the pet is on, and its speech bubble, which
always stays upright. The pet windows, `agentpet sheet` and the README pictures all use it."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter

from .frame import Frame, cells, pet_box
from .sprites import PALETTE

INK = QColor(31, 31, 38)
CATCH = QColor(0, 0, 0, 1)      # invisible, but on Windows and macOS it makes the pet clickable


def _colour(key: str) -> QColor:
    return QColor(*PALETTE[key])


def draw_pixels(p: QPainter, cells_, ox: float, oy: float, px: float) -> None:
    """cells: (x, y, key) in sprite pixels; later pixels win."""
    last: dict[tuple[int, int], str] = {}
    for x, y, key in cells_:
        last[(x, y)] = key
    for (x, y), key in last.items():
        p.fillRect(QRectF(ox + x * px, oy + y * px, px, px), _colour(key))


def draw_pet(p: QPainter, frame: Frame, turn: str, cx: float, cy: float, px: float,
             clamp: tuple[float, float] | None = None, catch: bool = False) -> tuple[int, int, int, int]:
    """Draws the frame centred on (cx, cy), lying as `turn` says; the bubble goes above it (below
    it when it hangs from the top), kept between clamp's x bounds. With `catch`, the sprite box is
    filled with an invisible colour so the whole pet takes clicks. Returns the sprite box."""
    pts, _, _ = cells(frame, turn)
    box = pet_box(frame, turn, cx, cy, px)
    ox, oy, bw, bh = box
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setOpacity(max(0.0, min(1.0, frame.alpha)))
    if catch:
        p.fillRect(QRectF(ox - px, oy - px, bw + 2 * px, bh + 2 * px), CATCH)
    draw_pixels(p, pts, ox, oy, px)
    if frame.bubble:
        ys = [y for _, y, _ in pts] + [0, int(bh // px) - 1]
        if turn == "flip":
            draw_bubble(p, frame.bubble, ox + bw / 2, oy + (max(ys) + 1) * px + 6, clamp, below=True)
        else:
            draw_bubble(p, frame.bubble, ox + bw / 2, oy + min(ys) * px - 6, clamp)
    p.restore()
    return box


def draw_frame(p: QPainter, frame: Frame, anchor_x: float, ground_y: float, px: float,
               area_w: float | None = None) -> None:
    """An upright pet standing with its feet on (anchor_x, ground_y)."""
    draw_pet(p, frame, "", anchor_x, ground_y - frame.height * px / 2, px,
             clamp=(0, area_w) if area_w is not None else None)


def bubble_font() -> QFont:
    f = QFont("monospace")
    f.setStyleHint(QFont.Monospace)
    f.setBold(True)
    f.setPixelSize(11)
    return f


def draw_bubble(p: QPainter, text: str, cx: float, y: float, clamp: tuple[float, float] | None = None,
                below: bool = False) -> None:
    """A square-cornered pixel-style speech bubble whose stepped tail points at (cx, y): down from
    above it, or up from below it."""
    font = bubble_font()
    fm = QFontMetricsF(font)
    pad, tail, border = 6, 5, 2
    bw, bh = round(fm.horizontalAdvance(text) + pad * 2), 22
    bx = round(cx - bw / 2)
    if clamp is not None:
        bx = max(int(clamp[0]) + border, min(bx, int(clamp[1] - bw - border)))
    by = round(y + tail) if below else round(y - tail - bh)
    tx = round(min(max(cx, bx + 8), bx + bw - 8))
    steps = ((by - 2, 8), (by - 4, 4)) if below else ((by + bh, 8), (by + bh + 2, 4))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.fillRect(QRectF(bx - border, by - border, bw + border * 2, bh + border * 2), INK)
    for sy, sw in steps:
        p.fillRect(QRectF(tx - sw / 2 - border, sy - (border if below else 0), sw + border * 2, 2 + border), INK)
    p.fillRect(QRectF(bx, by, bw, bh), Qt.white)
    for sy, sw in steps:
        p.fillRect(QRectF(tx - sw / 2, sy, sw, 2), Qt.white)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setFont(font)
    p.setPen(INK)
    p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, text)
    p.restore()
