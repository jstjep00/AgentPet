"""How each pet shows each state: a View in, a Frame (sprite, effects, bubble) out. Pure; `t` is
the wall clock, for idle blinks and bobs that do not depend on the state's age."""

from __future__ import annotations

import math

from . import sprites as s
from .pet import FLIP_S, NEEDS_YOU, SLEEPING, THINKING, WORKING, View
from .frame import Frame


def _beat(age: float, hz: float) -> int:
    return int(age * hz) % 2


def _dots(age: float, x: int) -> list:
    """Three thought dots rising one after another above (x, 0)."""
    out = []
    for i in range(3):
        if (age * 2.5) % 4 > i:
            out.append((("GGG", "GGG", "GGG") if i == 2 else ("GG", "GG"), x + i * 3, -4 - i * 4))
    return out


def _zs(age: float, x: int) -> list:
    out = []
    for i in range(2):
        k = (age * 0.6 + i * 0.5) % 1.0
        out.append((s.ZED, x + i * 4 + int(k * 3), -4 - int(k * 10) - i * 3))
    return out


def _poof(age: float, w: int, h: int, length: float) -> list:
    """Clouds puffing out from both sides of the pet and rising."""
    k = min(1.0, age / max(length, 0.01))
    rise = int(k * 6)
    out = [(s.POOF, -9 - int(k * 3), h - 6 - rise), (s.POOF, w - 2 + int(k * 3), h - 6 - rise)]
    if k > 0.35:
        out.append((s.POOF, w // 2 - 5, -6 - rise))
    return out


def _stars(age: float, cx: int, y: int) -> list:
    """Dizzy stars circling over its head."""
    out = []
    for i in range(3):
        a = age * 5 + i * 2.09
        out.append((s.SPARKLE, int(round(cx - 1 + math.cos(a) * 7)), int(round(y + math.sin(a) * 1.5))))
    return out


def _backflip(body: tuple[str, ...], age: float, w: int, h: int, height: int) -> Frame:
    """The body going up and over backwards a quarter turn at a time (upside down at the top),
    never below the floor, and landing on its feet. The sprite box stays empty where the pet
    stands; the body is drawn over it."""
    k = min(1.0, age / FLIP_S)
    body = s.rotate(body, -int(k * 4 + 0.5))
    lift = int(round(height * math.sin(math.pi * k)))
    return Frame(s.freeze(s.blank(w, h)), effects=[(body, (w - len(body[0])) // 2, h - len(body) - lift)])


def frame(view: View, t: float) -> Frame:
    return clawd(view, t) if view.kind == "clawd" else hermes(view, t)


# ---------------------------------------------------------------- Clawd

def clawd(v: View, t: float) -> Frame:
    st, age = v.state, v.age
    eyes, arms, feet, dy = "open", "down", "both", 0
    fx: list = []
    pixels: list = []
    w = s.CLAWD_W
    if st == "held":
        return Frame(s.clawd("open", "up", "left" if int(age * 3) % 2 else "right"), bubble=v.bubble)
    if st == "falling":
        return Frame(s.clawd("closed", "up"))
    if st == "bonk":
        return Frame(s.flip(s.clawd("closed")), effects=[(s.SPARKLE, w // 2 - 1, s.CLAWD_H - 2)])
    if st == "dizzy":
        return Frame(s.clawd("left" if int(age * 2.5) % 2 else "right"), dx=1 if _beat(age, 1.5) else 0,
                     effects=_stars(age, w // 2, -5))
    if st == "land":
        return Frame(s.clawd(), effects=[(s.DUST, -3, s.CLAWD_H - 3), (s.DUST, w - 1, s.CLAWD_H - 3)])
    if st == "rare":
        n = len(s.SPIN)
        i = int(age / 0.09)
        if i < n:
            return Frame(s.clawd_turn(s.SPIN[i]), dy=-1 if i % 4 in (1, 2) else 0)
        arms = "up" if _beat(age, 4) else "down"
        return Frame(s.clawd("closed", arms), effects=[(s.SPARKLE, 0, -4), (s.SPARKLE, w - 3, -6)])
    if st == "flip":
        if age < FLIP_S:
            return _backflip(s.clawd("closed", "up"), age, w, s.CLAWD_H, 8)
        st, age = "done", age - FLIP_S                  # landed: the cheer of "done"
    if v.walking:
        eyes = "right" if v.facing > 0 else "left"
        feet = "left" if (v.steps // 3) % 2 else "right"
    elif st == "idle":
        phase = t % 7.0
        if phase < 0.15 or 3.6 < phase < 3.75:
            eyes = "closed"
        elif 4.5 < phase < 5.6:
            eyes = "left"
        elif 5.6 < phase < 6.4:
            eyes = "right"
    elif st == THINKING:
        eyes = "up"
        fx += _dots(age, w - 4)
    elif st == WORKING:
        arms = "one-up" if _beat(age, 4) else "down"           # typing away
        feet = ("left", "both", "right", "both")[int(age * 6) % 4]
    elif st == NEEDS_YOU:
        arms = "up" if _beat(age, 3) else "down"
        fx.append((s.BANG, w // 2 - 2, -9))
        if v.urgent:
            dy = -1 if _beat(age, 3) else 0
    elif st == "thanks":
        eyes, arms = "closed", "up"
        fx.append((s.HEART, w // 2 - 3, -8 - int(age * 3)))
    elif st == "oops":
        eyes = "closed" if age < 0.6 else "open"
        fx.append((s.SWEAT, w - 2, -1))
        dy = 0
    elif st == "helper":
        eyes, arms = "right", "one-up"
    elif st == "done":
        arms = "up" if _beat(age, 4) else "down"
        eyes = "closed" if _beat(age, 2) else "open"
        dy = -1 if _beat(age, 4) else 0
        pixels = s.confetti(age, w)
    elif st == "failed":
        eyes = "closed"
        fx.append((s.SWEAT, w - 2, 0))
    elif st == "compact":
        eyes = "closed"
        fx += _poof(age, w, s.CLAWD_H, 1.0)
    elif st == SLEEPING:
        eyes = "closed"
        fx += _zs(t, w - 4)
    elif st == "poke":
        eyes, arms = "closed", "up" if age < 0.5 else "down"
        dy = -1 if age < 0.25 else 0
    elif st in ("arrive", "leaving"):
        fx += _poof(age, w, s.CLAWD_H, 0.9)
    f = Frame(s.clawd(eyes, arms, feet), dy=dy, effects=fx, pixels=pixels, bubble=v.bubble)
    if st == "oops" and age < 0.9:
        f.dx = 1 if _beat(age, 10) else -1
    if st == "leaving":
        f.alpha = max(0.0, 1.0 - age / 0.9)
    elif st == "arrive":
        f.alpha = min(1.0, age / 0.5)
    return f


# ---------------------------------------------------------------- Hermes

def hermes(v: View, t: float) -> Frame:
    st, age = v.state, v.age
    kw: dict = {"orb_dy": -1 if int(t * 1.6) % 2 else 0, "orb_phase": int(t * 1.5)}
    fx: list = []
    pixels: list = []
    dy = 0
    w, h = s.HERMES_W, s.HERMES_H
    if st == "held":
        legs = "left" if int(age * 3) % 2 else "right"
        return _face(Frame(s.hermes(eyes="open", arm="up", legs=legs, orb_dy=-1), bubble=v.bubble), v)
    if st == "falling":
        return _face(Frame(s.hermes(eyes="open", arm="up", orb_dy=-2)), v)
    if st == "bonk":
        return _face(Frame(s.flip(s.hermes()), effects=[(s.SPARKLE, w // 2 - 2, h - 2)]), v)
    if st == "dizzy":
        return _face(Frame(s.hermes(bow=int(age * 2) % 2, orb_dy=1), dx=1 if _beat(age, 1.5) else 0,
                           effects=_stars(age, w // 2 - 2, -5)), v)
    if st == "land":
        return _face(Frame(s.hermes(), effects=[(s.DUST, -2, h - 3), (s.DUST, w - 3, h - 3)]), v)
    if st == "flip":
        if age < FLIP_S:
            return _face(_backflip(s.hermes(eyes="open", arm="up", glow=True), age, w, h, 9), v)
        st, age = "done", age - FLIP_S
    if v.walking:
        kw["legs"] = "left" if (v.steps // 3) % 2 else "right"
        kw["back_arm"] = (v.steps // 3) % 2
    elif st == "idle":
        if 5.0 < t % 9.0 < 6.2:
            kw["eyes"] = "open"
    elif st == THINKING:
        kw["glow"] = _beat(age, 2) == 1
        fx += _dots(age, 14)
    elif st == WORKING:
        kw["orb_phase"] = int(age * 6)
        kw["glow"] = True
    elif st == NEEDS_YOU:
        kw.update(arm="wave" if _beat(age, 3) else "up", eyes="open")
        fx.append((s.BANG, 8, -9))
        if v.urgent:
            dy = -1 if _beat(age, 3) else 0
    elif st == "thanks":
        kw["bow"] = 1
        fx.append((s.HEART, 7, -8 - int(age * 3)))
    elif st == "oops":
        kw["eyes"] = "open"
        fx.append((s.SWEAT, 14, 3))
    elif st == "helper":
        kw.update(glow=True, orb_phase=int(age * 8))
    elif st == "done":
        kw.update(arm="up", glow=True)
        dy = -1 if _beat(age, 3) else 0
        for x, y in s.sparkles(age, 19, 11):
            fx.append((s.SPARKLE, x - 1, y - 1))
        pixels = s.confetti(age, w)
    elif st == "rare":
        # the orb circles her, passing behind her head
        kw.update(arm="up", with_orb=False)
        a = age * 4.0
        ox, oy = int(round(w / 2 - 2 + math.cos(a) * 12)), int(round(7 + math.sin(a) * 4))
        behind = math.sin(a) < 0
        f = Frame(s.hermes(**kw), effects=[(s.orb(int(age * 6), True), ox, oy)] if not behind else [])
        if behind:
            f.under = [(s.orb(int(age * 6), True), ox, oy)]
        return _face(f, v)
    elif st == "failed":
        kw.update(bow=1)
        fx.append((s.SWEAT, 14, 3))
    elif st == "compact":
        kw["glow"] = True
        fx += _poof(age, w, h, 1.0)
    elif st == SLEEPING:
        kw.update(bow=1, orb_dy=1, orb_phase=0)
        fx += _zs(t, 13)
    elif st == "poke":
        kw.update(eyes="open", arm="wave" if age < 0.6 and _beat(age, 5) else "hold")
        dy = -1 if age < 0.25 else 0
    elif st in ("arrive", "leaving"):
        fx += _poof(age, w, h, 0.9)
    f = Frame(s.hermes(**kw), dy=dy, effects=fx, pixels=pixels, bubble=v.bubble)
    if st == "oops" and age < 0.9:
        f.dx = 1 if _beat(age, 10) else -1
    if st == "leaving":
        f.alpha = max(0.0, 1.0 - age / 0.9)
    elif st == "arrive":
        f.alpha = min(1.0, age / 0.5)
    return _face(f, v)


def _face(f: Frame, v: View) -> Frame:
    """Hermes is drawn facing right; walking left mirrors her and her effects."""
    if v.facing > 0:
        return f
    w = f.width
    f.sprite = s.mirror(f.sprite)
    f.effects = [(s.mirror(b), w - x - len(b[0]), y) for b, x, y in f.effects]
    f.under = [(s.mirror(b), w - x - len(b[0]), y) for b, x, y in f.under]
    f.pixels = [(w - 1 - x, y, c) for x, y, c in f.pixels]
    return f
