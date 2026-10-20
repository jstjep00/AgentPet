import contextlib
import io
import json
import unittest
from unittest import mock

from agentpet import hook, ipc, places
from agentpet.procs import Proc

from .helpers import FakeHome, Pets, posix_only


class FieldsTest(unittest.TestCase):
    def test_reads_the_fields_it_needs(self):
        raw = json.dumps({"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/w",
                          "tool_input": {"command": "echo secret"}}).encode()
        self.assertEqual(hook.fields(raw), {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash",
                                            "cwd": "/w"})

    def test_scans_a_payload_too_big_to_parse(self):
        raw = b'{"session_id":"s1","hook_event_name":"PostToolUse","tool_response":"' + b"x" * (hook.MAX_PARSE + 10) + b'"}'
        self.assertEqual(hook.fields(raw)["hook_event_name"], "PostToolUse")


class AncestryTest(unittest.TestCase):
    def table(self, *procs):
        t = {p.pid: p for p in procs}
        return lambda pid: t.get(pid)

    def test_finds_claude_and_the_terminal(self):
        look = self.table(Proc(300, "python3", 200, 5), Proc(200, "sh", 100, 4), Proc(100, "claude", 50, 3),
                          Proc(50, "ptyxis-agent", 1, 2))
        self.assertEqual(hook.ancestry(env={}, start=300, lookup=look), ("Ptyxis", 100, 3))

    def test_finds_the_npm_build_of_claude_code(self):
        look = self.table(Proc(300, "sh", 100, 5), Proc(100, "node", 50, 3, "node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"),
                          Proc(50, "kitty", 1, 2))
        self.assertEqual(hook.ancestry(env={}, start=300, lookup=look), ("kitty", 100, 3))

    def test_windows_terminal_and_vs_code(self):
        look = self.table(Proc(300, "python", 200, 5), Proc(200, "bash", 100, 4), Proc(100, "claude", 60, 3),
                          Proc(60, "pwsh", 50, 2), Proc(50, "windowsterminal", 4, 1))
        self.assertEqual(hook.ancestry(env={}, start=300, lookup=look), ("Windows Terminal", 100, 3))
        self.assertEqual(hook.ancestry(env={"TERM_PROGRAM": "vscode"}, start=300, lookup=look)[0], "VS Code")
        self.assertEqual(hook.ancestry(env={"TERM_PROGRAM": "Apple_Terminal"}, start=300, lookup=look)[0], "Terminal")

    def test_no_claude_above_means_no_process(self):
        look = self.table(Proc(300, "bash", 50, 5), Proc(50, "kitty", 1, 2))
        self.assertEqual(hook.ancestry(env={}, start=300, lookup=look), ("kitty", None, None))


@posix_only
class RunTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.home.__enter__()
        self.pets = Pets()

    def tearDown(self):
        self.pets.close()
        self.home.__exit__()

    def payload(self, **kw):
        return json.dumps({"session_id": "s1", **kw}).encode()

    def test_sends_event_session_tool_and_folder_only(self):
        hook.run("claude", self.payload(hook_event_name="PreToolUse", tool_name="Bash", cwd="/srv/app",
                                        tool_input={"command": "ls ~"}), env={})
        msg = json.loads(self.pets.wait(1)[0])
        self.assertEqual((msg["agent"], msg["event"], msg["session"], msg["tool"], msg["where"]),
                         ("claude", "PreToolUse", "s1", "Bash", "/srv/app"))
        self.assertNotIn("ls", json.dumps(msg))
        self.assertTrue(list(places.runtime_dir().glob("last-claude-*.json")))

    def test_ignores_other_notifications_and_unknown_events(self):
        self.assertIsNone(hook.run("claude", self.payload(hook_event_name="Notification", notification_type="idle_prompt"), env={}))
        self.assertIsNone(hook.run("claude", self.payload(hook_event_name="Setup"), env={}))
        self.assertIsNotNone(hook.run("claude", self.payload(hook_event_name="Notification", notification_type="permission_prompt"), env={}))

    def test_starts_the_pets_only_for_starting_events(self):
        self.pets.close()
        with mock.patch.object(ipc, "spawn_app") as spawn:
            hook.run("claude", self.payload(hook_event_name="PostToolUse"), env={})
            spawn.assert_not_called()
            hook.run("claude", self.payload(hook_event_name="UserPromptSubmit"), env={})
            spawn.assert_called_once()

    def test_main_prints_nothing_and_never_fails(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(hook, "run", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}"))):
            self.assertEqual(hook.main(["claude"]), 0)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("boom", places.log_path().read_text())


if __name__ == "__main__":
    unittest.main()
