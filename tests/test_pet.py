import random
import unittest

from agentpet import looks
from agentpet.motion import Area
from agentpet.pet import LEAVE_S, NEEDS_YOU, QUIET_WORK, SLEEP_AFTER, URGENT_AFTER, Pet, View

AREA = Area(0, 0, 1000, 600)


def pet(**kw):
    return Pet("clawd", rng=random.Random(1), **kw)


def run(p, start, seconds, dt=0.08):
    t = start
    while t < start + seconds:
        t += dt
        p.update(t, dt, AREA, 72, 40, 36)
    return t


class PetTest(unittest.TestCase):
    def test_hidden_until_its_agent_says_something(self):
        p = pet()
        self.assertEqual(p.state(0), "hidden")
        p.handle("SessionStart", 0, "s1")
        self.assertEqual(p.state(0.1), "arrive")
        self.assertEqual(p.state(5), "idle")

    def test_prompt_then_tools(self):
        p = pet()
        p.handle("UserPromptSubmit", 0, "s1")
        self.assertEqual(p.state(2), "thinking")
        p.handle("PreToolUse", 3, "s1", "Bash")
        self.assertEqual(p.state(4), "working")
        self.assertEqual(p.view(4).bubble, "Running a command…")

    def test_approval_says_thanks_and_keeps_the_tool(self):
        p = pet()
        p.handle("PreToolUse", 0, "s1", "Bash")
        p.handle("PermissionRequest", 1, "s1", "Bash")
        self.assertEqual(p.state(2), NEEDS_YOU)
        self.assertEqual(p.view(2).bubble, "Needs you!")
        self.assertTrue(p.view(1 + URGENT_AFTER + 1).urgent)
        p.handle("PostToolUse", 40, "s1")
        self.assertEqual(p.state(40.5), "thanks")
        self.assertEqual(p.state(43), "working")
        self.assertEqual(p.view(43).bubble, "Running a command…")

    def test_short_reactions_hand_back(self):
        p = pet()
        p.handle("PreToolUse", 0, "s1", "Edit")
        p.handle("PostToolUseFailure", 1, "s1")
        self.assertEqual(p.state(1.5), "oops")
        self.assertEqual(p.state(5), "working")
        p.handle("Stop", 6, "s1")
        self.assertEqual(p.state(6.5), "done")
        self.assertEqual(p.state(10), "idle")
        p.handle("StopFailure", 11, "s1")
        self.assertEqual(p.state(11.5), "failed")

    def test_a_side_agent_finishing_while_idle_does_not_make_it_work(self):
        # Claude Code's away summary (and background agents) run helpers after the turn is over:
        # SubagentStart/SubagentStop arrive while the main agent is idle.
        p = pet()
        p.handle("UserPromptSubmit", 0, "s1")
        p.handle("Stop", 10, "s1")
        self.assertEqual(p.state(20), "idle")
        p.handle("SubagentStart", 30, "s1")
        p.handle("SubagentStop", 35, "s1")
        self.assertEqual(p.state(36), "idle")
        self.assertEqual(p.state(60), "idle")

    def test_a_helper_during_a_turn_still_shows(self):
        p = pet()
        p.handle("PreToolUse", 0, "s1", "Task")
        p.handle("SubagentStart", 1, "s1")
        self.assertEqual(p.state(1.5), "helper")
        p.handle("SubagentStop", 20, "s1")
        self.assertEqual(p.state(21), "working")

    def test_rare_surprise(self):
        p = pet(rare_chance=1.0)
        p.handle("Stop", 0, "s1")
        self.assertEqual(p.state(0.5), "rare")

    def test_leaves_when_the_last_session_ends(self):
        p = pet()
        p.handle("SessionStart", 0, "a")
        p.handle("SessionStart", 0, "b")
        p.handle("SessionEnd", 5, "a")
        self.assertEqual(p.state(5.1), "idle")
        p.handle("SessionEnd", 6, "b")
        self.assertEqual(p.state(6.1), "leaving")
        run(p, 6, LEAVE_S + 0.2)
        self.assertEqual(p.state(7.5), "hidden")
        p.handle("UserPromptSubmit", 8, "c")
        self.assertEqual(p.state(8.1), "arrive")

    def test_sleeps_when_quiet_and_settles_after_silent_work(self):
        p = pet()
        p.handle("SessionStart", 0, "s1")
        self.assertEqual(p.state(SLEEP_AFTER + 1), "sleeping")
        p.handle("PreToolUse", SLEEP_AFTER + 2, "s1", "Bash")
        p.update(SLEEP_AFTER + 2 + QUIET_WORK + 1, 0.08, AREA, 72, 40, 36)
        self.assertEqual(p.steady, "idle")

    def test_roams_when_idle_and_stands_still_on_the_floor_when_busy(self):
        p = pet()
        p.handle("SessionStart", 0, "s1")
        xs = set()
        t = 1.0
        for _ in range(3000):
            t += 0.08
            p.update(t, 0.08, AREA, 72, 40, 36)
            xs.add(round(p.x))
            self.assertTrue(-1 <= p.x <= 1001 and -1 <= p.y <= 601)
        self.assertGreater(max(xs) - min(xs), 100)
        p.handle("UserPromptSubmit", t, "s1")
        t = run(p, t, 3)
        x = (p.x, p.y)
        run(p, t, 2)
        self.assertEqual((p.x, p.y), x)
        self.assertEqual(p.motion.surface, "floor")

    def test_a_click_says_which_window(self):
        p = pet()
        p.handle("SessionStart", 0, "s1", app="Ptyxis", where="~/projects/thatpet", tty="pts/3")
        p.poke(1)
        self.assertEqual(p.view(1.2).bubble, "~/projects/thatpet · Ptyxis")
        p.handle("PermissionRequest", 5, "s1", "Bash")
        p.poke(6)
        self.assertEqual(p.view(6.2).bubble, "Needs you: ~/projects/thatpet · Ptyxis")
        self.assertEqual(p.state(10), NEEDS_YOU)


class LooksTest(unittest.TestCase):
    def test_every_state_draws_for_both_pets(self):
        states = ("hidden", "arrive", "idle", "thinking", "working", "needs_you", "thanks", "oops", "helper",
                  "done", "rare", "failed", "compact", "sleeping", "poke", "leaving", "held", "falling",
                  "bonk", "dizzy", "land")
        for kind in ("clawd", "hermes"):
            size = None
            for st in states:
                for age in (0, 0.3, 1.1, 2.9, 40):
                    for facing in (1, -1):
                        for turn in ("", "cw", "ccw", "flip"):
                            f = looks.frame(View(kind, st, age, st == "idle" and age > 1, facing, 7, "hi", age > 30, turn), age * 3)
                            dims = (f.width, f.height)
                            size = size or dims
                            self.assertEqual(dims, size, (kind, st, age))
                            self.assertTrue(0 <= f.alpha <= 1)


if __name__ == "__main__":
    unittest.main()
