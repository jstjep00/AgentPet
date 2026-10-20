import unittest

from agentpet import events


class EventsTest(unittest.TestCase):
    def test_tool_labels(self):
        self.assertEqual(events.tool_label("Bash"), "Running a command…")
        self.assertEqual(events.tool_label("terminal"), "Running a command…")
        self.assertEqual(events.tool_label("Edit"), "Editing code…")
        self.assertEqual(events.tool_label("patch"), "Editing code…")
        self.assertEqual(events.tool_label("browser_click"), "Browsing the web…")
        self.assertEqual(events.tool_label("mcp__github__create_issue"), "Using github…")
        self.assertEqual(events.tool_label("Frobnicate"), "Using Frobnicate…")
        self.assertEqual(events.tool_label(None), "Working…")

    def test_round_trip(self):
        msg = events.message("claude", "PreToolUse", "abc-123", "Bash", "Ptyxis", now_ms=5)
        self.assertEqual(events.decode(events.encode(msg)),
                         {"agent": "claude", "event": "PreToolUse", "ts": 5, "session": "abc-123", "tool": "Bash", "app": "Ptyxis"})

    def test_decode_rejects_and_cleans(self):
        self.assertIsNone(events.decode(b"not json"))
        self.assertIsNone(events.decode(b'{"agent":"codex","event":"Stop"}'))
        self.assertIsNone(events.decode(b'{"agent":"claude","event":"Explode"}'))
        out = events.decode(b'{"agent":"hermes","event":"PreToolUse","tool":"rm -rf /; echo","session":"a/b"}')
        self.assertEqual(out["tool"], "rm_-rf____echo")
        self.assertEqual(out["session"], "a_b")
        self.assertEqual(events.decode(b'{"cmd":"quit"}'), {"cmd": "quit"})
        self.assertEqual(events.decode(b'{"agent":"claude","event":"Stop","app":"VS Code"}')["app"], "VS Code")

    def test_every_event_maps_to_a_reaction(self):
        for name in events.EVENTS:
            self.assertIsNotNone(events.reaction(name))
        self.assertEqual(events.reaction("Rare"), "rare")


if __name__ == "__main__":
    unittest.main()
