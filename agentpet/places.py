"""Where AgentPet keeps things on each system, and the name of the private channel the hooks use
to reach the running pets.

            state (log, quit flag)              config               channel
  Linux     ~/.local/state/agentpet             ~/.config/agentpet   $XDG_RUNTIME_DIR/agentpet/pets.sock
  macOS     ~/Library/Application Support/AgentPet                   .../AgentPet/run/pets.sock
  Windows   %LOCALAPPDATA%\\AgentPet                                  \\\\.\\pipe\\agentpet-<user>

The channel is a Unix socket in a directory only you can open (mode 0700), or a named pipe that
only your user can open on Windows.
"""

from __future__ import annotations

import getpass
import os
import re
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = not (WINDOWS or MACOS)


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def state_dir() -> Path:
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or _home() / "AppData" / "Local") / "AgentPet"
    if MACOS:
        return _home() / "Library" / "Application Support" / "AgentPet"
    base = os.environ.get("XDG_STATE_HOME", "")
    return (Path(base) if os.path.isabs(base) else _home() / ".local" / "state") / "agentpet"


def config_dir() -> Path:
    if WINDOWS or MACOS:
        return state_dir()
    base = os.environ.get("XDG_CONFIG_HOME", "")
    return (Path(base) if os.path.isabs(base) else _home() / ".config") / "agentpet"


def runtime_dir(create: bool = True) -> Path:
    """Short-lived files: the channel, each agent instance's last event."""
    base = os.environ.get("XDG_RUNTIME_DIR", "") if LINUX else ""
    d = Path(base) / "agentpet" if os.path.isabs(base) and os.path.isdir(base) else state_dir() / "run"
    if create:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def channel() -> str:
    """The Unix socket's path, or the Windows named pipe's name."""
    if WINDOWS:
        user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
        return rf"\\.\pipe\agentpet-{user}"
    return os.fspath(runtime_dir() / "pets.sock")


def quit_flag() -> Path:
    return state_dir() / "quit"


def log_path() -> Path:
    return state_dir() / "log.txt"
