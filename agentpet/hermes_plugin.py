# AgentPet - the Hermes pet reacts to what Hermes Agent is doing.
#
# Written by `agentpet connect hermes`; `agentpet disconnect hermes` removes it. Each hook sends
# the event name, the session id, the tool name and the folder Hermes works in to the pets over a
# private local channel. Prompts, code, model output and command text never leave this file, and
# nothing goes over the network. Every hook returns None, so Hermes behaves exactly as without it.
#
# The mapping of Hermes's plugin hooks onto agent events follows ThatPet's Hermes plugin (MIT).

import getpass
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time

# How to start the pets when they are not running (filled in on connect).
LAUNCHER = ["__LAUNCHER__"]
STARTERS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest"}
WINDOWS = os.name == "nt"
MACOS = sys.platform == "darwin"

# Subagents run under their own session ids; their work belongs to the session that started them.
_parents = {}
_lock = threading.Lock()


# -- where things are: the same places as agentpet/places.py ------------------------------------

def _state_dir():
    home = os.path.expanduser("~")
    if WINDOWS:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), "AgentPet")
    if MACOS:
        return os.path.join(home, "Library", "Application Support", "AgentPet")
    base = os.environ.get("XDG_STATE_HOME", "")
    return os.path.join(base if os.path.isabs(base) else os.path.join(home, ".local", "state"), "agentpet")


def _runtime_dir():
    base = os.environ.get("XDG_RUNTIME_DIR", "") if not (WINDOWS or MACOS) else ""
    if os.path.isabs(base) and os.path.isdir(base):
        d = os.path.join(base, "agentpet")
    else:
        d = os.path.join(_state_dir(), "run")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _channel():
    if WINDOWS:
        user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
        return "\\\\.\\pipe\\agentpet-" + user
    return os.path.join(_runtime_dir(), "pets.sock")


def _send(data):
    line = data + b"\n"
    if WINDOWS:
        try:
            with open(_channel(), "wb", buffering=0) as pipe:
                pipe.write(line)
            return True
        except OSError:
            return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(_channel())
        s.sendall(line)
        return True
    except OSError:
        return False
    finally:
        s.close()


# -- this Hermes: its process, terminal tab and folder ------------------------------------------

def _own_stamp():
    """This process's start time in 1/100 s since the epoch, as psutil gives it (Linux only)."""
    try:
        with open("/proc/self/stat", "rb") as f:
            ticks = int(f.read().rpartition(b")")[2].split()[19])
        with open("/proc/stat", "rb") as f:
            btime = next(int(line.split()[1]) for line in f if line.startswith(b"btime"))
        return int(round((btime + ticks / os.sysconf("SC_CLK_TCK")) * 100))
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def _own_tty():
    try:
        name = os.ttyname(0)
    except (OSError, AttributeError):
        return None
    return name[5:] if name.startswith("/dev/") else None


def _short_path(path):
    path = path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/").rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        path = "~" + path[len(home):]
    if len(path) > 32:
        path = ".../" + "/".join([p for p in path.split("/") if p][-2:])
    return path[:48]


_STAMP = _own_stamp()
_TTY = _own_tty()


