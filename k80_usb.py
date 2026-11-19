"""Windows USB HID transport and the K80 lighting protocol."""

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import re
from contextlib import contextmanager

kernel = C.WinDLL("kernel32", use_last_error=True)
hid = C.WinDLL("hid", use_last_error=True)
cfg = C.WinDLL("cfgmgr32", use_last_error=True)
P = C.c_void_p
INVALID_HANDLE = P(-1).value
DEVICE_PATTERN = re.compile(r"^\\\\\?\\hid#vid_5566&pid_0008(?:&|#)", re.I)


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


class Guid(C.Structure):
    _fields_ = [("data", C.c_byte * 16)]


class Overlapped(C.Structure):
    _fields_ = [("internal", C.c_size_t), ("high", C.c_size_t),
                ("offset", W.DWORD), ("offset_high", W.DWORD), ("event", W.HANDLE)]


guid = bind(hid, "HidD_GetHidGuid", None, C.POINTER(Guid))
list_size = bind(cfg, "CM_Get_Device_Interface_List_SizeW", W.DWORD, C.POINTER(W.ULONG),
                 C.POINTER(Guid), W.LPCWSTR, W.ULONG)
list_interfaces = bind(cfg, "CM_Get_Device_Interface_ListW", W.DWORD, C.POINTER(Guid),
                       W.LPCWSTR, W.LPWSTR, W.ULONG, W.ULONG)
locate = bind(cfg, "CM_Locate_DevNodeW", W.DWORD, C.POINTER(W.ULONG), W.LPCWSTR, W.ULONG)
get_parent = bind(cfg, "CM_Get_Parent", W.DWORD, C.POINTER(W.ULONG), W.ULONG, W.ULONG)
get_id = bind(cfg, "CM_Get_Device_IDW", W.DWORD, W.ULONG, W.LPWSTR, W.ULONG, W.ULONG)
create = bind(kernel, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, P,
              W.DWORD, W.DWORD, W.HANDLE)
