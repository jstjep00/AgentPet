"""`agentpet connect` and `disconnect`: hooking the pets into Claude Code and Hermes.

Claude Code: one command handler per event in ~/.claude/settings.json ($CLAUDE_CONFIG_DIR).
Every other key and hook is kept, the file is backed up first (settings.json.agentpet-backup-
<time>), a file that is not valid JSON is left alone, and connecting twice changes nothing.

Hermes: a plugin folder this app owns, ~/.hermes/plugins/agentpet ($HERMES_HOME), switched on
and off with `hermes plugins enable|disable agentpet`.

Handlers and plugins of the earlier `agentpets` name are recognised too, and replaced.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import places

PLUGIN = "agentpet"
OLD_PLUGIN = "agentpets"

# (event, matcher): None for events that take no matcher
CLAUDE_EVENTS = (("SessionStart", None), ("UserPromptSubmit", None), ("PreToolUse", "*"),
                 ("PostToolUse", "*"), ("PostToolUseFailure", "*"), ("PermissionRequest", "*"),
                 ("Notification", "permission_prompt"), ("SubagentStart", None), ("SubagentStop", None),
                 ("Stop", None), ("StopFailure", None), ("PreCompact", None), ("SessionEnd", None))
_OURS = re.compile(r"""agentpets?(?:\.exe)?['"]?\s+hook\s+claude\s*$""", re.I)

HERMES_MANIFEST = """\
# AgentPet: a desktop pet that reacts to what Hermes Agent is doing.
# Written by `agentpet connect hermes`; removed by `agentpet disconnect hermes`.
name: agentpet
version: "1.0.0"
description: "AgentPet: a desktop pet that reacts to what Hermes Agent is doing."
author: AgentPet
provides_hooks:
  - on_session_start
  - pre_llm_call
  - pre_tool_call
  - post_tool_call
  - pre_approval_request
  - post_approval_response
  - subagent_start
  - subagent_stop
  - on_session_end
  - on_session_finalize
"""


class ConnectError(Exception):
    pass


# ---------------------------------------------------------------- Claude Code

def claude_settings() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return Path(base) / "settings.json"


def hook_command(launcher: str) -> str:
    """The command Claude Code runs. Forward slashes, so it reads the same to cmd, PowerShell and
    the Git Bash Claude Code uses on Windows."""
    return '"{}" hook claude'.format(launcher.replace("\\", "/") if places.WINDOWS else launcher)


def is_ours(handler) -> bool:
    return (isinstance(handler, dict) and handler.get("type") == "command"
            and isinstance(handler.get("command"), str) and bool(_OURS.search(handler["command"])))


def strip_claude_hooks(settings: dict) -> dict:
    """The settings without this app's handlers. Groups and events left empty by that go too;
    nothing else changes."""
    s = copy.deepcopy(settings)
    hooks = s.get("hooks")
    if not isinstance(hooks, dict):
        return s
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list) and any(is_ours(h) for h in handlers):
                rest = [h for h in handlers if not is_ours(h)]
                if rest:
                    kept.append({**group, "hooks": rest})
            else:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del s["hooks"]
    return s


def add_claude_hooks(settings: dict, command: str) -> dict:
    s = strip_claude_hooks(settings)
    hooks = s.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ConnectError('"hooks" in settings.json is not an object; not touching it')
    for event, matcher in CLAUDE_EVENTS:
        group: dict = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        if matcher is not None:
            group = {"matcher": matcher, **group}
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ConnectError(f'hooks.{event} in settings.json is not a list; not touching it')
        groups.append(group)
    return s


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ConnectError(f"{path} is not valid JSON ({exc}); not touching it") from exc
    if not isinstance(data, dict):
        raise ConnectError(f"{path} is not a JSON object; not touching it")
    return data


def _save(path: Path, data: dict) -> Path | None:
    """Writes atomically after backing the old file up; returns the backup."""
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.agentpet-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.agentpet-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if path.exists():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)
    return backup