def _spawn():
    if not WINDOWS and not MACOS and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    if os.path.exists(os.path.join(_state_dir(), "quit")) or not os.path.isfile(LAUNCHER[0]):
        return
    kw = {"creationflags": 0x00000008 | 0x00000200} if WINDOWS else {"start_new_session": True}
    subprocess.Popen([*LAUNCHER, "run"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, **kw)


# Hermes never waits on the pets: reports go out in order from one background thread.
_outbox = queue.Queue()
_worker = []


def _deliver():
    while True:
        event, data = _outbox.get()
        try:
            d = _runtime_dir()
            name = "last-hermes-%d.json" % os.getpid()
            tmp = os.path.join(d, "." + name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(d, name))
            if not _send(data) and event in STARTERS:
                _spawn()
        except Exception:
            pass  # A missing desktop pet must never disturb Hermes.
        finally:
            _outbox.task_done()


def _report(event, session=None, tool=None):
    try:
        msg = {"v": 1, "agent": "hermes", "event": event, "ts": int(time.time() * 1000)}
        if isinstance(session, str) and session:
            msg["session"] = session[:128]
        if isinstance(tool, str) and tool:
            msg["tool"] = tool[:64]
        if os.environ.get("TERM_PROGRAM"):
            msg["app"] = os.environ["TERM_PROGRAM"][:40]
        elif os.environ.get("WT_SESSION"):
            msg["app"] = "Windows Terminal"
        # This plugin runs inside Hermes, so this process is Hermes: the pets watch it and the
        # Hermes pet leaves when Hermes stops, however it stops.
        msg["pid"] = os.getpid()
        if _STAMP is not None:
            msg["pid_start"] = _STAMP
        msg["where"] = _short_path(os.getcwd())
        if _TTY:
            msg["tty"] = _TTY
        _outbox.put((event, json.dumps(msg).encode("utf-8")))
        with _lock:
            if not _worker:
                t = threading.Thread(target=_deliver, name="agentpet", daemon=True)
                t.start()
                _worker.append(t)
    except Exception:
        pass  # A missing desktop pet must never disturb Hermes.


# -- Hermes's hooks -------------------------------------------------------------------------------

def _session(kw):
    for key in ("session_id", "session_key", "task_id"):
        value = kw.get(key)
        if isinstance(value, str) and value:
            with _lock:
                return _parents.get(value, value)
    return None


def _subagent(kw):
    return kw.get("platform") == "subagent"


def _on_session_start(**kw):
    if not _subagent(kw):
        _report("SessionStart", _session(kw))


def _pre_llm_call(**kw):
    if not _subagent(kw) and not kw.get("parent_session_id"):
        _report("UserPromptSubmit", _session(kw))


def _pre_tool_call(**kw):
    tool = kw.get("tool_name")
    # `clarify` is Hermes asking you a question: that needs you as much as an approval does.
    _report("PermissionRequest" if tool == "clarify" else "PreToolUse", _session(kw), tool)


def _post_tool_call(**kw):
    failed = False
    result = kw.get("result")
    if isinstance(result, str) and '"error"' in result:
        try:
            parsed = json.loads(result)
            failed = isinstance(parsed, dict) and bool(parsed.get("error"))
        except ValueError:
            pass
    _report("PostToolUseFailure" if failed else "PostToolUse", _session(kw))


def _pre_approval_request(**kw):
    # A dangerous command waits for a decision. "smart" approvals are decided by Hermes's
    # auxiliary model, not by you, so they don't call you over.
    if kw.get("surface") != "smart":
        _report("PermissionRequest", _session(kw), "terminal")


def _post_approval_response(**kw):
    if kw.get("surface") == "smart":
        return
    if kw.get("choice") in ("once", "session", "always"):
        _report("PreToolUse", _session(kw), "terminal")      # approved: thanks, then the command runs
    else:
        _report("UserPromptSubmit", _session(kw))            # denied or timed out: back to thinking


def _subagent_start(**kw):
    parent, child = kw.get("parent_session_id"), kw.get("child_session_id")
    if not (isinstance(parent, str) and parent):
        return
    with _lock:
        root = _parents.get(parent, parent)
        if isinstance(child, str) and child:
            _parents[child] = root
    _report("SubagentStart", root)


def _subagent_stop(**kw):
    parent, child = kw.get("parent_session_id"), kw.get("child_session_id")
    if not (isinstance(parent, str) and parent):
        return
    with _lock:
        root = _parents.get(parent, parent)
        if isinstance(child, str):
            _parents.pop(child, None)
    _report("SubagentStop", root)


def _on_session_end(**kw):
    if _subagent(kw):
        return
    if kw.get("failed"):
        event = "StopFailure"
    elif kw.get("interrupted"):
        event = "SessionStart"  # the person stopped the turn: back to idle
    elif kw.get("completed"):
        event = "Stop"
    else:
        event = "StopFailure"
    _report(event, _session(kw))


def _on_session_finalize(**kw):
    if not _subagent(kw):
        _report("SessionEnd", _session(kw))


def register(ctx):
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("pre_approval_request", _pre_approval_request)
    ctx.register_hook("post_approval_response", _post_approval_response)
    ctx.register_hook("subagent_start", _subagent_start)
    ctx.register_hook("subagent_stop", _subagent_stop)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_finalize", _on_session_finalize)
