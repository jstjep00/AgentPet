"""Pixel sprites for the two pets and their effects. No GTK, no cairo: a sprite is a tuple of equal
length strings, one character per pixel ('.' is transparent, every other character is a PALETTE
key), so poses can be built, compared and tested as plain text.

Clawd is decoded from the block-glyph sprite Claude Code draws in the terminal (2.1.x): every
glyph is one terminal cell of 2 x 2 quadrants, and a quadrant is one pixel wide and two tall,
because a terminal cell is about twice as tall as it is wide. Hermes is drawn here by hand at the
same pixel size, after the girl in Nous Research's Hermes Agent portal art.
"""

from __future__ import annotations

import math
import random

PALETTE = {
    "#": (215, 119, 87),    # Clawd: Claude Code's clawd_body
    "k": (0, 0, 0),         # Clawd's eyes: the terminal background showing through
    "B": (0, 0, 242),       # Hermes: the blue of the Nous art
    "W": (242, 242, 242),   # Hermes: its paper white
    "L": (150, 150, 255),   # Hermes: light blue (headphone ring, blush, orb)
    "R": (232, 72, 100),    # heart
    "Y": (255, 204, 0),     # "!" badge
    "G": (150, 150, 165),   # thought dots
    "w": (226, 226, 234),   # poof cloud
    "S": (255, 226, 110),   # sparkles
    "Z": (120, 130, 200),   # sleep Zs
    "s": (120, 190, 255),   # sweat drop
}

CONFETTI = ("R", "Y", "S", "L", "#", "s")


def blank(w: int, h: int) -> list[list[str]]:
    return [["."] * w for _ in range(h)]


def freeze(g: list[list[str]]) -> tuple[str, ...]:
    return tuple("".join(row) for row in g)


