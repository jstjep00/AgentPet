"""How a hook reaches the running pets: one line of JSON over a private local channel (a Unix
socket, or a named pipe on Windows; see places), plus the last event of each agent instance in a
small file, so a pet app that starts late (or restarts) knows what is going on.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import places

_DETACHED_PROCESS, _NEW_PROCESS_GROUP = 0x00000008, 0x00000200


def send(data: bytes, timeout: float = 0.3) -> bool:
    """One message to the running pets; False when they are not running. Never waits long."""
    line = data.rstrip(b"\n") + b"\n"
    if places.WINDOWS:
        deadline = time.monotonic() + timeout
        while True:
            try:
                with open(places.channel(), "wb", buffering=0) as pipe:
                    pipe.write(line)
                return True
            except FileNotFoundError:
                return False
            except OSError:                    # every pipe instance busy: try again shortly
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.02)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(places.channel())
            s.sendall(line)
        finally:
            s.close()
        return True
    except OSError:
        return False


def write_last(agent: str, data: bytes, instance: object = "x") -> None:
    """Keeps an agent instance's last event (instance: its process id)."""
    d = places.runtime_dir()
    tmp = d / f".last-{agent}-{instance}.{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, d / f"last-{agent}-{instance}.json")


def read_all_last(max_age_s: float, now: float | None = None) -> list[tuple[Path, dict]]:
    """Every instance's last event younger than max_age_s; older ones are deleted."""
    now = time.time() if now is None else now
    out = []
    for p in sorted(places.runtime_dir(create=False).glob("last-*.json")):
        try:
            msg = json.loads(p.read_bytes())
        except (OSError, ValueError):
            forget(p)
            continue
        if not isinstance(msg, dict) or not isinstance(msg.get("ts"), int) or now - msg["ts"] / 1000 > max_age_s:
            forget(p)
            continue
        out.append((p, msg))
    return out


def forget(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def launcher() -> str | None:
    """The installed `agentpet` command: what the agents' hooks run."""
    a0 = sys.argv[0] if sys.argv else ""
    if os.path.basename(a0).lower() in ("agentpet", "agentpet.exe") and os.path.isfile(a0):
        return os.path.abspath(a0)
    return shutil.which("agentpet")


def can_show(env=None) -> bool:
    """Is there a desktop to show the pets on (not an SSH session, not a headless box)?"""
    env = os.environ if env is None else env
    if env.get("SSH_CONNECTION") and not env.get("DISPLAY"):
        return False
    if places.LINUX:
        return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    return True


def _python_without_console() -> str:
    if places.WINDOWS:
        w = Path(sys.executable).with_name("pythonw.exe")
        if w.is_file():
            return os.fspath(w)
    return sys.executable


def spawn_app(env=None) -> bool:
    """Starts the pets in the background (`python -m agentpet run`), unless there is no desktop
    to show them on or they were quit by hand. True when started."""
    env = dict(os.environ if env is None else env)
    if not can_show(env) or places.quit_flag().exists():
        return False
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = pkg_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    kw: dict = {}
    if places.WINDOWS:
        kw["creationflags"] = _DETACHED_PROCESS | _NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    places.state_dir().mkdir(parents=True, exist_ok=True)
    try:
        with open(places.log_path(), "ab") as err:
            subprocess.Popen([_python_without_console(), "-m", "agentpet", "run"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=err, env=env, close_fds=True, **kw)
        return True
    except OSError:
        return False