close = bind(kernel, "CloseHandle", W.BOOL, W.HANDLE)
product_string = bind(hid, "HidD_GetProductString", C.c_ubyte, W.HANDLE, P, W.ULONG)
preparsed = bind(hid, "HidD_GetPreparsedData", C.c_ubyte, W.HANDLE, C.POINTER(P))
free_preparsed = bind(hid, "HidD_FreePreparsedData", C.c_ubyte, P)
get_caps = bind(hid, "HidP_GetCaps", W.LONG, P, P)
flush = bind(hid, "HidD_FlushQueue", C.c_ubyte, W.HANDLE)
event = bind(kernel, "CreateEventW", W.HANDLE, P, W.BOOL, W.BOOL, W.LPCWSTR)
wait = bind(kernel, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
cancel = bind(kernel, "CancelIoEx", W.BOOL, W.HANDLE, C.POINTER(Overlapped))
result = bind(kernel, "GetOverlappedResult", W.BOOL, W.HANDLE, C.POINTER(Overlapped),
              C.POINTER(W.DWORD), W.BOOL)
read = bind(kernel, "ReadFile", W.BOOL, W.HANDLE, P, W.DWORD, C.POINTER(W.DWORD),
            C.POINTER(Overlapped))
write = bind(kernel, "WriteFile", W.BOOL, W.HANDLE, P, W.DWORD, C.POINTER(W.DWORD),
             C.POINTER(Overlapped))


@contextmanager
def handle_for(path, access=0):
    handle = create(path, access, 3, None, 3, 0x40000000 if access else 0, None)
    if handle == INVALID_HANDLE:
        raise C.WinError(C.get_last_error())
    try:
        yield handle
    finally:
        close(handle)


def interface_paths():
    hid_guid = Guid()
    guid(C.byref(hid_guid))
    for _ in range(3):
        size = W.ULONG()
        if list_size(C.byref(size), C.byref(hid_guid), None, 0):
            break
        buffer = C.create_unicode_buffer(size.value)
        status = list_interfaces(C.byref(hid_guid), None, buffer, size, 0)
        if status == 0:
            return [path for path in buffer[:].split("\0") if DEVICE_PATTERN.match(path)]
        if status != 0x1A:  # CR_BUFFER_SMALL if a device arrived during enumeration
            break
    raise OSError("Could not enumerate Windows HID interfaces.")


def interface_identity(path):
    # HID and Raw Input use different class GUIDs for the same Windows devnode.
    return path.lower().rsplit("#", 1)[0]


def physical_device(path):
    parts = interface_identity(path)[4:].split("#")
    if len(parts) != 3:
        return None
    node = W.ULONG()
    if locate(C.byref(node), "\\".join(parts[:3]), 0):
        return None
    for _ in range(5):
        instance = C.create_unicode_buffer(512)
        if get_id(node, instance, len(instance), 0):
            return None
        instance_id = instance.value.upper()
        if instance_id.startswith("USB\\VID_5566&PID_0008\\"):
            return instance_id
        parent = W.ULONG()
        if get_parent(C.byref(parent), node, 0):
            return None
        node = parent
    return None


def product(path):
    with handle_for(path) as handle:
        name = C.create_unicode_buffer(128)
        if not product_string(handle, name, C.sizeof(name)):
            raise OSError("Could not read the HID product name.")
        return name.value


def validate_control(handle):
    name = C.create_unicode_buffer(128)
    if not product_string(handle, name, C.sizeof(name)) or name.value != "ZXWCustom":
        raise OSError("The K80 custom HID product name did not match.")
    data = P()
    if not preparsed(handle, C.byref(data)):
        raise OSError("Could not read K80 HID capabilities.")
    try:
        caps = (C.c_ushort * 32)()
        if get_caps(data, caps) != 0x110000 or tuple(caps[:5]) != (0, 1, 65, 65, 0):
            raise OSError("The K80 HID report format did not match.")
    finally:
        free_preparsed(data)


@dataclass(frozen=True)
class Device:
    identity: str
    keyboard_paths: frozenset
    control_path: str | None


def discover():
    devices = {}
    for path in interface_paths():
        if not re.search(r"&mi_(?:00&col01|01|02)#", path, re.I):
            continue
        identity = physical_device(path)
        if identity:
            devices.setdefault(identity, []).append(path)
    matches = []
    for identity, paths in devices.items():
        primary = next((p for p in paths if "&mi_00&col01#" in p.lower()), None)
        if not primary:
            continue
        try:
            if product(primary) != "K80":
                continue
        except OSError:
            continue
        keyboards = frozenset(interface_identity(p) for p in paths
                              if "&mi_02#" not in p.lower())
        control = next((p for p in paths if "&mi_02#" in p.lower()), None)
        matches.append(Device(identity, keyboards, control))
    if len(matches) > 1:
        raise OSError("Multiple wired K80 keyboards found. Connect one to select it.")
    return matches[0] if matches else None


def transfer(handle, operation, buffer):
    count = W.DWORD()
    overlapped = Overlapped()
    overlapped.event = event(None, True, False, None)
    if not overlapped.event:
        raise C.WinError(C.get_last_error())
    try:
        if not operation(handle, buffer, len(buffer), C.byref(count), C.byref(overlapped)):
            error = C.get_last_error()
            if error != 997:  # ERROR_IO_PENDING
                raise C.WinError(error)
            if wait(overlapped.event, 400) != 0:
                cancel(handle, C.byref(overlapped))
                result(handle, C.byref(overlapped), C.byref(count), True)
                raise TimeoutError("The K80 did not complete the USB request.")
            if not result(handle, C.byref(overlapped), C.byref(count), False):
                raise C.WinError(C.get_last_error())
        if count.value != len(buffer):
            raise OSError("The K80 returned a partial HID report.")
    finally:
        close(overlapped.event)


def exchange(handle, opcode, payload=0, state=None):
    frame = bytearray(state if state is not None else bytes(65))
    frame[:4] = bytes((0, 0x55, opcode, 0))
    frame[5] = payload
    frame[4] = sum(frame[5:]) & 255
    transfer(handle, write, (C.c_ubyte * 65).from_buffer_copy(frame))
    response = (C.c_ubyte * 65)()
    transfer(handle, read, response)
    data = bytes(response)
    if data[:3] != bytes((0, 0xAA, opcode)) or data[4] != (sum(data[5:]) & 255):
        raise OSError(f"Unexpected K80 reply for command {opcode:02X}.")
    return data


def read_settings(handle):
    state = exchange(handle, 0x05, 0x20)
    if state[10] != 0xAA or state[12] > 100 or state[13] > 4:
        raise OSError("The K80 lighting reply has an unrecognized format.")
    return state


def settings(device, changes=None, expected=None):
    if not device or not device.control_path:
        raise OSError("The K80 custom HID interface is unavailable.")
    if discover() != device:
        raise OSError("The wired K80 changed. Connect it and read its settings again.")
    if changes and (expected is None or any(
        index not in (11, 12, 13, 26) or type(value) is not int
        or not 0 <= value <= {11: 255, 12: 100, 13: 4, 26: 255}[index]
        for index, value in changes.items()
    )):
        raise ValueError("Invalid K80 lighting change.")
    with handle_for(device.control_path, 0xC0000000) as handle:
        validate_control(handle)
        flush(handle)
        exchange(handle, 0x01)
        try:
            original = read_settings(handle)
            if changes:
                if any(original[i] != expected[i] for i in (11, 12, 13, 26)):
                    raise OSError("Settings changed on the keyboard. Read them again before applying.")
                updated = bytearray(original)
                for index, value in changes.items():
                    updated[index] = value
                if updated != original:
                    exchange(handle, 0x06, 0x20, updated)
        except (OSError, ValueError):
            try:
                exchange(handle, 0x02)
            except OSError:
                pass
            raise
        else:
            exchange(handle, 0x02)
        if not changes or updated == original:
            return original
    confirmed = settings(device)
    if any(confirmed[index] != value for index, value in changes.items()):
        raise OSError("The K80 did not report the requested settings. Read them again.")
    return confirmed
