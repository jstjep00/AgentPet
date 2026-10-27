"""agentpet: desktop pets for your coding agents. Clawd reacts to Claude Code, Hermes to Hermes.

usage: agentpet [command]

  run                 start the pets (the hooks also start them when an agent gets busy)
  quit                stop the pets; they stay closed until you `run` them again
  connect [AGENT]     hook the pets into claude, hermes or all (default: all)
  disconnect [AGENT]  remove the hooks again
  status              what is connected and whether the pets are running
  demo [WHICH]        play every reaction once (claude, hermes or all); `demo climb` sends
                      them up the walls; `demo many` brings out five pets at once
  size SIZE           small, normal, large or huge (takes effect on the next run)
  sheet FILE.png      draw every reaction of both pets into one picture
  icon FILE.png       draw the app icon
  hook AGENT          (what the agent's hook runs; reads the event on stdin)
"""

from __future__ import annotations

import os
import sys
import time


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("run", [])
    if cmd == "hook":
        from .hook import main as hook

        return hook(rest)
    if cmd == "run":
        from . import places

        try:
            places.quit_flag().unlink()
        except FileNotFoundError:
            pass
        from .app import main as run

        return run(rest)
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    handler = {"quit": _quit, "connect": _connect, "disconnect": _disconnect, "status": _status,
               "demo": _demo, "size": _size, "sheet": _pictures("sheet"), "icon": _pictures("icon")}.get(cmd)
    if handler is None:
        print(f"agentpet: unknown command {cmd!r}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    return handler(rest)


def _agents(rest: list[str]) -> list[str]:
    which = (rest[0] if rest else "all").lower()
    if which in ("all", "both"):
        return ["claude", "hermes"]
    if which in ("claude", "clawd", "claude-code"):
        return ["claude"]
    if which == "hermes":
        return ["hermes"]
    raise SystemExit(f"agentpet: unknown agent {which!r} (claude, hermes or all)")


def _launcher() -> str:
    from . import ipc

    found = ipc.launcher()
    if found:
        return found
    raise SystemExit("agentpet: install it first (uv tool install, or pipx install), so the hooks have an "
                     "`agentpet` command to run")


def _connect(rest: list[str]) -> int:
    from . import connect

    launcher, code = _launcher(), 0
    for agent in _agents(rest):
        try:
            print(connect.connect_claude(launcher) if agent == "claude" else connect.connect_hermes(launcher))
        except connect.ConnectError as exc:
            print(f"{'Claude Code' if agent == 'claude' else 'Hermes'}: {exc}", file=sys.stderr)
            code = 1
    return code


def _disconnect(rest: list[str]) -> int:
    from . import connect

    code = 0
    for agent in _agents(rest):
        try:
            print(connect.disconnect_claude() if agent == "claude" else connect.disconnect_hermes())
        except connect.ConnectError as exc:
            print(f"{agent}: {exc}", file=sys.stderr)
            code = 1
    return code


def _status(_rest: list[str]) -> int:
    from . import config, connect, events, ipc, places

    running = ipc.send(events.encode({"cmd": "ping"}))
    print(f"pets:        {'running' if running else 'not running'}" + (" (quit by hand)" if places.quit_flag().exists() else ""))
    print(f"Claude Code: {'connected' if connect.claude_connected() else 'not connected'} ({connect.claude_settings()})")
    print(f"Hermes:      {'connected' if connect.hermes_connected() else 'not connected'} ({connect.hermes_plugin_dir()})")
    print(f"size:        {config.load()['pixel']} screen pixels per sprite pixel")
    return 0


def _quit(_rest: list[str]) -> int:
    from . import events, ipc, places

    places.state_dir().mkdir(parents=True, exist_ok=True)
    places.quit_flag().touch()
    sent = ipc.send(events.encode({"cmd": "quit"}))
    print("The pets are going to sleep. `agentpet run` brings them back." if sent else "The pets were not running.")
    return 0


def _size(rest: list[str]) -> int:
    from . import config

    if not rest or rest[0] not in config.SIZES:
        print(f"usage: agentpet size {'|'.join(config.SIZES)}", file=sys.stderr)
        return 2
    config.save({"pixel": config.SIZES[rest[0]]})
    print(f"Size set to {rest[0]}. Restart the pets to see it: agentpet quit; agentpet run")
    return 0


CLAUDE_DEMO = (
    (0.0, "SessionStart", None, "hello"),
    (3.0, "UserPromptSubmit", None, "thinking about your prompt"),
    (3.0, "PreToolUse", "Read", "working: reading"),
    (2.5, "PreToolUse", "Bash", "working: running a command"),
    (2.5, "PermissionRequest", "Bash", "needs you (click the pet!)"),
    (5.0, "PostToolUse", None, "thanks for approving"),
    (2.5, "PreToolUse", "Edit", "working: editing code"),
    (2.5, "PostToolUseFailure", None, "oops, a tool failed"),
    (2.5, "SubagentStart", None, "asking a helper"),
    (2.5, "PreCompact", None, "tidying up the conversation"),
    (2.5, "Stop", None, "done: confetti"),
    (4.0, "UserPromptSubmit", None, "thinking again"),
    (2.5, "StopFailure", None, "oh no, the turn failed"),
    (3.5, "Rare", None, "the rare surprise"),
    (3.5, "Flip", None, "the odd backflip"),
    (4.5, "SessionEnd", None, "goodbye"),
)
# Hermes's own script, in a different order, so the two pets are seen doing different things.
HERMES_DEMO = (
    (0.0, "SessionStart", None, "hello"),
    (2.0, "UserPromptSubmit", None, "thinking about your prompt"),
    (3.5, "PreToolUse", "web_search", "working: browsing the web"),
    (3.0, "PreToolUse", "terminal", "working: running a command"),
    (3.0, "PostToolUseFailure", None, "oops, a tool failed"),
    (3.0, "PermissionRequest", "terminal", "needs you (click the pet!)"),
    (5.5, "PostToolUse", None, "thanks for approving"),
    (2.5, "SubagentStart", None, "asking a helper"),
    (3.0, "Stop", None, "done: sparkles and confetti"),
    (4.0, "UserPromptSubmit", None, "thinking again"),
    (3.0, "PreCompact", None, "tidying up the conversation"),
    (2.5, "StopFailure", None, "oh no, the turn failed"),
    (3.5, "Rare", None, "the rare surprise"),
    (3.5, "Flip", None, "the odd backflip"),
    (4.5, "SessionEnd", None, "goodbye"),
)
CLIMB_DEMO = (
    (0.0, "SessionStart", None, "hello"),
    (2.0, "Climb", None, "off up the wall, over the top, and... bonk"),
    (45.0, "SessionEnd", None, "goodbye (or pick them up and move them first!)"),
)
MANY = (("claude", "~/projects/webapp"), ("claude", "~/projects/api"), ("claude", "~/notes"),
        ("hermes", "~/research"), ("hermes", "~/projects/api"))
MANY_EVENTS = (("UserPromptSubmit", None), ("PreToolUse", "Bash"), ("PreToolUse", "Edit"), ("PreToolUse", "Read"),
               ("PermissionRequest", "Bash"), ("PostToolUse", None), ("Stop", None), ("PreToolUse", "terminal"))


def _start_pets() -> bool:
    from . import events, ipc, places

    if ipc.send(events.encode({"cmd": "ping"})):
        return True
    try:
        places.quit_flag().unlink()
    except FileNotFoundError:
        pass
    if not ipc.spawn_app():
        print("agentpet: no desktop to show the pets on", file=sys.stderr)
        return False
    for _ in range(100):
        time.sleep(0.1)
        if ipc.send(events.encode({"cmd": "ping"})):
            return True
    print(f"agentpet: the pets did not start; see {places.log_path()}", file=sys.stderr)
    return False


def _demo(rest: list[str]) -> int:
    """agentpet demo [claude|hermes|all|climb|many]"""
    import threading

    from . import events, ipc, procs

    which = (rest[0] if rest else "all").lower()
    if not _start_pets():
        return 1
    if which == "many":
        return _demo_many()
    agents = _agents(["all" if which == "climb" else which])
    # The demo stands in for the agents: the pets watch this process and leave when it ends,
    # just as they leave when a real agent exits (even on Ctrl-C).
    me = os.getpid()
    st = procs.info(me)
    names = {"claude": "Clawd", "hermes": "Hermes"}
    scripts = {"claude": CLAUDE_DEMO, "hermes": HERMES_DEMO}
    if which == "climb":
        scripts = {"claude": CLIMB_DEMO, "hermes": CLIMB_DEMO}
    lock = threading.Lock()

    def play(agent: str, offset: float) -> None:
        time.sleep(offset)
        for delay, event, tool, what in scripts[agent]:
            time.sleep(delay)
            ipc.send(events.encode(events.message(agent, event, f"demo-{agent}", tool, "Terminal",
                                                  pid=me, pid_start=st.stamp if st else None, where="the demo")))
            with lock:
                print(f"{names[agent]:<7} {what}", flush=True)

    threads = [threading.Thread(target=play, args=(a, 1.5 * i), daemon=True) for i, a in enumerate(agents)]
    for t in threads:
        t.start()
    try:
        for t in threads:
            while t.is_alive():
                t.join(0.2)
    except KeyboardInterrupt:
        print("stopped; the pets leave in a moment")
    return 0


def _demo_many() -> int:
    """Five agent windows at once: three Claude Codes and two Hermes, each its own pet. Each stand-in
    is a child process, so each pet leaves when its own process ends."""
    import random
    import subprocess

    from . import events, ipc, procs

    rnd = random.Random()
    kids = []
    try:
        for agent, where in MANY:
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            st = procs.info(child.pid)
            kids.append((agent, where, child, st.stamp if st else None))
            ipc.send(events.encode(events.message(agent, "SessionStart", f"many-{child.pid}", None, "Terminal",
                                                  pid=child.pid, pid_start=st.stamp if st else None, where=where)))
            print(f"{'Clawd' if agent == 'claude' else 'Hermes':<7} in {where}", flush=True)
            time.sleep(0.6)
        print("Click a pet to see which window it belongs to; drag them around.", flush=True)
        for _ in range(14):
            time.sleep(2.5)
            agent, where, child, start = rnd.choice(kids)
            event, tool = rnd.choice(MANY_EVENTS)
            if agent == "hermes" and tool in ("Bash", "Edit", "Read"):
                tool = {"Bash": "terminal", "Edit": "patch", "Read": "read_file"}[tool]
            ipc.send(events.encode(events.message(agent, event, f"many-{child.pid}", tool, "Terminal",
                                                  pid=child.pid, pid_start=start, where=where)))
        for agent, where, child, _start in kids:
            time.sleep(1.0)
            child.terminate()
            print(f"{where} closed", flush=True)
    except KeyboardInterrupt:
        print("stopped; the pets leave in a moment")
    finally:
        for _agent, _where, child, _start in kids:
            child.kill()
            child.wait()
    return 0


def _pictures(what: str):
    def run(rest: list[str]) -> int:
        if not rest:
            print(f"usage: agentpet {what} FILE.png", file=sys.stderr)
            return 2
        from . import pictures

        getattr(pictures, what)(rest[0])
        print(rest[0])
        return 0
    return run
