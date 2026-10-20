import json
import os
import unittest

from agentpet import connect

from .helpers import FakeHome, Pets, posix_only


class Ctx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn


def load_plugin():
    ns = {}
    exec(compile(connect.plugin_source("/nonexistent/agentpet"), "plugin", "exec"), ns)
    ctx = Ctx()
    ns["register"](ctx)
    return ctx, ns


class PluginTest(unittest.TestCase):
    def test_registers_only_hooks_this_hermes_knows(self):
        ctx, _ = load_plugin()
        known = {"on_session_start", "pre_llm_call", "pre_tool_call", "post_tool_call", "pre_approval_request",
                 "post_approval_response", "subagent_start", "subagent_stop", "on_session_end", "on_session_finalize"}
        self.assertEqual(set(ctx.hooks), known)

    def test_folders_match_agentpets_own(self):
        from agentpet import places

        with FakeHome():
            _, ns = load_plugin()
            self.assertEqual(ns["_state_dir"](), os.fspath(places.state_dir()))
            self.assertEqual(ns["_channel"](), places.channel())

    def test_start_stamp_matches_psutil(self):
        from agentpet import procs

        _, ns = load_plugin()
        stamp = ns["_own_stamp"]()
        if stamp is not None:                      # Linux only
            self.assertLessEqual(abs(stamp - procs.info(os.getpid()).stamp), 2)


@posix_only
class HermesPluginTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        d = self.home.__enter__()
        os.environ["TERM_PROGRAM"] = "kitty"
        os.chdir(d)
        self.pets = Pets()
        self.ctx, self.ns = load_plugin()

    def tearDown(self):
        self.pets.close()
        os.environ.pop("TERM_PROGRAM", None)
        self.home.__exit__()

    def got(self, n):
        self.ns["_outbox"].join()              # the plugin sends from a background thread
        return [json.loads(line) for line in self.pets.wait(n)]

    def test_maps_hermes_hooks_to_agent_events(self):
        h = self.ctx.hooks
        h["on_session_start"](session_id="s1")
        h["pre_llm_call"](session_id="s1", messages=["secret prompt"])
        h["pre_tool_call"](session_id="s1", tool_name="terminal", args={"command": "ls"})
        h["post_tool_call"](session_id="s1", tool_name="terminal", result='{"error": "boom"}')
        h["pre_approval_request"](session_id="s1", command="rm -rf build", surface="cli")
        h["post_approval_response"](session_id="s1", command="rm -rf build", surface="cli", choice="once")
        h["on_session_end"](session_id="s1", completed=True)
        h["on_session_finalize"](session_id="s1")
        got = self.got(8)
        self.assertEqual([m["event"] for m in got], ["SessionStart", "UserPromptSubmit", "PreToolUse",
                                                     "PostToolUseFailure", "PermissionRequest", "PreToolUse",
                                                     "Stop", "SessionEnd"])
        self.assertTrue(all(m["agent"] == "hermes" and m["session"] == "s1" and m["app"] == "kitty" for m in got))
        self.assertTrue(all(m["pid"] == os.getpid() and m["where"] == "~" for m in got))     # it runs inside Hermes
        self.assertEqual(got[2]["tool"], "terminal")
        self.assertNotIn("secret", json.dumps(got))
        self.assertNotIn("rm -rf", json.dumps(got))

    def test_approvals_and_questions(self):
        h = self.ctx.hooks
        h["pre_approval_request"](session_id="s1", surface="smart")          # the aux model decides: not you
        h["pre_tool_call"](session_id="s1", tool_name="clarify")             # Hermes asks you something
        h["post_approval_response"](session_id="s1", surface="gateway", choice="deny")
        h["post_approval_response"](session_id="s1", surface="smart", choice="smart_approve")
        h["pre_tool_call"](session_id="s1", tool_name="read_file")
        self.assertEqual([m["event"] for m in self.got(3)], ["PermissionRequest", "UserPromptSubmit", "PreToolUse"])

    def test_subagent_work_belongs_to_its_parent(self):
        h = self.ctx.hooks
        h["subagent_start"](parent_session_id="p", child_session_id="c")
        h["pre_tool_call"](session_id="c", tool_name="read_file")
        self.assertEqual([m["session"] for m in self.got(2)], ["p", "p"])

    def test_no_pet_running_is_fine(self):
        self.pets.close()
        self.ctx.hooks["pre_tool_call"](session_id="s1", tool_name="terminal")   # must not raise
        self.ns["_outbox"].join()

    def test_hermes_never_waits(self):
        import time

        self.pets.close()
        start = time.monotonic()
        for _ in range(20):
            self.ctx.hooks["pre_tool_call"](session_id="s1", tool_name="terminal")
        self.assertLess(time.monotonic() - start, 0.05)
        self.ns["_outbox"].join()


if __name__ == "__main__":
    unittest.main()
