"""One pet per agent instance; each hears only its own instance and is on screen only while that
instance runs."""

import random
import unittest

from agentpet import events
from agentpet.motion import Area
from agentpet.pet import CHECK_EVERY, LEAVE_S, Pets

AREA = Area(0, 0, 1200, 700)


def msg(agent, event, session="s1", tool=None, pid=None, start=None, where=None, app=None, tty=None):
    return events.decode(events.encode(events.message(agent, event, session, tool, app, pid=pid, pid_start=start,
                                                      where=where, tty=tty)))


class Procs:
    """Stand-in for the process table."""

    def __init__(self):
        self.running = set()

    def alive(self, pid, start):
        return (pid, start) in self.running


class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.procs = Procs()
        self.pets = Pets(rng=random.Random(3), alive=self.procs.alive, rare_chance=0)
        self.t = 0.0

    def send(self, *a, **kw):
        return self.pets.deliver(msg(*a, **kw), self.t)

    def tick(self, seconds):
        end = self.t + seconds
        while self.t < end:
            self.t += 0.08
            for _, pet in self.pets.items():
                pet.update(self.t, 0.08, AREA, 72, 40, 36)

    def state(self, key):
        return self.pets[key].state(self.t) if key in self.pets.pets else "gone"

    def test_each_pet_hears_only_its_own_agent(self):
        self.procs.running.add((100, 7))
        self.send("claude", "PreToolUse", tool="Bash", pid=100, start=7)
        self.tick(2)
        self.assertEqual(self.state("claude:100"), "working")
        self.assertEqual(len(self.pets.of_kind("hermes")), 0)        # Hermes isn't running: no Hermes pet

        self.procs.running.add((200, 9))
        self.send("hermes", "PermissionRequest", tool="terminal", pid=200, start=9)
        self.tick(2)
        self.assertEqual(self.state("hermes:200"), "needs_you")
        self.assertEqual(self.state("claude:100"), "working")       # untouched by Hermes's event
        self.assertEqual(self.pets["claude:100"].view(self.t).bubble, "Running a command…")

        self.send("claude", "Stop", pid=100, start=7)
        self.tick(4)
        self.assertEqual(self.state("claude:100"), "idle")
        self.assertEqual(self.state("hermes:200"), "needs_you")     # still waiting on its own

    def test_one_pet_per_claude_code_window(self):
        for pid in (100, 101, 102):
            self.procs.running.add((pid, 1))
            self.send("claude", "SessionStart", session=f"s{pid}", pid=pid, start=1, where=f"~/p{pid}")
        self.tick(1)
        self.assertEqual(len(self.pets.of_kind("clawd")), 3)
        self.send("claude", "PermissionRequest", session="s101", tool="Bash", pid=101, start=1)
        self.tick(1)
        self.assertEqual(self.state("claude:101"), "needs_you")
        self.assertEqual(self.state("claude:100"), "idle")
        self.assertEqual(self.state("claude:102"), "idle")
        self.procs.running.discard((101, 1))                          # that window is closed
        self.tick(CHECK_EVERY + LEAVE_S + 0.5)
        self.assertEqual(self.state("claude:101"), "hidden")
        self.assertEqual(self.state("claude:100"), "idle")

    def test_there_is_a_limit(self):
        pets = Pets(alive=self.procs.alive, limit=2)
        for pid in (1, 2, 3):
            pets.deliver(msg("claude", "SessionStart", pid=pid + 10), 0)
        self.assertEqual(len(pets), 2)

    def test_a_pet_leaves_when_its_agent_exits_and_only_that_pet(self):
        self.procs.running |= {(100, 7), (200, 9)}
        self.send("claude", "SessionStart", pid=100, start=7)
        self.send("hermes", "SessionStart", pid=200, start=9)
        self.tick(2)
        self.procs.running.discard((200, 9))                       # Hermes killed: no SessionEnd at all
        self.tick(CHECK_EVERY + LEAVE_S + 0.5)
        self.assertEqual(self.state("hermes:200"), "hidden")
        self.assertEqual(self.state("claude:100"), "idle")

    def test_a_reused_pid_is_not_the_agent(self):
        self.procs.running.add((100, 7))
        self.send("claude", "SessionStart", pid=100, start=7)
        self.tick(1)
        self.procs.running = {(100, 99)}                            # same pid, another process
        self.tick(CHECK_EVERY + LEAVE_S + 0.5)
        self.assertEqual(self.state("claude:100"), "hidden")

    def test_clear_in_the_same_claude_does_not_make_clawd_leave(self):
        self.procs.running.add((100, 7))
        self.send("claude", "SessionStart", "a", pid=100, start=7)
        self.tick(2)
        self.send("claude", "SessionEnd", "a", pid=100, start=7)
        self.send("claude", "SessionStart", "b", pid=100, start=7)
        self.tick(CHECK_EVERY + 1)
        self.assertEqual(self.state("claude:100"), "idle")
        self.procs.running.clear()                                   # /exit: the process ends
        self.send("claude", "SessionEnd", "b", pid=100, start=7)
        self.tick(CHECK_EVERY + LEAVE_S + 0.5)
        self.assertEqual(self.state("claude:100"), "hidden")

    def test_twins_in_the_same_folder_are_told_apart_by_their_tab(self):
        for pid, tty in ((100, "pts/1"), (101, "pts/4")):
            self.procs.running.add((pid, 1))
            self.send("claude", "SessionStart", session=f"s{pid}", pid=pid, start=1, where="~/app", app="Ptyxis", tty=tty)
        self.send("claude", "SessionStart", session="s9", pid=109, start=1, where="~/other", app="Ptyxis", tty="pts/9")
        self.assertEqual(self.pets.label("claude:100"), "~/app · Ptyxis · pts/1")
        self.assertEqual(self.pets.label("claude:101"), "~/app · Ptyxis · pts/4")
        self.assertEqual(self.pets.label("claude:109"), "~/other · Ptyxis")

    def test_messages_for_other_agents_are_dropped(self):
        self.assertIsNone(self.pets.deliver({"agent": "codex", "event": "Stop"}, 0))


class FieldsTest(unittest.TestCase):
    def test_pid_is_checked(self):
        self.assertEqual(msg("claude", "Stop", pid=1234, start=5)["pid"], 1234)
        bad = events.decode(b'{"agent":"claude","event":"Stop","pid":true,"pid_start":1}')
        self.assertNotIn("pid", bad)
        self.assertNotIn("pid", events.decode(b'{"agent":"claude","event":"Stop","pid":999999999}'))

    def test_window_fields(self):
        m = msg("claude", "Stop", where="~/projects/my app", tty="pts/12")
        self.assertEqual((m["where"], m["tty"]), ("~/projects/my app", "pts/12"))
        self.assertNotIn("tty", msg("claude", "Stop", tty="../../etc"))
        self.assertEqual(msg("claude", "Stop", tty="ttys003")["tty"], "ttys003")          # macOS
        self.assertEqual(events.short_path("C:\\Users\\me\\code\\app", "C:\\Users\\me"), "~/code/app")
        self.assertEqual(events.short_path("/home/u/projects/thatpet", "/home/u"), "~/projects/thatpet")
        self.assertEqual(events.short_path("/home/u", "/home/u"), "~")
        self.assertEqual(events.short_path("/srv/very/long/path/to/some/project", "/home/u"), ".../some/project")


if __name__ == "__main__":
    unittest.main()
