"""K80 keyboard input and Windows shortcut actions."""

import ctypes as C
from ctypes import wintypes as W
import os
import logging
from queue import SimpleQueue
from threading import Event, Thread

from k80_usb import bind, interface_identity, kernel, P

user = C.WinDLL("user32", use_last_error=True)
WNDPROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, C.c_size_t, C.c_ssize_t)


class RawDevice(C.Structure):
    _fields_ = [("page", W.USHORT), ("usage", W.USHORT), ("flags", W.DWORD),
                ("target", W.HWND)]


class RawHeader(C.Structure):
    _fields_ = [("kind", W.DWORD), ("size", W.DWORD), ("device", W.HANDLE),
                ("parameter", C.c_size_t)]


class RawKeyboard(C.Structure):
    _fields_ = [("scan", W.USHORT), ("flags", W.USHORT), ("reserved", W.USHORT),
                ("virtual", W.USHORT), ("message", W.UINT), ("extra", W.ULONG)]


class WindowClass(C.Structure):
    _fields_ = [("style", W.UINT), ("proc", WNDPROC), ("class_extra", C.c_int),
                ("window_extra", C.c_int), ("instance", W.HINSTANCE), ("icon", W.HICON),
                ("cursor", W.HANDLE), ("background", W.HBRUSH), ("menu", W.LPCWSTR),
                ("name", W.LPCWSTR)]


