"""`agentpet hook claude`: what Claude Code runs on each hook event.

Reads the event's JSON on stdin, keeps the event name, the session id, the tool name and the
folder, and sends them to the pets. It prints nothing (Claude Code adds a SessionStart or
UserPromptSubmit hook's output to the conversation), always exits 0 and never waits on the pets.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

from . import events, ipc, places

MAX_PARSE = 4 * 1024 * 1024     # bigger payloads (a huge tool result) are scanned, not parsed
_FIELD = re.compile(rb'"(hook_event_name|session_id|tool_name|notification_type|cwd)"\s*:\s*"((?:[^"\\]|\\.){0,400})"')
_KEYS = ("hook_event_name", "session_id", "tool_name", "notification_type", "cwd")

# Processes between the hook and the terminal the agent runs in.
_SKIP = set("""sh bash zsh fish dash ksh tcsh csh nu xonsh env node nodejs bun deno claude hermes
    agentpet python python3 pythonw py sudo doas su script login timeout nice nohup setsid uv uvx npx npm
    pnpm yarn tmux screen zellij direnv nix flatpak-spawn bwrap cmd powershell pwsh conhost openconsole
    git-bash mintty wsl wslhost winpty""".split())
_FRIENDLY = {"ptyxis": "Ptyxis", "ptyxis-agent": "Ptyxis", "gnome-terminal-server": "Terminal", "kgx": "Console",
             "code": "VS Code", "vscode": "VS Code", "cursor": "Cursor", "kitty": "kitty", "alacritty": "Alacritty",
             "wezterm-gui": "WezTerm", "wezterm": "WezTerm", "ghostty": "Ghostty", "konsole": "Konsole",
             "tilix": "Tilix", "terminator": "Terminator", "xterm": "XTerm", "foot": "foot", "zed": "Zed",
             "warp": "Warp", "warpterminal": "Warp", "windowsterminal": "Windows Terminal",
             "apple_terminal": "Terminal", "terminal": "Terminal", "iterm.app": "iTerm2", "iterm2": "iTerm2",
             "tabby": "Tabby", "hyper": "Hyper"}


def fields(raw: bytes) -> dict:
    """hook_event_name, session_id, tool_name, notification_type and cwd from the payload."""
    if len(raw) <= MAX_PARSE:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {k: data[k] for k in _KEYS if isinstance(data.get(k), str)}
        except (ValueError, UnicodeDecodeError):
            pass
    out: dict = {}
    for key, value in _FIELD.findall(raw[:65536]):
        out.setdefault(key.decode(), value.decode("utf-8", "replace"))
    return out


def _is_claude(p) -> bool:
    """Claude Code's own process: the native build runs as `claude`; the npm one is node running
    @anthropic-ai/claude-code."""
    return p.name == "claude" or (p.name in ("node", "nodejs", "bun") and "claude-code" in p.cmdline)


def ancestry(env=None, start: int | None = None, lookup=None) -> tuple[str | None, int | None, int | None]:
    """(terminal, agent pid, agent start stamp) from the processes above the hook: the agent is the
    first Claude Code process, the terminal (or editor) the first one that is not a shell,
    launcher or agent. TERM_PROGRAM (or Windows Terminal's WT_SESSION) names the terminal when set.
    `lookup(pid)` returns a procs.Proc (tests pass their own)."""
    env = os.environ if env is None else env
    if lookup is None:
        from . import procs

        def lookup(pid):
            return procs.info(pid, with_cmdline=True)

    app = None
    if env.get("TERM_PROGRAM"):
        app = _FRIENDLY.get(env["TERM_PROGRAM"].lower(), env["TERM_PROGRAM"])
    elif env.get("WT_SESSION"):
        app = "Windows Terminal"
    agent = agent_start = None
    pid = os.getppid() if start is None else start
    for _ in range(20):
        if pid is None or pid <= 1:
            break
        p = lookup(pid)
        if p is None:
            break
        if p.name in ("sshd", "systemd", "init", "launchd", "explorer", "services", "wininit"):
            break
        if agent is None and _is_claude(p):
            agent, agent_start = pid, p.stamp
        elif app is None and p.name not in _SKIP and not p.name.startswith("python") and not p.name[:1].isdigit():
            app = _FRIENDLY.get(p.name, p.name)
        if app is not None and agent is not None:
            break
        pid = p.parent
    return app, agent, agent_start


def run(agent: str, raw: bytes, env=None) -> dict | None:
    """Sends the event; returns the message sent (None when the event is not one the pets use)."""
    f = fields(raw)
    event = f.get("hook_event_name", "")
    if event not in events.EVENTS:
        return None
    if event == "Notification" and f.get("notification_type", "permission_prompt") != "permission_prompt":
        return None
    from . import procs

    tool = f.get("tool_name") if event in ("PreToolUse", "PermissionRequest") else None
    app, pid, pid_start = ancestry(env)
    msg = events.message(agent, event, f.get("session_id"), tool, app, pid=pid, pid_start=pid_start,
                         where=events.short_path(f.get("cwd")), tty=procs.terminal(pid))
    data = events.encode(msg)
    ipc.write_last(agent, data, pid or "x")
    if not ipc.send(data) and event in events.STARTERS:
        ipc.spawn_app(env)
    return msg


def main(argv: list[str]) -> int:
    agent = argv[0] if argv else "claude"
    try:
        if agent not in events.AGENTS:
            return 0
        stdin = sys.stdin.buffer if sys.stdin is not None and not sys.stdin.isatty() else None
        run(agent, stdin.read() if stdin else b"")
    except Exception as exc:                 # never break the agent
        try:
            places.state_dir().mkdir(parents=True, exist_ok=True)
            with open(places.log_path(), "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} hook {agent}: {exc!r}\n")
        except OSError:
            pass
    return 0
