"""A pet frame as data: the sprite, its effects and bubble, and how its pixels lie once the pet
is turned to stand on a wall or hang from the top. No drawing here (see paint)."""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class Frame:
    """What a pet looks like at one moment. Effect and confetti positions are in sprite pixels
    from the sprite's top-left corner (negative is above or left of it)."""

    sprite: tuple[str, ...]
    dy: int = 0                                         # hop: sprite pixels, negative is up
    dx: int = 0                                         # shake: sprite pixels
    effects: list = field(default_factory=list)         # (bitmap, x, y), drawn over the sprite
    under: list = field(default_factory=list)           # (bitmap, x, y), drawn behind it
    pixels: list = field(default_factory=list)          # (x, y, palette key): confetti
    bubble: str | None = None
    alpha: float = 1.0

    @property
    def width(self) -> int:
        return len(self.sprite[0])

    @property
    def height(self) -> int:
        return len(self.sprite)


# How a pixel at (x, y) of a w x h box moves when the box is turned (see motion.Motion.turn).
_TURNS = {
    "": lambda x, y, w, h: (x, y),
    "flip": lambda x, y, w, h: (x, h - 1 - y),
    "cw": lambda x, y, w, h: (h - 1 - y, x),
    "ccw": lambda x, y, w, h: (y, w - 1 - x),
}


def bitmap_cells(bitmap, x0: int = 0, y0: int = 0):
    for y, row in enumerate(bitmap):
        for x, ch in enumerate(row):
            if ch != ".":
                yield x0 + x, y0 + y, ch


def cells(frame: Frame, turn: str = "") -> tuple[list, int, int]:
    """Every coloured pixel of the frame, in the order drawn, turned; and the size of the turned
    sprite box (the hop and shake move the pixels, not the box)."""
    out = []
    for bitmap, ex, ey in frame.under:
        out.extend(bitmap_cells(bitmap, ex, ey))
    out.extend(bitmap_cells(frame.sprite))
    for bitmap, ex, ey in frame.effects:
        out.extend(bitmap_cells(bitmap, ex, ey))
    out.extend(frame.pixels)
    w, h = frame.width, frame.height
    f = _TURNS[turn]
    turned = [(*f(x + frame.dx, y + frame.dy, w, h), key) for x, y, key in out]
    return turned, (h if turn in ("cw", "ccw") else w), (w if turn in ("cw", "ccw") else h)


def pet_box(frame: Frame, turn: str, cx: float, cy: float, px: float) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the turned sprite box, centred on (cx, cy)."""
    w, h = frame.width, frame.height
    bw, bh = (h, w) if turn in ("cw", "ccw") else (w, h)
    return round(cx - bw * px / 2), round(cy - bh * px / 2), int(bw * px), int(bh * px)
