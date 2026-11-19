import ctypes as C
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from k80_control import ControlCenter
from k80_input import KEY_NAMES, RawKeyboard, keyboard_scan, output_sequence
from k80_profiles import defaults, load, new_binding, save
from k80_usb import Device, exchange, interface_identity, read, write


class ProtocolTests(unittest.TestCase):
    @staticmethod
    def response(opcode, bad_checksum=False):
        reply = bytearray(65)
        reply[:3] = (0, 0xAA, opcode)
        reply[5] = 0x20
        reply[4] = 0x21 if bad_checksum else 0x20
        return reply

    def test_exchange_preserves_vendor_fields_and_checks_checksum(self):
        state = bytearray(self.response(5))
        state[48] = 70

        def transfer(_handle, operation, buffer):
            if operation is write:
                frame = bytes(buffer)
                self.assertEqual(frame[:6], bytes((0, 0x55, 0x06, 0, 102, 0x20)))
                self.assertEqual(frame[48], 70)
            elif operation is read:
                C.memmove(buffer, bytes(self.response(6)), 65)

        with patch("k80_usb.transfer", side_effect=transfer):
            self.assertEqual(exchange(None, 6, 0x20, state)[2], 6)

    def test_rejects_malformed_reply(self):
        for response in (self.response(2), self.response(5, bad_checksum=True)):
            with self.subTest(response=response[:6]):
                def feed(_handle, operation, buffer):
                    if operation is read:
                        C.memmove(buffer, bytes(response), 65)
                with patch("k80_usb.transfer", side_effect=feed), self.assertRaises(OSError):
                    exchange(None, 5, 0x20)

    def test_timeout_surfaces_without_retrying_write(self):
        with patch("k80_usb.transfer", side_effect=[None, TimeoutError("no reply")]) as transfer:
            with self.assertRaises(TimeoutError):
                exchange(None, 5, 0x20)
            self.assertEqual(transfer.call_count, 2)


class ProfileTests(unittest.TestCase):
    def test_round_trip_and_invalid_profile_preserved(self):
        data = defaults()
        profile = data["profiles"]["Default"]
        profile["lighting"] = {"mode": 7, "brightness": 0, "speed": 0, "win_lock": False}
        profile["shortcuts"].append(new_binding(("Ctrl",), 0x20, "Type text", "مرحبًا"))
        with TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.json"
            self.assertEqual(load(path), defaults())
            save(data, path)
            self.assertEqual(load(path), data)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{")

    def test_binding_and_output_validation(self):
        with self.assertRaises(ValueError):
            new_binding((), 0x20, "Send keys", "Ctrl+S")
        with self.assertRaises(ValueError):
            output_sequence("Alt+Alt+A")
        self.assertEqual(len(output_sequence("Ctrl+S, Enter")), 6)


class InputTests(unittest.TestCase):
    def test_raw_and_hid_names_match_by_devnode(self):
        node = r"\\?\HID#VID_5566&PID_0008&MI_01#8&1234&0&0000"
        self.assertEqual(interface_identity(node + r"#{4d1e55b2}\KBD"),
                         interface_identity(node.lower() + "#{884b96c3}"))
        self.assertNotEqual(interface_identity(node + "#{4d1e55b2}"),
                            interface_identity(node.replace("1234", "1111") + "#{884b96c3}"))

    def test_layout_and_extended_keys(self):
        self.assertEqual(len(KEY_NAMES), 87)
        self.assertEqual(keyboard_scan(RawKeyboard(0x1D, 2, 0, 0x11)), 0x11D)
        self.assertEqual(keyboard_scan(RawKeyboard(0x45, 4, 0, 0x13)), 0x245)
        self.assertIsNone(keyboard_scan(RawKeyboard(0x2A, 2, 0, 0x10)))

    def test_chord_uses_only_k80_and_triggers_once_after_release(self):
        from types import SimpleNamespace
        app = SimpleNamespace()
        app.device = Device("board", frozenset({"k80"}), None)
        app.pressed = {}
        app.capturing = False
        app.pending = None
        app.profiles = defaults()
        app.profile = app.profiles["profiles"]["Default"]
        app.profile["shortcuts"].append(new_binding(("Ctrl",), 0x20, "Media", "Mute"))
        app.shortcuts_enabled = SimpleNamespace(isChecked=lambda: True)
        app.pages = SimpleNamespace(currentIndex=lambda: 2)
        app.paint_keys = lambda: None
        app.action_status = SimpleNamespace(setText=lambda value: None)
        app.release = lambda scan: ControlCenter.release(app, scan)
        with patch("k80_control.perform") as perform:
            for path in ("laptop", "k80"):
                ControlCenter.key_event(app, path, 0x1D, True)
                ControlCenter.key_event(app, path, 0x20, True)
                ControlCenter.key_event(app, path, 0x20, True)  # Windows repeat
                ControlCenter.key_event(app, path, 0x20, False)
                perform.assert_not_called()
                ControlCenter.key_event(app, path, 0x1D, False)
            perform.assert_called_once_with("Media", "Mute")


if __name__ == "__main__":
    unittest.main()
