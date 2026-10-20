"""What the agents tell the pets: event names, the bubble text for each tool and the message a hook
sends. The hook imports this on every agent event, so it imports nothing but json and re.

Hermes's plugin reports its hooks under Claude Code's event names, so one table serves both.
Messages carry the event, a session id, a tool name and the terminal's name, nothing else: no
prompts, file paths, commands or output.
"""

from __future__ import annotations

import json
import os
import re
import time

AGENTS = {"claude": "clawd", "hermes": "hermes"}      # agent -> the pet that reacts to it
NAMES = {"clawd": "Clawd", "hermes": "Hermes"}
AGENT_NAMES = {"claude": "Claude Code", "hermes": "Hermes"}

# agent event -> reaction
EVENTS = {
    "SessionStart": "session_start",
    "UserPromptSubmit": "prompt",
    "PreToolUse": "tool",
    "PostToolUse": "tool_done",
    "PostToolUseFailure": "tool_failed",
    "PermissionRequest": "needs_you",
    "Notification": "needs_you",          # hooked only for permission prompts
    "SubagentStart": "helper",
    "SubagentStop": "helper_done",
    "Stop": "done",
    "StopFailure": "failed",
    "PreCompact": "compact",
    "SessionEnd": "session_end",
}
# Events that start the pet app when it is not running (the others only matter to a running one).
STARTERS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest", "Notification"}
# Only `agentpets demo` sends these.
DEMO_EVENTS = {"Rare": "rare", "Climb": "climb"}

_SAFE = re.compile(r"[^A-Za-z0-9_.:+-]")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.:+-]")      # a terminal's name may have spaces ("VS Code")
_SAFE_PATH = re.compile(r"[^A-Za-z0-9 _.:+~/-]")
_TTY = re.compile(r"(pts/[0-9]{1,6}|ttys?[0-9]{1,4})")      # Linux pts/3, macOS ttys003

_LABELS = (
    ({"Bash", "BashOutput", "KillShell", "terminal", "process", "execute_code", "shell", "run_command"}, "Running a command…"),
    ({"Edit", "MultiEdit", "Write", "NotebookEdit", "write_file", "patch", "edit_file"}, "Editing code…"),
    ({"Read", "NotebookRead", "read_file", "view"}, "Reading…"),
    ({"Grep", "Glob", "LS", "search_files", "search"}, "Searching…"),
    ({"WebFetch", "WebSearch", "web_search", "web_extract"}, "Browsing the web…"),
    ({"Task", "Agent", "delegate_task"}, "Asking a helper…"),
    ({"TodoWrite", "TaskCreate", "TaskUpdate", "todo"}, "Planning…"),
    ({"image_generate"}, "Making an image…"),
    ({"memory"}, "Remembering…"),
    ({"Skill", "skill_view", "skills_list"}, "Using a skill…"),
)


def clean(value, limit: int = 64, spaces: bool = False) -> str | None:
    """A tool, session or app name cut to safe characters, or None."""
    if not isinstance(value, str):
        return None
    v = (_SAFE_NAME if spaces else _SAFE).sub("_", value)[:limit].strip()
    return v or None


def tool_label(tool: str | None) -> str:
    if not tool:
        return "Working…"
    for names, label in _LABELS:
        if tool in names:
            return label
    if tool.startswith("browser_"):
        return "Browsing the web…"
    if tool.startswith("mcp__"):
        server = tool.split("__")[1] if tool.count("__") >= 2 else "a tool"
        return f"Using {server[:16]}…"
    return f"Using {tool[:18]}…"


def short_path(path: str | None, home: str | None = None) -> str | None:
    """A folder for a bubble: home as ~, and only its last two parts when it is long."""
    if not path:
        return None
    path = path.replace("\\", "/")                    # Windows: C:\Users\me\x -> C:/Users/me/x
    home = (home if home is not None else os.path.expanduser("~")).replace("\\", "/").rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        path = "~" + path[len(home):]
    if len(path) > 32:
        path = ".../" + "/".join([p for p in path.split("/") if p][-2:])
    return path[:48]


def message(agent: str, event: str, session=None, tool=None, app=None, now_ms: int | None = None,
            pid: int | None = None, pid_start: int | None = None, where: str | None = None,
            tty: str | None = None) -> dict:
    """pid and pid_start: the agent's own process and its start time, so the pets can tell when
    the agent is no longer running however it ended."""
    msg = {"v": 1, "agent": agent, "event": event, "ts": int(time.time() * 1000) if now_ms is None else now_ms}
    if _pid_ok(pid):
        msg["pid"] = pid
        if _start_ok(pid_start):
            msg["pid_start"] = pid_start
    _window(msg, where, tty)
    for key, value, limit in (("session", session, 128), ("tool", tool, 64), ("app", app, 40)):
        v = clean(value, limit, spaces=key == "app")
        if v:
            msg[key] = v
    return msg


def encode(msg: dict) -> bytes:
    return json.dumps(msg, separators=(",", ":")).encode("utf-8")


def decode(data: bytes) -> dict | None:
    """A message from a hook, checked; None for anything else. Commands from the CLI
    ({"cmd": "quit"}) pass through as they are."""
    try:
        msg = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict):
        return None
    if msg.get("cmd") in ("quit", "ping"):
        return {"cmd": msg["cmd"]}
    if msg.get("agent") not in AGENTS or not (msg.get("event") in EVENTS or msg.get("event") in DEMO_EVENTS):
        return None
    out = {"agent": msg["agent"], "event": msg["event"],
           "ts": msg["ts"] if isinstance(msg.get("ts"), int) else int(time.time() * 1000)}
    for key, limit in (("session", 128), ("tool", 64), ("app", 40)):
        v = clean(msg.get(key), limit, spaces=key == "app")
        if v:
            out[key] = v
    if _pid_ok(msg.get("pid")):
        out["pid"] = msg["pid"]
        if _start_ok(msg.get("pid_start")):
            out["pid_start"] = msg["pid_start"]
    _window(out, msg.get("where"), msg.get("tty"))
    return out


def _window(msg: dict, where, tty) -> None:
    """Which window the agent is in: its folder (home as ~) and its terminal tab."""
    if isinstance(where, str) and where:
        msg["where"] = _SAFE_PATH.sub("_", where)[:48]
    if isinstance(tty, str) and _TTY.fullmatch(tty):
        msg["tty"] = tty


def _pid_ok(pid) -> bool:
    return isinstance(pid, int) and not isinstance(pid, bool) and 1 < pid < 1 << 22


def _start_ok(start) -> bool:
    return isinstance(start, int) and not isinstance(start, bool) and start >= 0


def reaction(event: str) -> str | None:
    return EVENTS.get(event) or DEMO_EVENTS.get(event)
