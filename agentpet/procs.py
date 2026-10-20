"""Processes, on every system (through psutil): is an agent still running, which process above a
hook is the agent, which terminal it runs in.

A process is named by its pid and its start time (`stamp`, in hundredths of a second since the
epoch), so a new process that happens to get the same pid is not taken for the agent.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass
class Proc:
    pid: int
    name: str          # lower case, without ".exe"
    parent: int
    stamp: int         # start time, 1/100 s since the epoch
    cmdline: str = ""


def stamp_of(create_time: float) -> int:
    return int(round(create_time * 100))


def info(pid: int, with_cmdline: bool = False) -> Proc | None:
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            name = p.name()
            parent = p.ppid()
            stamp = stamp_of(p.create_time())
            cmd = " ".join(p.cmdline()) if with_cmdline else ""
    except (psutil.Error, OSError):
        return None
    name = name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return Proc(pid, name, parent, stamp, cmd)


def alive(pid: int, stamp: int | None = None) -> bool:
    """True while that process runs (and, given its start time, is the same process)."""
    try:
        p = psutil.Process(pid)
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        return stamp is None or abs(stamp_of(p.create_time()) - stamp) <= 2
    except (psutil.Error, OSError):
        return False


def terminal(pid: int | None) -> str | None:
    """The terminal tab a process runs in ("pts/3" on Linux, "ttys003" on macOS); None on Windows
    or with no terminal."""
    if not pid:
        return None
    try:
        dev = psutil.Process(pid).terminal()
    except (psutil.Error, OSError, AttributeError):
        return None
    return dev[5:] if isinstance(dev, str) and dev.startswith("/dev/") else None
