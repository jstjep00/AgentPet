"""Where a pet is and how it gets around: along the floor (where it likes to be), up the side walls,
upside down along the top, through the air when it lets go or is dropped, and in your hand while
you drag it. Pure: positions are logical screen pixels, the clock is passed in.

A pet's position is its centre. On a surface it is kept as `s`, the distance along that surface
(x on the floor and the ceiling, y on a wall); on a wall the sprite lies on its side, feet to the
wall, so it is as wide as the sprite is tall.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

FLOOR, LEFT, RIGHT, CEILING, AIR, HELD = "floor", "left", "right", "ceiling", "air", "held"

GRAVITY = 2400.0         # px/s²
MAX_FALL = 1500.0        # px/s
CLIMB = 0.7              # climbing speed, as a share of walking speed
HURRY = 1.5              # off on an adventure (to a wall, up it, along the top), it hurries
DEMO_HURRY = 2.5         # ... and in the demo climb, more so
ADVENTURE = 0.2          # an idle pet picking its next spot heads for a wall this often
TO_CEILING = 0.55        # ... and from the wall carries on over the top this often
LET_GO = 0.45            # a pet on the ceiling drops instead of climbing back down this often
EDGE_SNAP = 32.0         # dropped this close to a screen edge, a pet holds on there
BONK_FALL = 0.45         # a fall longer than this share of the screen ends on its head
BONK_S, DIZZY_S, LAND_S = 0.5, 2.4, 0.3


@dataclass
class Area:
    """The screen minus panels and docks, as edges."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def of(cls, x: float, y: float, w: float, h: float) -> "Area":
        return cls(x, y, x + w, y + h)


