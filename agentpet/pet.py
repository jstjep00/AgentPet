"""The pets' state: which reaction each one shows and where it is. Pure Python with an injectable
clock and random source; `looks` turns a View into pixels.

A pet has a steady state (idle, thinking, working, needs_you) and, on top of it, short reactions
that play once and hand back to the steady state (thanks, oops, done, ...). Where it is and how it
moves is its `motion`: it likes the floor, climbs the walls and the top of the screen when idle,
and drops back to the floor when its agent needs it.

There is one pet per running agent: one Clawd for each Claude Code process, one Hermes for each
Hermes process (`Pets` routes each event to its own instance's pet). A pet is on screen only while
its agent process runs: it appears with the first event and leaves when that process has exited,
however it exited. Events that name no process keep a pet until their session ends or goes quiet
for hours.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from . import events
from .motion import AIR, FLOOR, HELD, Area, Motion

IDLE, THINKING, WORKING, NEEDS_YOU, SLEEPING = "idle", "thinking", "working", "needs_you", "sleeping"

# reaction -> seconds it plays
SHORT = {"thanks": 1.6, "oops": 1.8, "helper": 1.6, "done": 2.8, "rare": 3.0, "failed": 2.6,
         "compact": 1.8, "poke": 2.2, "arrive": 0.9}
CALM = ("poke", "arrive")    # short reactions that don't call a pet down to the floor
URGENT_AFTER = 30.0          # needs_you this long: it gets more insistent
SLEEP_AFTER = 600.0          # idle this long with no event: falls asleep (wherever it is)
QUIET_WORK = 600.0           # thinking or working with no event this long: back to idle
SESSION_TTL = 3 * 3600.0     # a session silent this long is over (when its process is unknown)
CHECK_EVERY = 2.0            # how often the agent processes are checked
LEAVE_S = 0.9                # the poof when it leaves
RARE_CHANCE = 0.03
MAX_PETS = 8


@dataclass
class View:
    """What the pet is doing now, for `looks`."""

    kind: str
    state: str                  # a steady state, a SHORT reaction, held/falling/bonk/dizzy/land, "leaving" or "hidden"
    age: float                  # seconds in this state
    walking: bool
    facing: int                 # 1 right, -1 left (in the sprite's own frame)
    steps: int                  # walk steps taken (for the walk cycle)
    bubble: str | None
    urgent: bool
    turn: str = ""              # "", "cw", "ccw" or "flip": how the sprite lies (see motion)


class Pet:
    def __init__(self, kind: str, rng: random.Random | None = None, rare_chance: float = RARE_CHANCE,
                 alive=None) -> None:
        self.kind = kind
        self.rng = rng or random.Random()
        self.rare_chance = rare_chance
        self.alive = alive or (lambda pid, start: True)      # is that agent process still running?
        self.motion = Motion(self.rng)
        self.visible = False
        self.leaving_since: float | None = None
        self.steady = IDLE
        self.steady_since = 0.0
        self.short: tuple[str, float, float] | None = None     # (reaction, start, end)
        self.tool: str | None = None
        self.app: str | None = None
        self.where: str | None = None     # the agent's working folder, home as ~
        self.tty: str | None = None       # its terminal tab (pts/N)
        self.sessions: dict[str, float] = {}         # session -> last event, for events with no process
        self.procs: dict[int, int | None] = {}      # agent process -> its start time
        self.checked = 0.0
        self.last_event = 0.0
        self.poke_text: str | None = None

    @property
    def x(self) -> float:
        return self.motion.x

    @property
    def y(self) -> float:
        return self.motion.y

    # -- events --------------------------------------------------------------------------
    def handle(self, event: str, now: float, session: str | None = None, tool: str | None = None,
               app: str | None = None, pid: int | None = None, pid_start: int | None = None,
               where: str | None = None, tty: str | None = None) -> None:
        r = events.reaction(event)
        if r is None:
            return
        sid = session or "default"
        self.app = app or self.app
        self.where = where or self.where
        self.tty = tty or self.tty
        if pid:
            self.procs[pid] = pid_start
        if r == "session_end":
            # With a process, the pet stays while it runs (a /clear ends one session and starts
            # the next in the same process) and leaves once it exits.
            self.sessions.pop(sid, None)
            if self.visible and not self.procs and not self.sessions:
                self._leave(now)
            return
        if not pid:
            self.sessions[sid] = now
        self.last_event = now
        if not self.visible or self.leaving_since is not None:
            self.visible = True
            self.leaving_since = None
            self._play("arrive", now)
        if r != "session_start":
            self.motion.landing = None          # whatever it was doing, the agent comes first
        if r == "session_start":
            self._steady(IDLE, now)
        elif r == "prompt":
            self._steady(THINKING, now)
        elif r in ("tool", "tool_done"):
            if self.steady == NEEDS_YOU:
                self._play("thanks", now)
            if r == "tool" or self.steady != WORKING:
                self.tool = tool or (self.tool if self.steady in (WORKING, NEEDS_YOU) else None)
            self._steady(WORKING, now)
        elif r == "tool_failed":
            self._steady(WORKING, now)
            self._play("oops", now)
        elif r == "needs_you":
            if self.steady != NEEDS_YOU:
                self._steady(NEEDS_YOU, now)
            if tool:
                self.tool = tool
        elif r == "helper":
            # Helpers also run after a turn is over (Claude Code's away summary, background
            # agents): only a helper the busy main agent asked for is shown.
            if self.steady in (THINKING, WORKING):
                self._steady(WORKING, now)
                self._play("helper", now)
        elif r == "helper_done":
            pass                # says nothing about what the main agent is doing
        elif r == "done":
            self._steady(IDLE, now)
            self._play("rare" if self.rng.random() < self.rare_chance else "done", now)
        elif r == "rare":
            self._steady(IDLE, now)
            self._play("rare", now)
        elif r == "failed":
            self._steady(IDLE, now)
            self._play("failed", now)
        elif r == "compact":
            self._play("compact", now)
        elif r == "climb":
            self._steady(IDLE, now)
            self.short = None
            self.motion.adventure(now)

    def poke(self, now: float, label: str | None = None) -> None:
        """A click on the pet: it says which window its agent is in (calling you over to it when
        it needs you)."""
        if not self.visible or self.leaving_since is not None:
            return
        label = label or self.label()
        self.poke_text = f"Needs you: {label}" if self.steady == NEEDS_YOU else label
        self._play("poke", now)

    def label(self, with_tty: bool = False) -> str:
        """Which window: the agent's folder and its terminal ("~/projects/x · Ptyxis")."""
        parts = [p for p in (self.where, self.app) if p]
        if with_tty and self.tty:
            parts.append(self.tty)
        agent = next(a for a, p in events.AGENTS.items() if p == self.kind)
        return " · ".join(parts) or events.AGENT_NAMES[agent]

    def hide(self) -> None:
        self.visible = False
        self.leaving_since = None
        self.sessions.clear()
        self.procs.clear()

    def prune(self, now: float) -> None:
        """Forgets agent processes that have exited and sessions gone quiet; with nothing left,
        the pet leaves."""
        for pid, start in list(self.procs.items()):
            if not self.alive(pid, start):
                del self.procs[pid]
        for sid, seen in list(self.sessions.items()):
            if now - seen > SESSION_TTL:
                del self.sessions[sid]
        if self.visible and self.leaving_since is None and not self.procs and not self.sessions:
            self._leave(now)

    def _leave(self, now: float) -> None:
        self.leaving_since = now
        self.short = None
        self.motion.walking = False

    def _steady(self, state: str, now: float) -> None:
        if state != self.steady:
            self.steady = state
            self.steady_since = now
        if state != WORKING:
            self.tool = None if state != NEEDS_YOU else self.tool

    def _play(self, reaction: str, now: float, seconds: float | None = None) -> None:
        self.short = (reaction, now, now + (seconds or SHORT[reaction]))

    # -- time ----------------------------------------------------------------------------
    def update(self, now: float, dt: float, area: Area, w: float, h: float, speed: float) -> None:
        """Moves the clock on: short reactions end, quiet states settle, and the pet moves: it
        roams when idle, keeps still asleep or dizzy, and gets down to the floor when busy."""
        if self.leaving_since is not None and now - self.leaving_since >= LEAVE_S:
            self.hide()
        if not self.visible:
            return
        if now - self.checked >= CHECK_EVERY:
            self.checked = now
            self.prune(now)
        if self.short and now >= self.short[2]:
            self.short = None
            self.poke_text = None
        if self.steady in (THINKING, WORKING) and now - self.last_event > QUIET_WORK:
            self._steady(IDLE, now)
        if self.leaving_since is not None:
            self.motion.walking = False
            return
        busy = self.steady != IDLE or (self.short is not None and self.short[0] not in CALM)
        if busy:
            mode = "ground"
        elif self.short or self.motion.landed(now) or self.state(now) == SLEEPING:
            mode = "stay"
        else:
            mode = "roam"
        self.motion.step(now, dt, area, w, h, speed, mode)

    def state(self, now: float) -> str:
        if not self.visible:
            return "hidden"
        if self.leaving_since is not None:
            return "leaving"
        if self.motion.surface == HELD:
            return "held"
        if self.motion.surface == AIR:
            return "falling"
        if self.short and now < self.short[2]:
            return self.short[0]
        landed = self.motion.landed(now)
        if landed:
            return landed
        if self.steady == IDLE and now - max(self.last_event, self.steady_since) > SLEEP_AFTER:
            return SLEEPING
        return self.steady

    def view(self, now: float, step_px: float = 1.0) -> View:
        state = self.state(now)
        if state == "leaving":
            age = now - (self.leaving_since or now)
        elif self.short and state == self.short[0]:
            age = now - self.short[1]
        elif state in ("bonk", "dizzy", "land"):
            age = self.motion.landed_age(now)
        else:
            age = now - self.steady_since
        urgent = state == NEEDS_YOU and age >= URGENT_AFTER
        m = self.motion
        return View(self.kind, state, max(0.0, age), m.walking, m.facing, int(m.travel / max(step_px, 1e-6)),
                    self.bubble(state, urgent), urgent, m.turn)

    def bubble(self, state: str, urgent: bool = False) -> str | None:
        if state == "poke":
            return self.poke_text
        if state == WORKING:
            return events.tool_label(self.tool)
        if state == NEEDS_YOU:
            return "Still waiting for you…" if urgent else "Needs you!"
        return {"oops": "Oops!", "helper": "Asking a helper…", "done": "Done!", "failed": "Oh no…",
                "compact": "Tidying up…"}.get(state)