def mirror(sprite: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(row[::-1] for row in sprite)


def flip(sprite: tuple[str, ...]) -> tuple[str, ...]:
    """Upside down."""
    return tuple(reversed(sprite))


def rotate(sprite: tuple[str, ...], quarters: int) -> tuple[str, ...]:
    """Turned clockwise by that many quarter turns (negative is anticlockwise)."""
    for _ in range(quarters % 4):
        sprite = tuple("".join(row[x] for row in reversed(sprite)) for x in range(len(sprite[0])))
    return sprite


def stamp(g: list[list[str]], x: int, y: int, bitmap) -> None:
    """Copies the bitmap's opaque pixels into g with its top-left at (x, y), clipped to g."""
    for dy, row in enumerate(bitmap):
        for dx, ch in enumerate(row):
            if ch != "." and 0 <= y + dy < len(g) and 0 <= x + dx < len(g[0]):
                g[y + dy][x + dx] = ch


# ---------------------------------------------------------------- Clawd

# quadrant bits: upper-left 8, upper-right 4, lower-left 2, lower-right 1
_QUADRANTS = {" ": 0b0000, "█": 0b1111, "▀": 0b1100, "▄": 0b0011, "▌": 0b1010, "▐": 0b0101,
              "▘": 0b1000, "▝": 0b0100, "▖": 0b0010, "▗": 0b0001, "▛": 0b1110, "▜": 0b1101,
              "▙": 0b1011, "▟": 0b0111, "▚": 0b1001, "▞": 0b0110}
LID = "▂"                     # a closed eye: a body cell whose bottom pixel row is dark
CLAWD_W, CLAWD_H = 18, 10     # 9 cells x 3 rows; the feet use only the third row's upper half
_FACE_ROWS = 8                # rows where a gap inside the body is an eye, not background

# The parts Claude Code composes Clawd from: arms (row 1 left/right, row 2 left/right), eyes
# (the middle of row 1) and feet (row 3). The middle of row 2 is always five full blocks.
ARMS = {"down": (" ▐", "", "▝▜", "█▀"), "up": ("▗▟", "▄", " ▜", "█▘"), "one-up": (" ▐", "▄", "▝▜", "█▘")}
EYES = {"open": "▛███▛█", "left": "▟███▟█", "right": "█▟███▟", "up": "▙███▙█",
        "closed": LID + "███" + LID + "█", "wink": "▛███" + LID + "█"}
FEET = {"both": " ▝▝   ▝▝ ", "left": " ▝▝      ", "right": "      ▝▝ "}

# Claude Code's turn-around frames, as it draws them.
TURN = {
    "right-12": (" ▐█▜██▛█ ", "▝▜██████▀", " ▝▝   ▝▝ "),
    "right-30": ("  █▛██▛▌ ", " ▝█████▛ ", "  ▘▘  ▘▘ "),
    "right-55": ("  ▐█▛█▜  ", "  ▐████  ", "  ▝▝ ▝▝  "),
    "right-75": ("   ██▛▌  ", "   ███▌  ", "   ▘  ▘  "),
    "edge":     ("   ▐██   ", "   ▐██   ", "   ▝ ▝   "),
    "back-105": ("   ███▌  ", "   ███▌  ", "   ▘  ▘  "),
    "back-125": ("  ▐████  ", "  ▐████  ", "  ▝▝ ▝▝  "),
    "back-150": ("  █████▌ ", " ▝█████▛ ", "  ▘▘  ▘▘ "),
    "back":     (" ▐██████ ", "▝▜██████▀", " ▝▝   ▝▝ "),
    "left-75":  ("   ▛██▌  ", "   ███▌  ", "   ▘  ▘  "),
    "left-55":  ("  ▐▜▛██  ", "  ▐████  ", "  ▝▝ ▝▝  "),
    "left-30":  ("  ▛██▛█▌ ", " ▝█████▛ ", "  ▘▘  ▘▘ "),
    "left-12":  (" ▐▛███▜█ ", "▝▜██████▀", " ▝▝   ▝▝ "),
}
# A full turn: Claude Code has the right side and the front-left; the back-left is the back-right
# mirrored ("~").
SPIN = ("front", "right-12", "right-30", "right-55", "right-75", "edge", "back-105", "back-125",
        "back-150", "back", "~back-150", "~back-125", "~back-105", "~edge", "left-75", "left-55",
        "left-30", "left-12", "front")


def decode(rows) -> tuple[str, ...]:
    """Three rows of up to 9 block glyphs -> an 18 x 10 sprite ('#' body, 'k' eyes)."""
    g = blank(CLAWD_W, CLAWD_H)
    for gr, text in enumerate(rows):
        for gc, ch in enumerate(text.ljust(9)[:9]):
            x0, y0 = gc * 2, gr * 4
            if ch == LID:
                for y in range(y0, y0 + 4):
                    g[y][x0] = g[y][x0 + 1] = "#"
                g[y0 + 3][x0] = g[y0 + 3][x0 + 1] = "k"
                continue
            bits = _QUADRANTS[ch]
            for i, (qx, qy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                if bits & (8 >> i):
                    for y in (y0 + qy * 2, y0 + qy * 2 + 1):
                        if y >= CLAWD_H:
                            raise ValueError(f"glyph {ch!r} reaches below the feet row")
                        g[y][x0 + qx] = "#"
    for y in range(_FACE_ROWS):
        filled = [x for x in range(CLAWD_W) if g[y][x] != "."]
        for x in range(filled[0], filled[-1] + 1) if filled else ():
            if g[y][x] == ".":
                g[y][x] = "k"
    return freeze(g)


def clawd(eyes: str = "open", arms: str = "down", feet: str = "both") -> tuple[str, ...]:
    a = ARMS[arms]
    return decode((a[0] + EYES[eyes] + a[1], a[2] + "█████" + a[3], FEET[feet]))


def clawd_turn(name: str) -> tuple[str, ...]:
    if name == "front":
        return clawd()
    if name.startswith("~"):
        return mirror(clawd_turn(name[1:]))
    return decode(TURN[name])


# ---------------------------------------------------------------- Hermes

HERMES_W, HERMES_H = 22, 21

# Head (rows 0-12) and body (13-17), facing right; arms, legs, headphones and the orb are added
# by hermes() so they can move.
_HEAD = (
    "......BBBBBB..........",
    "....BBBBBBBBBB........",
    "...BBBBBBBBBBBB.......",
    "..BBBBBBBBBBBBBB......",
    "..BBBBBBBBBBBBBB......",
    ".BBBBBBBBBBBBBBB......",
    ".BBBBBWWBWWBWBBB......",
    ".BBBBWWWWWWWWWBB......",
    ".BBBBWWBBWWBBWBB......",
    ".BBBBWLWWWWWLWBB......",
    ".BBBBBWWWWBWWBBB......",
    ".BBBBBBBBBBBBBBB......",
    ".B.B....BWWB.B.B......",
)
_BODY = (
    ".....BWWWLLWB.........",
    "....BWWWWWWWWB........",
    "....BWWWWWWWWB........",
    "....BWWWWWWWWB........",
    "....BBBBBBBBBB........",
)
_CUP = (".BBB.", "BLLLB", "BLBLB", "BLLLB", ".BBB.")
_BAND = ((2, 5), (2, 4), (3, 3), (4, 2), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1), (10, 1), (11, 1), (12, 2), (13, 3))
_ORB = (".BBB.", "BWLWB", "BLWWB", "BWWLB", ".BBB.")
_ORB_TURNS = (("WLW", "LWW", "WWL"), ("LWW", "WWL", "WLW"), ("WWL", "WLW", "LWW"))


def orb(phase: int = 0, glow: bool = False) -> tuple[str, ...]:
    """The orb, 5 x 5; `phase` turns its markings, `glow` lights it up."""
    inside = _ORB_TURNS[phase % 3]
    if glow:
        inside = tuple(r.replace("W", "L") if i != 1 else "LWL" for i, r in enumerate(inside))
    return (".BBB.",) + tuple("B" + r + "B" for r in inside) + (".BBB.",)


def hermes(eyes: str = "closed", arm: str = "hold", legs: str = "both", back_arm: int = 0,
           bow: int = 0, orb_dy: int = 0, orb_phase: int = 0, glow: bool = False,
           with_orb: bool = True) -> tuple[str, ...]:
    """Hermes facing right.

    eyes: closed (calm, downcast), open (surprised); arm: hold (palm up under the orb), up and
    wave (raised, two frames), down; legs: both, left or right (that leg lifted); back_arm: 0/1
    (swing); bow: 0/1 (head lowered a pixel); orb_dy: the orb's float offset."""
    g = blank(HERMES_W, HERMES_H)
    # legs and shoes; a lifted leg is one pixel shorter
    for name, x in (("left", 6), ("right", 10)):
        lift = 1 if legs == name else 0
        stamp(g, x, 18 - lift, ("BB", "BB", "BBB"))
    stamp(g, 0, 13, _BODY)
    # back arm, swinging a pixel
    stamp(g, 2, 13 + back_arm, (".B", "BW", "BW", ".B"))
    stamp(g, 0, bow, _HEAD)
    stamp(g, 0, 6 + bow, _CUP)
    for x, y in _BAND:
        g[y + bow][x] = "L"
    if eyes == "open":
        for x in (7, 8, 11, 12):
            g[8 + bow][x] = "W"
        for x in (8, 11):
            g[7 + bow][x] = g[8 + bow][x] = "B"
    # front arm
    if arm == "hold":
        stamp(g, 13, 12, ("....B", ".BBBWB", "BWWWWB", ".BBBBB"))
    elif arm in ("up", "wave"):
        dx = 1 if arm == "wave" else 0
        stamp(g, 15 + dx, 7, (".B.", "BWB", "BWB", "BWB"))
        stamp(g, 14, 11, ("BWB" if dx == 0 else "BWWB", "BWB", ".BWB"))
    else:  # down
        stamp(g, 13, 13, ("BB", "WB", "WB", "BB"))
    if with_orb:
        oy = 8 + orb_dy if arm == "hold" else 9 + orb_dy
        stamp(g, 16 if arm == "hold" else 17, oy, orb(orb_phase, glow))
    return freeze(g)


# ---------------------------------------------------------------- effects

HEART = (".RR.RR.", "RRRRRRR", "RRRRRRR", ".RRRRR.", "..RRR..", "...R...")
BANG = (".kkk.", ".kYk.", ".kYk.", ".kYk.", ".kkk.", ".kYk.", ".kkk.")
ZED = ("ZZZZ", "..Z.", ".Z..", "ZZZZ")
SWEAT = (".s", "ss", "ss")
SPARKLE = (".S.", "SSS", ".S.")
DUST = (".GG.", "GwwG", ".GG.")
POOF = ("..GGG.GGG..", ".GwwwGwwwG.", "GwwwwwwwwwG", ".GwwwwwwwG.", "..GGGGGGG..")


def confetti(t: float, w: int, seed: int = 7, count: int = 26) -> list[tuple[int, int, str]]:
    """Confetti `t` seconds after it burst from a sprite `w` pixels wide: (x, y, colour) in
    sprite pixels, y up from the sprite's top (negative is above it). Pure: the same t, same
    picture."""
    rnd = random.Random(seed)
    out = []
    for _ in range(count):
        vx = rnd.uniform(-9, 9)
        vy = rnd.uniform(-26, -14)
        colour = rnd.choice(CONFETTI)
        delay = rnd.uniform(0, 0.25)
        s = t - delay
        if s < 0:
            continue
        x = w / 2 + vx * s
        y = vy * s + 16 * s * s
        out.append((int(round(x)), int(round(y)), colour))
    return out


def sparkles(t: float, cx: float, cy: float, count: int = 6) -> list[tuple[int, int]]:
    """Sparkles flying out of a point: (x, y) of each sparkle's centre, in sprite pixels."""
    out = []
    for i in range(count):
        a = i * 2 * math.pi / count + 0.4
        r = 2 + t * 14
        out.append((int(round(cx + math.cos(a) * r)), int(round(cy + math.sin(a) * r * 0.8))))
    return out