class KeyboardInput(C.Structure):
    _fields_ = [("virtual", W.WORD), ("scan", W.WORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", C.c_size_t)]


class MouseInput(C.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG), ("data", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", C.c_size_t)]


class InputData(C.Union):
    _fields_ = [("key", KeyboardInput), ("mouse", MouseInput)]


class Input(C.Structure):
    _fields_ = [("kind", W.DWORD), ("data", InputData)]


register = bind(user, "RegisterRawInputDevices", W.BOOL, C.POINTER(RawDevice), W.UINT, W.UINT)
raw_data = bind(user, "GetRawInputData", W.UINT, W.HANDLE, W.UINT, P, C.POINTER(W.UINT), W.UINT)
raw_info = bind(user, "GetRawInputDeviceInfoW", W.UINT, W.HANDLE, W.UINT, P, C.POINTER(W.UINT))
module = bind(kernel, "GetModuleHandleW", W.HINSTANCE, W.LPCWSTR)
register_class = bind(user, "RegisterClassW", W.ATOM, C.POINTER(WindowClass))
unregister_class = bind(user, "UnregisterClassW", W.BOOL, W.LPCWSTR, W.HINSTANCE)
create_window = bind(user, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR,
                     W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU,
                     W.HINSTANCE, P)
destroy_window = bind(user, "DestroyWindow", W.BOOL, W.HWND)
default_proc = bind(user, "DefWindowProcW", C.c_ssize_t, W.HWND, W.UINT, C.c_size_t, C.c_ssize_t)
get_message = bind(user, "GetMessageW", W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
dispatch_message = bind(user, "DispatchMessageW", C.c_ssize_t, C.POINTER(W.MSG))
post_quit = bind(user, "PostQuitMessage", None, C.c_int)
post_message = bind(user, "PostMessageW", W.BOOL, W.HWND, W.UINT, C.c_size_t, C.c_ssize_t)
get_root = bind(user, "GetAncestor", W.HWND, W.HWND, W.UINT)
foreground = bind(user, "GetForegroundWindow", W.HWND)
send_input = bind(user, "SendInput", W.UINT, W.UINT, C.POINTER(Input), C.c_int)

MODIFIERS = {
    0x1D: "Ctrl", 0x11D: "Ctrl", 0x2A: "Shift", 0x36: "Shift",
    0x38: "Alt", 0x138: "Alt", 0x15B: "Win", 0x15C: "Win",
}
MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
MEDIA = {"Volume up": 0xAF, "Volume down": 0xAE, "Mute": 0xAD,
         "Play / pause": 0xB3, "Next track": 0xB0, "Previous track": 0xB1}
OUTPUT_KEYS = {**{chr(n): n for n in range(65, 91)}, **{str(n): 48 + n for n in range(10)},
               **{f"F{n}": 111 + n for n in range(1, 13)},
               "Escape": 0x1B, "Backspace": 0x08, "Tab": 0x09, "Enter": 0x0D,
               "Space": 0x20, "Page Up": 0x21, "Page Down": 0x22, "End": 0x23,
               "Home": 0x24, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
               "Insert": 0x2D, "Delete": 0x2E}
OUTPUT_MODIFIERS = {"Ctrl": 0xA2, "Alt": 0xA4, "Shift": 0xA0, "Win": 0x5B}
EXTENDED_KEYS = {0x5B, *range(0x21, 0x29), 0x2D, 0x2E, *MEDIA.values()}


def row(names, scans):
    return tuple(zip(names, scans, strict=True))


LAYOUT = (
    row(("Esc", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10",
         "F11", "F12", "PrtSc", "ScrLk", "Pause"),
        (0x01, *range(0x3B, 0x45), 0x57, 0x58, 0x137, 0x46, 0x245)),
    row(tuple("`1234567890-=") + ("Backspace", "Ins", "Home", "PgUp"),
        (0x29, *range(0x02, 0x0E), 0x0E, 0x152, 0x147, 0x149)),
    row(("Tab", *"QWERTYUIOP[]\\", "Del", "End", "PgDn"),
        (0x0F, *range(0x10, 0x1C), 0x2B, 0x153, 0x14F, 0x151)),
    row(("Caps Lock", *"ASDFGHJKL;'", "Enter"), (0x3A, *range(0x1E, 0x29), 0x1C)),
    row(("L Shift", *"ZXCVBNM,./", "R Shift", "↑"),
        (0x2A, *range(0x2C, 0x36), 0x36, 0x148)),
    row(("L Ctrl", "L Win", "L Alt", "Space", "R Alt", "R Win", "Menu", "R Ctrl", "←", "↓", "→"),
        (0x1D, 0x15B, 0x38, 0x39, 0x138, 0x15C, 0x15D, 0x11D, 0x14B, 0x150, 0x14D)),
)
KEY_NAMES = {scan: name for keys in LAYOUT for name, scan in keys}


def keyboard_scan(data):
    if data.virtual == 0xFF or data.scan == 0xFF:
        return None
    if data.virtual == 0x13:
        return 0x245
    if data.flags & 4:  # Ignore the E1 prefix preceding Pause
        return None
    if data.virtual == 0x2C:
        return 0x137
    if data.flags & 2 and data.scan in (0x2A, 0x36):  # Print Screen's fake Shift
        return None
    return data.scan | (0x100 if data.flags & 2 else 0)


def canonical(modifiers):
    return tuple(modifier for modifier in MODIFIER_ORDER if modifier in modifiers)


class RawInput:
    def __init__(self, hwnd):
        self.owner = get_root(hwnd, 2) or hwnd
        self.hwnd = None
        self.background = False
        self.events = SimpleQueue()
        self.names = {}
        self.callback = WNDPROC(self.window_proc)
        self.ready = Event()
        self.error = None
        self.thread = Thread(target=self.run, name="K80 Raw Input", daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise self.error

    def run(self):
        name = "K80InputWindow"
        instance = module(None)
        window_class = WindowClass(proc=self.callback, instance=instance, name=name)
        registered = False
        try:
            if not register_class(C.byref(window_class)):
                raise C.WinError(C.get_last_error())
            registered = True
            self.hwnd = create_window(0, name, name, 0, 0, 0, 0, 0, -3, None, instance, None)
            if not self.hwnd:
                raise C.WinError(C.get_last_error())
            device = RawDevice(1, 6, 0x2100, self.hwnd)  # DEVNOTIFY | INPUTSINK
            if not register(C.byref(device), 1, C.sizeof(device)):
                raise C.WinError(C.get_last_error())
            self.ready.set()
            msg = W.MSG()
            while get_message(C.byref(msg), None, 0, 0) > 0:
                dispatch_message(C.byref(msg))
        except OSError as exc:
            self.error = exc
        finally:
            if self.hwnd:
                destroy_window(self.hwnd)
            if registered:
                unregister_class(name, instance)
            self.ready.set()

    def listen(self, background):
        self.background = background

    def close(self):
        if self.hwnd:
            post_message(self.hwnd, 0x10, 0, 0)  # WM_CLOSE
        self.thread.join(timeout=1)

    def device_path(self, handle):
        if handle not in self.names:
            size = W.UINT()
            if raw_info(handle, 0x20000007, None, C.byref(size)) == 0 and size.value:
                name = C.create_unicode_buffer(size.value)
                if raw_info(handle, 0x20000007, name, C.byref(size)) != 0xFFFFFFFF:
                    self.names[handle] = interface_identity(name.value)
        return self.names.get(handle)

    def parse(self, parameter):
        size = W.UINT()
        header_bytes = C.sizeof(RawHeader)
        if raw_data(parameter, 0x10000003, None, C.byref(size), header_bytes):
            return
        if size.value < header_bytes + C.sizeof(RawKeyboard):
            return
        buffer = C.create_string_buffer(size.value)
        got = raw_data(parameter, 0x10000003, buffer, C.byref(size), header_bytes)
        if got != len(buffer):
            return
        header = RawHeader.from_buffer(buffer)
        if header.kind != 1 or not header.device:
            return
        path = self.device_path(header.device)
        if not path:
            return
        data = RawKeyboard.from_buffer(buffer, header_bytes)
        scan = keyboard_scan(data)
        if scan in KEY_NAMES and "hid#vid_5566&pid_0008&" in path:
            self.events.put((path, scan, not bool(data.flags & 1)))

    def window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == 0x00FF and (self.background or foreground() == self.owner):
                self.parse(lparam)
            elif message == 0x00FE:
                path = self.device_path(lparam)
                if wparam == 2:
                    self.names.pop(lparam, None)
                self.events.put((path, None, wparam == 1))
            elif message == 0x10:
                device = RawDevice(1, 6, 1, None)  # REMOVE
                register(C.byref(device), 1, C.sizeof(device))
                destroy_window(hwnd)
                self.hwnd = None
                post_quit(0)
                return 0
        except Exception:
            logging.exception("K80 Raw Input callback failed")
        return default_proc(hwnd, message, wparam, lparam)


def key_event(virtual=0, scan=0, flags=0):
    item = Input()
    item.kind = 1
    item.data.key = KeyboardInput(virtual, scan, flags, 0, 0)
    return item


def virtual_event(virtual, up=False):
    return key_event(virtual, flags=(1 if virtual in EXTENDED_KEYS else 0) | (2 if up else 0))


def output_sequence(value):
    sequence = []
    for chord in value.split(","):
        items = [item.strip() for item in chord.split("+")]
        if not items or items[-1] not in OUTPUT_KEYS or any(
                item not in OUTPUT_MODIFIERS for item in items[:-1]):
            raise ValueError("Use key chords such as Ctrl+S, Enter. Key names are case sensitive.")
        if len(set(items[:-1])) != len(items[:-1]):
            raise ValueError("Use each modifier once per key chord.")
        keys = [OUTPUT_MODIFIERS[item] for item in items[:-1]] + [OUTPUT_KEYS[items[-1]]]
        sequence.extend(virtual_event(key) for key in keys)
        sequence.extend(virtual_event(key, True) for key in reversed(keys))
    return sequence


def perform(action, value):
    if action == "Open file or app":
        os.startfile(value)
        return
    if action == "Type text":
        encoded = value.encode("utf-16-le")
        units = [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]
        sequence = [event for unit in units for event in
                    (key_event(scan=unit, flags=4), key_event(scan=unit, flags=6))]
    elif action == "Send keys":
        sequence = output_sequence(value)
    else:
        virtual = MEDIA[value]
        sequence = [virtual_event(virtual), virtual_event(virtual, True)]
    count = len(sequence)
    if count:
        if send_input(count, (Input * count)(*sequence), C.sizeof(Input)) != count:
            raise OSError("Windows blocked the shortcut or the action was incomplete.")
