"""A pet on screen: one small, see-through, always-on-top window per pet, centred on the pet and
moved with it anywhere on the screen, made with Qt on every system.

* Linux: the pets run through X11 (XWayland on Wayland desktops, where an app may not place its
  own windows or keep them above others). Each window bypasses the window manager (no frame,
  focus, taskbar or Alt-Tab entry), and an X input region makes clicks fall through everywhere
  but on the pet itself.
* macOS: tool windows with no Dock icon, on every Space and over full-screen apps; clicks fall
  through the transparent parts.
* Windows: tool windows (no taskbar button) that never take the focus; clicks fall through the
  transparent parts.

Pressing on a pet and moving the mouse picks it up; it follows the pointer until you let go.
"""

from __future__ import annotations

import ctypes
import logging
import time

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from . import places
from .frame import Frame, pet_box
from .paint import draw_pet

log = logging.getLogger("agentpet")

WIN = 300                       # logical pixels, square: room around the pet for its bubble and effects
RAISE_EVERY = 1.0
DRAG_START = 4                  # pixels the pointer moves before a press becomes a pick-up


class X11Input:
    """Linux: the X input region of a window (XShape), so only the pet itself takes clicks."""

    class _Rect(ctypes.Structure):
        _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]

    def __init__(self) -> None:
        x = self.x11 = ctypes.CDLL("libX11.so.6")
        e = self.xext = ctypes.CDLL("libXext.so.6")
        x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        x.XFlush.argtypes = [ctypes.c_void_p]
        e.XShapeCombineRectangles.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                              ctypes.POINTER(self._Rect), ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dpy = x.XOpenDisplay(None)
        if not self.dpy:
            raise RuntimeError("no X display")

    def set(self, xid: int, box: tuple[int, int, int, int], scale: float) -> None:
        x, y, w, h = (int(round(v * scale)) for v in box)
        r = self._Rect(x, y, max(1, w), max(1, h))
        self.xext.XShapeCombineRectangles(self.dpy, xid, 2, 0, 0, ctypes.byref(r), 1, 0, 0)   # ShapeInput, ShapeSet
        self.x11.XFlush(self.dpy)


class Mac:
    """macOS: a few AppKit calls through the Objective-C runtime (no PyObjC needed)."""

    def __init__(self) -> None:
        self.objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        self.objc.objc_getClass.restype = ctypes.c_void_p
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(self, obj, selector: str, restype=ctypes.c_void_p, *args):
        fn = self.objc.objc_msgSend
        fn.restype = restype
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [t for t, _ in args]
        return fn(obj, self.objc.sel_registerName(selector.encode()), *[v for _, v in args])

    def hide_dock_icon(self) -> None:
        app = self.send(self.objc.objc_getClass(b"NSApplication"), "sharedApplication")
        self.send(app, "setActivationPolicy:", ctypes.c_bool, (ctypes.c_long, 1))        # accessory

    def everywhere(self, view: int) -> None:
        """On every Space and over full-screen apps, and still there when another app is active."""
        win = self.send(ctypes.c_void_p(view), "window")
        if win:
            # canJoinAllSpaces | stationary | ignoresCycle | fullScreenAuxiliary
            self.send(win, "setCollectionBehavior:", None, (ctypes.c_ulong, 1 | 16 | 64 | 256))
            self.send(win, "setHidesOnDeactivate:", None, (ctypes.c_bool, False))


class PetWindow(QWidget):
    """`hand` gets the mouse: hand("click"), hand("pick", x, y), hand("move", x, y),
    hand("drop", x, y), with x and y the pointer in logical screen pixels."""

    def __init__(self, px: int, hand, x11: X11Input | None = None, mac: Mac | None = None) -> None:
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                 | Qt.NoDropShadowWindowHint)
        if places.LINUX:
            flags |= Qt.X11BypassWindowManagerHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("AgentPet")
        self.resize(WIN, WIN)
        self.px = px
        self.hand = hand
        self.x11, self.mac = x11, mac
        self.frame: Frame | None = None
        self.turn = ""
        self.clamp: tuple[float, float] | None = None
        self.input_box: tuple | None = None
        self.raised = 0.0
        self.press = None
        self.dragging = False
        self.prepared = False

    # -- placing and drawing -------------------------------------------------------------
    def show_pet(self, frame: Frame, turn: str, cx: float, cy: float, clamp: tuple[float, float]) -> None:
        """Shows the frame centred on (cx, cy) in logical screen pixels; the bubble stays between
        clamp's x bounds (the screen's)."""
        left, top = round(cx) - WIN // 2, round(cy) - WIN // 2
        self.frame, self.turn = frame, turn
        self.clamp = (clamp[0] - left, clamp[1] - left)
        if (self.x(), self.y()) != (left, top):
            self.move(left, top)
        if not self.isVisible():
            self.show()
        if not self.prepared:
            self._prepare()
        now = time.monotonic()
        if self.x11 is not None and now - self.raised > RAISE_EVERY:      # X11: keep above newer windows
            self.raised = now
            self.raise_()
        if self.x11 is not None:
            m = self.px
            x, y, w, h = pet_box(frame, turn, WIN / 2, WIN / 2, self.px)
            box = (x - m, y - m, w + 2 * m, h + 2 * m)
            if box != self.input_box:
                self.input_box = box
                try:
                    self.x11.set(int(self.winId()), box, self.devicePixelRatioF())
                except Exception as exc:          # pragma: no cover - X errors
                    log.debug("input region: %s", exc)
        self.update()

    def _prepare(self) -> None:
        self.prepared = True
        if self.mac is not None:
            try:
                self.mac.everywhere(int(self.winId()))
            except Exception as exc:              # pragma: no cover - macOS only
                log.debug("macOS window: %s", exc)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if self.frame is not None:
            draw_pet(p, self.frame, self.turn, WIN / 2, WIN / 2, self.px, self.clamp, catch=not places.LINUX)
        p.end()

    # -- the mouse -----------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.press = event.globalPosition()
            self.dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self.press is None:
            return
        g = event.globalPosition()
        if not self.dragging:
            if abs(g.x() - self.press.x()) < DRAG_START and abs(g.y() - self.press.y()) < DRAG_START:
                return
            self.dragging = True
            self.hand("pick", self.press.x(), self.press.y())
        self.hand("move", g.x(), g.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self.dragging:
            g = event.globalPosition()
            self.hand("drop", g.x(), g.y())
        elif self.press is not None:
            self.hand("click")
        self.press = None
        self.dragging = False


def work_area() -> tuple[int, int, int, int]:
    """(x, y, w, h) of the primary screen minus panels, docks, the menu bar and the taskbar, in
    logical pixels."""
    screen = QGuiApplication.primaryScreen()
    r = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)
    return r.x(), r.y(), r.width(), r.height()
