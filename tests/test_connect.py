import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentpet import connect

THATPET = {"type": "command", "command": '"/home/u/.local/bin/thatpet" hook --provider claude', "timeout": 2}
EXISTING = {
    "model": "opus",
    "hooks": {
        "PreToolUse": [{"matcher": "", "hooks": [THATPET]}],
        "Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}],
    },
}


class ClaudeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_adds_one_handler_per_event_and_keeps_everything_else(self):
        new = connect.add_claude_hooks(EXISTING, connect.hook_command("/x/agentpet"))
        self.assertEqual(new["model"], "opus")
        self.assertIn({"matcher": "", "hooks": [THATPET]}, new["hooks"]["PreToolUse"])
        self.assertEqual(new["hooks"]["Stop"][0], EXISTING["hooks"]["Stop"][0])
        for event, matcher in connect.CLAUDE_EVENTS:
            ours = [g for g in new["hooks"][event] if any(connect.is_ours(h) for h in g["hooks"])]
            self.assertEqual(len(ours), 1, event)
            self.assertEqual(ours[0].get("matcher"), matcher)

    def test_connecting_twice_changes_nothing_and_strip_undoes_it(self):
        once = connect.add_claude_hooks(EXISTING, connect.hook_command("/x/agentpet"))
        self.assertEqual(connect.add_claude_hooks(once, connect.hook_command("/x/agentpet")), once)
        self.assertEqual(connect.strip_claude_hooks(once), EXISTING)
        self.assertEqual(connect.strip_claude_hooks({"hooks": {}}), {})

    def test_connect_backs_up_and_disconnect_restores(self):
        self.path.write_text(json.dumps(EXISTING, indent=2))
        self.assertFalse(connect.claude_connected(self.path))
        msg = connect.connect_claude("/x/agentpet", self.path)
        self.assertIn("connected", msg)
        self.assertTrue(connect.claude_connected(self.path))
        backups = list(Path(self.tmp.name).glob("settings.json.agentpet-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), EXISTING)
        self.assertEqual(connect.connect_claude("/x/agentpet", self.path), "Claude Code: already connected")
        connect.disconnect_claude(self.path)
        self.assertEqual(json.loads(self.path.read_text()), EXISTING)

    def test_replaces_hooks_of_the_old_name(self):
        old = connect.add_claude_hooks(EXISTING, '"/home/u/.local/bin/agentpets" hook claude')
        new = connect.add_claude_hooks(old, connect.hook_command("/x/agentpet"))
        self.assertNotIn("agentpets", json.dumps(new))
        self.assertEqual(connect.strip_claude_hooks(new), EXISTING)

    def test_leaves_invalid_json_alone(self):
        self.path.write_text("{ not json")
        with self.assertRaises(connect.ConnectError):
            connect.connect_claude("/x/agentpet", self.path)
        self.assertEqual(self.path.read_text(), "{ not json")

    def test_creates_settings_when_there_are_none(self):
        connect.connect_claude("/x/agentpet", self.path)
        self.assertTrue(connect.claude_connected(self.path))


class HermesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / ".hermes"
        self.home.mkdir()
        self.env = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_plugin_source_has_the_launcher(self):
        src = connect.plugin_source("/home/u/.local/bin/agentpet")
        self.assertIn('LAUNCHER = ["/home/u/.local/bin/agentpet"]', src)
        compile(src, "plugin", "exec")

    def test_connect_writes_the_plugin_and_enables_it(self):
        calls = []

        def run(argv, **kw):
            calls.append(argv[1:])
            if argv[1:] == ["plugins", "enable", "agentpet"]:
                (self.home / "config.yaml").write_text("plugins:\n  enabled:\n    - agentpet\n  disabled: []\n")
            return mock.Mock(returncode=0, stdout=b"ok")

        with mock.patch.object(connect, "hermes_executable", return_value="/bin/hermes"):
            self.assertIn("connected", connect.connect_hermes("/x/agentpet", run=run))
            self.assertTrue(connect.hermes_connected())
            self.assertTrue((self.home / "plugins/agentpet/plugin.yaml").is_file())
            connect.disconnect_hermes(run=run)
        self.assertEqual(calls, [["plugins", "enable", "agentpet"], ["plugins", "disable", "agentpet"]])
        self.assertFalse((self.home / "plugins/agentpet").exists())


if __name__ == "__main__":
    unittest.main()
