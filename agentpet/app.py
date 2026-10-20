"""`agentpet run`: the pets. One Qt application (a second start just exits), one window per pet
(one pet per running agent instance), one private channel the hooks send to (a QLocalServer: a
Unix socket, or a named pipe on Windows), and a 12.5 fps tick that moves and redraws the pets.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

from . import config, events, ipc, looks, places, sprites
from .motion import Area
from .pet import Pets

log = logging.getLogger("agentpet")

TICK_MS = 80
SPEED = {"clawd": 9.0, "hermes": 7.0}                       # sprite pixels a second
SIZE = {"clawd": (sprites.CLAWD_W, sprites.CLAWD_H), "hermes": (sprites.HERMES_W, sprites.HERMES_H)}
REPLAY_S = 24 * 3600            # on start, an instance's last event is replayed if that agent still runs
FRESH_S = 120                   # ... as itself when this recent, else as plain presence (idle)
MAX_MESSAGE = 64 * 1024


class PetsApp:
    """Everything but the event loop: the channel, the pets, their windows and the tick."""

    def __init__(self, px: int | None = None) -> None:
        from . import procs

        self.pets = Pets(alive=procs.alive)
        self.windows: dict = {}
        self.grabs: dict[str, tuple[float, float]] = {}
        self.px = px or config.load().get("pixel", 4)
        self.server = None
        self.timer = None
        self.last_tick = time.monotonic()
        self.area: Area | None = None
        self.area_checked = 0.0
        self.x11 = self.mac = None

    def start(self) -> bool:
        """Listens on the channel and starts the tick; False when the pets already run."""
        from PySide6.QtCore import QTimer

        from . import window

        from PySide6.QtGui import QGuiApplication

        if not self._listen():
            return False
        platform = QGuiApplication.platformName()      # the extras need the real thing, not "offscreen"
        if platform == "xcb":
            try:
                self.x11 = window.X11Input()
            except Exception as exc:
                log.warning("no X input regions (clicks won't pass around the pets): %s", exc)
        if platform == "cocoa":
            try:
                self.mac = window.Mac()
                self.mac.hide_dock_icon()
            except Exception as exc:
                log.warning("macOS setup: %s", exc)
        self._replay()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        log.info("started (pixel size %s, channel %s)", self.px, places.channel())
        return True

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
        for win in self.windows.values():
            win.close()
        self.windows.clear()
        if self.server is not None:
            self.server.close()

    # -- the channel -----------------------------------------------------------------------
    def _listen(self) -> bool:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        name = places.channel()
        probe = QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(300):
            probe.disconnectFromServer()
            log.info("the pets are already running")
            return False
        QLocalServer.removeServer(name)               # a socket left by a pet app that crashed
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.UserAccessOption)
        if not server.listen(name):
            log.error("cannot listen on %s: %s", name, server.errorString())
            return False
        server.newConnection.connect(self._accept)
        self.server = server
        return True

    def _accept(self) -> None:
        from PySide6.QtNetwork import QLocalSocket

        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            buf = bytearray()
            done = []

            def read(conn=conn, buf=buf):
                buf.extend(bytes(conn.readAll()))
                if len(buf) > MAX_MESSAGE:
                    conn.abort()

            def finish(conn=conn, buf=buf, done=done):
                if done:
                    return
                done.append(True)
                read()
                self.receive(bytes(buf))
                conn.deleteLater()

            conn.readyRead.connect(read)
            conn.disconnected.connect(finish)
            read()
            if conn.state() == QLocalSocket.UnconnectedState:
                finish()

    def receive(self, data: bytes) -> None:
        for line in data.splitlines():
            msg = events.decode(line)
            if msg is None:
                continue
            if msg.get("cmd") == "quit":
                log.info("quit")
                from PySide6.QtWidgets import QApplication

                QApplication.quit()
                return
            if "agent" in msg:
                log.debug("event %s", msg)
                self.pets.deliver(msg, time.monotonic())

    def _replay(self) -> None:
        """Shows a pet for each agent instance running right now (the hook that started this app
        wrote its event down first). Instances that are not running get no pet."""
        from . import procs

        now, wall = time.monotonic(), time.time()
        for path, last in ipc.read_all_last(REPLAY_S):
            msg = events.decode(events.encode(last))
            if not msg or "pid" not in msg or not procs.alive(msg["pid"], msg.get("pid_start")):
                ipc.forget(path)
                continue
            if msg["event"] == "SessionEnd":
                continue
            if wall - msg["ts"] / 1000 > FRESH_S:
                msg = {**msg, "event": "SessionStart"}
            self.pets.deliver(msg, now)

    # -- the mouse -------------------------------------------------------------------------
    def hand(self, key: str, what: str, x: float = 0.0, y: float = 0.0) -> None:
        if key not in self.pets.pets:
            return
        pet, now = self.pets[key], time.monotonic()
        if what == "click":
            self.pets.poke(key, now)
        elif what == "pick":
            pet.motion.pick_up()
            self.grabs[key] = (pet.x - x, pet.y - y)
        elif what in ("move", "drop"):
            gx, gy = self.grabs.get(key, (0.0, 0.0))
            pet.motion.hold_at(x + gx, y + gy)
            if what == "drop" and self.area is not None:
                w, h = self.size(pet.kind)
                pet.motion.drop(now, self.area, w, h)
                self.grabs.pop(key, None)
            self.show(key, pet, now)

    # -- time ------------------------------------------------------------------------------
    def size(self, kind: str) -> tuple[float, float]:
        w, h = SIZE[kind]
        return w * self.px, h * self.px

    def tick(self) -> None:
        from . import window

        now = time.monotonic()
        dt = min(0.25, now - self.last_tick)
        self.last_tick = now
        if self.area is None or now - self.area_checked > 5:
            self.area = Area.of(*window.work_area())
            self.area_checked = now
        for key, pet in self.pets.items():
            w, h = self.size(pet.kind)
            pet.update(now, dt, self.area, w, h, SPEED[pet.kind] * self.px)
            if pet.state(now) == "hidden":
                win = self.windows.pop(key, None)
                if win is not None:
                    win.close()
                    win.deleteLater()
                self.pets.remove(key)
                continue
            self.show(key, pet, now)

    def show(self, key: str, pet, now: float) -> None:
        from . import window

        win = self.windows.get(key)
        if win is None:
            win = self.windows[key] = window.PetWindow(self.px, lambda *a, k=key: self.hand(k, *a), self.x11, self.mac)
        view = pet.view(now, step_px=self.px)
        area = self.area or Area(0, 0, 1e9, 1e9)
        win.show_pet(looks.frame(view, now), view.turn, pet.x, pet.y, (area.left, area.right))


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.DEBUG if "--debug" in argv else logging.INFO, stream=sys.stderr,
                        format="%(asctime)s agentpet %(levelname)s %(message)s")
    if places.LINUX and "QT_QPA_PLATFORM" not in os.environ:
        if not os.environ.get("DISPLAY"):
            log.error("no X display (DISPLAY is not set). On a Wayland desktop the pets need XWayland.")
            return 1
        os.environ["QT_QPA_PLATFORM"] = "xcb"      # see window.py: the pets need X11 (XWayland) on Linux
    _trim_log()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["agentpet"])
    app.setApplicationName("AgentPet")
    app.setQuitOnLastWindowClosed(False)
    pets = PetsApp()
    if not pets.start():
        return 0
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    try:
        return app.exec()
    finally:
        pets.stop()


def _trim_log() -> None:
    p = places.log_path()
    try:
        if p.stat().st_size > 512 * 1024:
            tail = p.read_bytes()[-128 * 1024:]
            p.write_bytes(tail[tail.find(b"\n") + 1:])
    except OSError:
        pass