def connect_claude(launcher: str, path: Path | None = None) -> str:
    path = path or claude_settings()
    data = _load(path)
    new = add_claude_hooks(data, hook_command(launcher))
    if new == data:
        return "Claude Code: already connected"
    backup = _save(path, new)
    return "Claude Code: connected" + (f" (backup: {backup.name})" if backup else "") + \
        ". New Claude Code sessions pick it up; running ones after /hooks or a restart."


def disconnect_claude(path: Path | None = None) -> str:
    path = path or claude_settings()
    data = _load(path)
    new = strip_claude_hooks(data)
    if new == data:
        return "Claude Code: not connected"
    backup = _save(path, new)
    return "Claude Code: disconnected" + (f" (backup: {backup.name})" if backup else "")


def claude_connected(path: Path | None = None) -> bool:
    try:
        hooks = _load(path or claude_settings()).get("hooks") or {}
    except ConnectError:
        return False
    return all(any(is_ours(h) for g in hooks.get(e, []) if isinstance(g, dict) for h in g.get("hooks", []))
               for e, _ in CLAUDE_EVENTS)


# ---------------------------------------------------------------- Hermes

def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes"))


def hermes_plugin_dir(name: str = PLUGIN) -> Path:
    return hermes_home() / "plugins" / name


def hermes_executable() -> str | None:
    found = shutil.which("hermes")
    if found:
        return found
    p = Path(os.path.expanduser("~/.local/bin/hermes"))
    return str(p) if p.is_file() and os.access(p, os.X_OK) else None


def plugin_source(launcher: str) -> str:
    template = (Path(__file__).with_name("hermes_plugin.py")).read_text(encoding="utf-8")
    if '["__LAUNCHER__"]' not in template:
        raise ConnectError("the Hermes plugin template is damaged")
    return template.replace('["__LAUNCHER__"]', json.dumps([launcher]))


def _hermes(args: list[str], run=subprocess.run) -> tuple[int, str]:
    exe = hermes_executable()
    if exe is None:
        return 127, "hermes not found"
    try:
        r = run([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=60, env={**os.environ, "NO_COLOR": "1"})
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return r.returncode, (r.stdout or b"").decode("utf-8", "replace")


def connect_hermes(launcher: str, run=subprocess.run) -> str:
    if not hermes_home().is_dir() and hermes_executable() is None:
        raise ConnectError("Hermes is not installed (no ~/.hermes and no hermes command)")
    d = hermes_plugin_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text(plugin_source(launcher), encoding="utf-8")
    (d / "plugin.yaml").write_text(HERMES_MANIFEST, encoding="utf-8")
    if hermes_plugin_dir(OLD_PLUGIN).exists():             # the earlier name: replaced by this one
        _hermes(["plugins", "disable", OLD_PLUGIN], run)
        shutil.rmtree(hermes_plugin_dir(OLD_PLUGIN))
    code, out = _hermes(["plugins", "enable", PLUGIN], run)
    if code != 0:
        last = [l for l in out.splitlines() if l.strip()][-1:] or ["no output"]
        return f"Hermes: plugin written to {d}, but `hermes plugins enable {PLUGIN}` failed: {last[0]}"
    return "Hermes: connected. New Hermes sessions pick it up."


def disconnect_hermes(run=subprocess.run) -> str:
    found = [n for n in (PLUGIN, OLD_PLUGIN) if hermes_plugin_dir(n).exists()]
    if not found:
        return "Hermes: not connected"
    for name in found:
        _hermes(["plugins", "disable", name], run)
        shutil.rmtree(hermes_plugin_dir(name))
    return "Hermes: disconnected"


def hermes_connected() -> bool:
    if not (hermes_plugin_dir() / "__init__.py").is_file():
        return False
    try:
        text = (hermes_home() / "config.yaml").read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r"^plugins:\s*\n((?:[ \t]+.*\n?)*)", text, re.M)
    block = m.group(1) if m else ""
    en = re.search(r"^[ \t]+enabled:\s*\n((?:[ \t]+-.*\n?)*)", block, re.M)
    return bool(en and re.search(rf"^[ \t]+-\s*['\"]?{PLUGIN}['\"]?\s*$", en.group(1), re.M))