class Pets:
    """The pets on screen: one per running agent instance (an agent process, or a session when
    the event names no process). An agent's events reach only its own instance's pet, so a pet
    never shows what another agent, or another window of the same agent, is doing."""

    def __init__(self, rng: random.Random | None = None, alive=None, rare_chance: float = RARE_CHANCE,
                 limit: int = MAX_PETS) -> None:
        self.rng = rng or random.Random()
        self.alive = alive
        self.rare_chance = rare_chance
        self.limit = limit
        self.pets: dict[str, Pet] = {}

    @staticmethod
    def key(msg: dict) -> str:
        if msg.get("pid"):
            return f"{msg['agent']}:{msg['pid']}"
        return f"{msg['agent']}:session:{msg.get('session') or 'default'}"

    def __getitem__(self, key: str) -> Pet:
        return self.pets[key]

    def __len__(self) -> int:
        return len(self.pets)

    def items(self) -> list[tuple[str, Pet]]:
        return list(self.pets.items())

    def of_kind(self, kind: str) -> list[Pet]:
        return [p for p in self.pets.values() if p.kind == kind]

    def remove(self, key: str) -> None:
        self.pets.pop(key, None)

    def deliver(self, msg: dict, now: float) -> Pet | None:
        """Hands a decoded hook message to its instance's pet, making the pet if it is new;
        returns that pet."""
        kind = events.AGENTS.get(msg.get("agent"))
        if kind is None or "event" not in msg:
            return None
        k = self.key(msg)
        pet = self.pets.get(k)
        if pet is None:
            if msg["event"] == "SessionEnd" or len(self.pets) >= self.limit:
                return None
            pet = self.pets[k] = Pet(kind, random.Random(self.rng.random()), self.rare_chance, self.alive)
        pet.handle(msg["event"], now, msg.get("session"), msg.get("tool"), msg.get("app"),
                   msg.get("pid"), msg.get("pid_start"), msg.get("where"), msg.get("tty"))
        return pet

    def label(self, key: str) -> str:
        """The window a pet's agent is in; with the terminal tab too when another pet of the same
        kind is in the same folder and terminal."""
        pet = self.pets[key]
        twin = any(o is not pet and o.kind == pet.kind and o.label() == pet.label() for o in self.pets.values())
        return pet.label(with_tty=twin)

    def poke(self, key: str, now: float) -> None:
        if key in self.pets:
            self.pets[key].poke(now, self.label(key))

