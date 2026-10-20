"""The real pet app, headless (Qt's offscreen platform), on every system: it takes hook messages over
the real channel (a Unix socket, or a named pipe on Windows), makes a pet per agent instance and
draws it."""

import os
import time
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from agentpet import events, ipc, procs  # noqa: E402
from agentpet.app import PetsApp  # noqa: E402

from .helpers import FakeHome  # noqa: E402

APP = QApplication.instance() or QApplication(["agentpet-test"])


def pump(until, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return False


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.home.__enter__()
        self.app = PetsApp(px=4)
        self.assertTrue(self.app.start())

    def tearDown(self):
        self.app.stop()
        APP.processEvents()
        self.home.__exit__()

    def send(self, agent, event, tool=None, pid=None):
        me = procs.info(pid or os.getpid())
        msg = events.message(agent, event, f"s-{agent}", tool, "Terminal", pid=me.pid, pid_start=me.stamp,
                             where="~/projects/x")
        self.assertTrue(ipc.send(events.encode(msg)), "the pets did not take the message")

    def test_hook_messages_make_pets_that_draw(self):
        self.send("claude", "SessionStart")
        self.assertTrue(pump(lambda: len(self.app.pets) == 1))
        self.send("claude", "PreToolUse", "Bash")
        self.assertTrue(pump(lambda: self.app.pets["claude:%d" % os.getpid()].steady == "working"))
        start = time.monotonic()
        while time.monotonic() - start < 1.2:          # past the fade-in of a pet that just arrived
            self.app.tick()
            APP.processEvents()
            time.sleep(0.04)
        win = self.app.windows["claude:%d" % os.getpid()]
        img = win.grab().toImage()
        opaque = sum(1 for x in range(0, img.width(), 3) for y in range(0, img.height(), 3) if img.pixelColor(x, y).alpha() > 200)
        self.assertGreater(opaque, 50, "nothing drawn")

    def test_one_pet_per_instance_and_each_only_hears_its_own(self):
        self.send("claude", "UserPromptSubmit")
        self.send("hermes", "SessionStart")
        self.assertTrue(pump(lambda: len(self.app.pets) == 2))
        self.app.tick()
        states = {k: p.steady for k, p in self.app.pets.items()}
        self.assertEqual(states, {"claude:%d" % os.getpid(): "thinking", "hermes:%d" % os.getpid(): "idle"})

    def test_a_second_start_steps_aside(self):
        self.assertFalse(PetsApp(px=4).start())

    def test_the_mouse(self):
        self.send("claude", "SessionStart")
        self.assertTrue(pump(lambda: len(self.app.pets) == 1))
        self.app.tick()
        key = "claude:%d" % os.getpid()
        pet = self.app.pets[key]
        self.app.hand(key, "click")
        self.assertEqual(pet.state(time.monotonic()), "poke")
        self.assertEqual(pet.view(time.monotonic()).bubble, "~/projects/x · Terminal")
        self.app.hand(key, "pick", pet.x, pet.y)
        self.app.hand(key, "move", pet.x, 100)
        self.assertEqual(pet.motion.surface, "held")
        self.app.hand(key, "drop", pet.x, 100)
        self.assertEqual(pet.motion.surface, "air")


if __name__ == "__main__":
    unittest.main()
