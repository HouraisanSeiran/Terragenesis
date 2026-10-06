"""Inspect and control only the Minecraft client recorded in verification/pid.txt.

Coordinates for click are relative to the target client's content area. All output is
written under the workspace; this script never targets an arbitrary foreground app.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import time

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "verification/client-managed-service/pid.txt"
OUTPUT = ROOT / "verification/client-managed-service"
USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

USER32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
USER32.IsWindowVisible.argtypes = [wintypes.HWND]
USER32.IsWindowVisible.restype = wintypes.BOOL
USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
USER32.GetWindowTextLengthW.restype = ctypes.c_int
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
USER32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
USER32.GetForegroundWindow.restype = wintypes.HWND
USER32.SetForegroundWindow.argtypes = [wintypes.HWND]
USER32.SetForegroundWindow.restype = wintypes.BOOL
USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
USER32.BringWindowToTop.argtypes = [wintypes.HWND]
USER32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
USER32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
USER32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_size_t]
USER32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
KERNEL32.GetCurrentThreadId.restype = wintypes.DWORD

VK = {"enter": 0x0D, "escape": 0x1B, "tab": 0x09, "space": 0x20,
      "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25,
      "right": 0x27, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f11": 0x7A}
JAVA = Path("D:/codexwork/MinecraftZombieArmy/tools/jdk-25.0.2/bin/java.exe")


def recorded_pid() -> int:
    pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    if pid <= 0:
        raise RuntimeError("Invalid recorded Minecraft PID")
    return pid


def client_window() -> int:
    pid = recorded_pid()
    matches = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def inspect(hwnd, unused):
        found = wintypes.DWORD()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(found))
        if found.value != pid or not USER32.IsWindowVisible(hwnd):
            return True
        length = USER32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, title, len(title))
        if "Minecraft" in title.value:
            matches.append((hwnd, title.value))
        return True

    USER32.EnumWindows(inspect, 0)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one visible Minecraft window for PID {pid}, found {matches}")
    return matches[0][0]


def client_bounds(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not USER32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Cannot read Minecraft client bounds")
    origin = wintypes.POINT(0, 0)
    if not USER32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("Cannot locate Minecraft client")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 320 or height < 200:
        raise RuntimeError(f"Minecraft client too small: {width}x{height}")
    return origin.x, origin.y, width, height


def focus(hwnd: int) -> None:
    if USER32.GetForegroundWindow() == hwnd:
        return
    # Restore a minimized game before asking Windows to transfer focus.
    USER32.ShowWindow(hwnd, 9)
    foreground = USER32.GetForegroundWindow()
    foreground_thread = USER32.GetWindowThreadProcessId(foreground, None)
    current_thread = KERNEL32.GetCurrentThreadId()
    attached = foreground_thread != current_thread and USER32.AttachThreadInput(current_thread, foreground_thread, True)
    try:
        USER32.BringWindowToTop(hwnd)
        USER32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            USER32.AttachThreadInput(current_thread, foreground_thread, False)
    for _ in range(6):
        if USER32.GetForegroundWindow() == hwnd:
            return
        time.sleep(.1)
    if USER32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Minecraft did not become foreground; no input was sent")


def snapshot(hwnd: int, name: str) -> Path:
    output = OUTPUT / name
    if output.resolve().parent != OUTPUT.resolve() or output.suffix.lower() != ".png":
        raise ValueError("Screenshot must be a PNG filename under verification/client-managed-service")
    try:
        image = ImageGrab.grab(window=hwnd)
    except (OSError, TypeError):
        focus(hwnd)
        x, y, width, height = client_bounds(hwnd)
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def key(hwnd: int, name: str) -> None:
    focus(hwnd)
    code = VK.get(name.lower())
    if code is None and len(name) == 1 and name.isascii() and name.isalnum():
        code = ord(name.upper())
    if code is None:
        raise ValueError(f"Unsupported key: {name}")
    USER32.keybd_event(code, 0, 0, 0)
    time.sleep(.05)
    USER32.keybd_event(code, 0, 2, 0)


def click(hwnd: int, x: int, y: int, button: str) -> None:
    focus(hwnd)
    left, top, width, height = client_bounds(hwnd)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"Click outside Minecraft client {width}x{height}")
    if not USER32.SetCursorPos(left + x, top + y):
        raise RuntimeError("Could not move cursor into Minecraft")
    down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
    USER32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(.05)
    USER32.mouse_event(up, 0, 0, 0, 0)


def launch() -> int:
    """Launch the workspace's recorded test client without touching other instances."""
    args_file = OUTPUT / "client.args"
    if not JAVA.is_file() or not args_file.is_file():
        raise RuntimeError("Client Java runtime or argument file is missing")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "stdout.log").open("ab") as stdout, (OUTPUT / "stderr.log").open("ab") as stderr:
        process = subprocess.Popen([str(JAVA), "@" + str(args_file)], cwd=ROOT,
                                   stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    shot = actions.add_parser("screenshot")
    shot.add_argument("filename")
    press = actions.add_parser("key")
    press.add_argument("name")
    mouse = actions.add_parser("click")
    mouse.add_argument("x", type=int)
    mouse.add_argument("y", type=int)
    mouse.add_argument("--button", choices=("left", "right"), default="left")
    actions.add_parser("launch")
    args = parser.parse_args()
    if args.action == "launch":
        print(f"Launched workspace Minecraft client PID {launch()}")
        return
    hwnd = client_window()
    print(f"Minecraft PID {recorded_pid()}, HWND {hwnd}, client {client_bounds(hwnd)}")
    if args.action == "screenshot":
        print(snapshot(hwnd, args.filename))
    elif args.action == "key":
        key(hwnd, args.name)
    else:
        click(hwnd, args.x, args.y, args.button)


if __name__ == "__main__":
    main()