class Motion:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.surface = FLOOR
        self.s: float | None = None
        self.x = self.y = 0.0
        self.vy = 0.0
        self.target: float | None = None
        self.goal: str | None = None     # floor: "wall"; wall: "up", "ceiling", "down"; ceiling: "end", "fall"
        self.side = LEFT
        self.force = False               # a demo climb: all the way over the top, then let go
        self.pause_until = 0.0
        self.facing = 1                  # in the sprite's own frame: 1 is its right
        self.walking = False
        self.travel = 0.0
        self.fall_from = 0.0
        self.soft = False                # a deliberate hop down lands on its feet
        self.landing: tuple[str, float] | None = None     # ("bonk" | "land", when)

    # -- geometry ------------------------------------------------------------------------
    @staticmethod
    def limits(surface: str, area: Area, w: float, h: float) -> tuple[float, float]:
        if surface in (FLOOR, CEILING):
            lo, hi = area.left + w / 2, area.right - w / 2
        else:
            lo, hi = area.top + w / 2, area.bottom - w / 2
        return (lo, hi) if hi >= lo else ((lo + hi) / 2,) * 2

    @staticmethod
    def centre(surface: str, s: float, area: Area, w: float, h: float) -> tuple[float, float]:
        if surface == FLOOR:
            return s, area.bottom - h / 2
        if surface == CEILING:
            return s, area.top + h / 2
        if surface == LEFT:
            return area.left + h / 2, s
        return area.right - h / 2, s

    @property
    def turn(self) -> str:
        """How the sprite is turned: "" upright, "cw" feet to the left wall, "ccw" feet to the
        right wall, "flip" upside down."""
        return {LEFT: "cw", RIGHT: "ccw", CEILING: "flip"}.get(self.surface, "")

    def _sync(self, area: Area, w: float, h: float) -> None:
        if self.surface not in (AIR, HELD) and self.s is not None:
            self.x, self.y = self.centre(self.surface, self.s, area, w, h)

    def _go(self, surface: str, s: float, area: Area, w: float, h: float) -> None:
        self.surface = surface
        lo, hi = self.limits(surface, area, w, h)
        self.s = min(max(s, lo), hi)
        self._sync(area, w, h)

    def place(self, area: Area, w: float, h: float, x: float | None = None) -> None:
        lo, hi = self.limits(FLOOR, area, w, h)
        self._go(FLOOR, self.rng.uniform(lo, hi) if x is None else x, area, w, h)

    def landed(self, now: float) -> str | None:
        """"bonk" (on its head), then "dizzy"; or "land" after a short hop; else None."""
        if not self.landing:
            return None
        kind, t = self.landing
        age = now - t
        if kind == "bonk":
            return "bonk" if age < BONK_S else "dizzy" if age < BONK_S + DIZZY_S else None
        return "land" if age < LAND_S else None

    def landed_age(self, now: float) -> float:
        if not self.landing:
            return 0.0
        age = now - self.landing[1]
        return age - BONK_S if self.landed(now) == "dizzy" else age

    # -- you and the pet -----------------------------------------------------------------
    def pick_up(self) -> None:
        self.surface = HELD
        self.target = self.goal = None
        self.walking = self.force = False
        self.landing = None

    def hold_at(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def drop(self, now: float, area: Area, w: float, h: float) -> None:
        """Let go of a held pet: it holds on to the edge it was dropped at, else falls."""
        x, y, reach = self.x, self.y, max(w, h) / 2
        self.pause_until = now + self.rng.uniform(1.5, 3.0)
        if x - reach - area.left < EDGE_SNAP:
            self._go(LEFT, y, area, w, h)
        elif area.right - (x + reach) < EDGE_SNAP:
            self._go(RIGHT, y, area, w, h)
        elif y - reach - area.top < EDGE_SNAP:
            self._go(CEILING, x, area, w, h)
        elif y >= area.bottom - h / 2 - 2:
            self._go(FLOOR, x, area, w, h)
        else:
            self.let_go(soft=False)

    def let_go(self, soft: bool) -> None:
        self.surface = AIR
        self.vy = 0.0
        self.fall_from = self.y
        self.soft = soft
        self.target = self.goal = None
        self.walking = False

    def adventure(self, now: float) -> None:
        """Off to the wall right now, over the top, and down the quick way (the demo)."""
        self.force = True
        self.pause_until = now
        self.target = None
        self.landing = None
        if self.surface == FLOOR:
            self.goal = None

    # -- time ----------------------------------------------------------------------------
    def step(self, now: float, dt: float, area: Area, w: float, h: float, speed: float, mode: str = "roam") -> None:
        """mode: "roam" (idle: wander, sometimes climb), "stay" (keep still) or "ground" (get
        down to the floor and stand there)."""
        if self.surface == HELD:
            self.walking = False
            return
        if self.surface == AIR:
            self._fall(now, dt, area, w, h)
            return
        if self.s is None:
            self.place(area, w, h)
        lo, hi = self.limits(self.surface, area, w, h)
        self.s = min(max(self.s, lo), hi)
        if mode == "ground" and self.surface != FLOOR:
            self.let_go(soft=True)
            self._fall(now, dt, area, w, h)
            return
        if mode != "roam" or (self.target is None and now < self.pause_until):
            self.walking = False
            if mode == "ground":
                self.target = self.goal = None
            self._sync(area, w, h)
            return
        if self.target is None:
            self._decide(area, w, h, lo, hi)
            if self.surface == AIR:
                self._fall(now, dt, area, w, h)
                return
        hurry = DEMO_HURRY if self.force else HURRY if self.goal or self.surface != FLOOR else 1.0
        step = speed * hurry * (CLIMB if self.surface in (LEFT, RIGHT) else 1.0) * dt
        delta = self.target - self.s
        if abs(delta) <= step:
            self.s = self.target
            self.target = None
            self.walking = False
            self._arrive(now, area, w, h)
        else:
            d = 1 if delta > 0 else -1
            self.s += step * d
            self.travel += step
            self.walking = True
            # on the right wall the sprite's right points up the wall; elsewhere along +s
            self.facing = -d if self.surface == RIGHT else d
        self._sync(area, w, h)

    def _decide(self, area: Area, w: float, h: float, lo: float, hi: float) -> None:
        """Picks where to go next, once a pause is over."""
        r = self.rng.random
        if self.surface == FLOOR:
            if self.force or r() < ADVENTURE:
                near_left = (self.s - lo) <= (hi - self.s)
                self.side = LEFT if (near_left if r() < 0.75 else not near_left) else RIGHT
                self.goal, self.target = "wall", lo if self.side == LEFT else hi
            else:
                self.goal, self.target = None, self.rng.uniform(lo, hi)
        elif self.surface in (LEFT, RIGHT):
            if self.goal not in ("ceiling", "down"):
                self.goal = "ceiling" if r() < 0.5 else "down"
            self.target = lo if self.goal == "ceiling" else hi
        else:  # ceiling
            if self.goal == "fall" or (self.goal is None and r() < LET_GO * 0.5):
                self.let_go(soft=False)
                return
            if self.goal == "end":
                self.side = LEFT if (self.s - lo) <= (hi - self.s) else RIGHT
                self.target = lo if self.side == LEFT else hi
            else:
                self.target = self.rng.uniform(lo, hi)

    def _arrive(self, now: float, area: Area, w: float, h: float) -> None:
        """Reached the target: turn a corner, or rest a moment."""
        r = self.rng.random
        if self.surface == FLOOR:
            if self.goal == "wall":
                over = self.force or r() < TO_CEILING
                self.goal = "ceiling" if over else "up"
                lo, hi = self.limits(self.side, area, w, h)
                self._go(self.side, hi, area, w, h)
                self.target = lo if over else self.rng.uniform(lo, lo + (hi - lo) * 0.6)
                return
            self.goal = None
            self.pause_until = now + self.rng.uniform(2.0, 7.0)
        elif self.surface in (LEFT, RIGHT):
            lo, hi = self.limits(self.surface, area, w, h)
            if self.goal == "ceiling" and self.s <= lo + 0.5:
                clo, chi = self.limits(CEILING, area, w, h)
                self._go(CEILING, clo if self.surface == LEFT else chi, area, w, h)
                self.goal = "fall" if self.force else None
                self.target = self.rng.uniform(clo, chi)
            elif self.goal == "down" and self.s >= hi - 0.5:
                flo, fhi = self.limits(FLOOR, area, w, h)
                self._go(FLOOR, flo if self.surface == LEFT else fhi, area, w, h)
                self.goal = None
                self.pause_until = now + self.rng.uniform(1.0, 3.0)
            else:
                self.goal = "down"
                self.pause_until = now + self.rng.uniform(1.5, 4.0)
        else:  # ceiling
            if self.goal == "end":
                lo, hi = self.limits(self.side, area, w, h)
                self._go(self.side, lo, area, w, h)
                self.goal, self.target = "down", hi
                return
            if self.goal != "fall":
                self.goal = "fall" if r() < LET_GO else "end"
            self.pause_until = now + self.rng.uniform(1.5, 4.0)

    def _fall(self, now: float, dt: float, area: Area, w: float, h: float) -> None:
        self.walking = False
        self.vy = min(self.vy + GRAVITY * dt, MAX_FALL)
        self.y += self.vy * dt
        self.x = min(max(self.x, area.left + w / 2), area.right - w / 2)
        floor_y = area.bottom - h / 2
        if self.y < floor_y:
            return
        drop = floor_y - self.fall_from
        kind = "bonk" if not self.soft and drop > BONK_FALL * (area.bottom - area.top) else "land"
        self._go(FLOOR, self.x, area, w, h)
        self.vy = 0.0
        self.landing = (kind, now)
        self.pause_until = now + (BONK_S + DIZZY_S if kind == "bonk" else LAND_S) + self.rng.uniform(0.5, 2.0)
        self.target = self.goal = None
        self.force = self.soft = False
