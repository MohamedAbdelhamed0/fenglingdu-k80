"""Qt desktop control panel for the wired F-ENGLINGDU K80."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
from queue import Empty
import sys

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSlider, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from k80_input import KEY_NAMES, MEDIA, MODIFIERS, RawInput, canonical, perform
from k80_profiles import ACTIONS, EFFECTS, default_profile, defaults, load, new_binding, save
from k80_usb import P, bind, close, discover, kernel, settings
from k80_widgets import ComboBox, KeyboardView, STYLE

ICON = Path(__file__).with_name("k80.ico")
APP_NAME = "FENGLINGDU K80 – Wireless Gaming Keyboard"
CREATOR_URL = "https://github.com/MohamedAbdelhamed0"
PAGE_COPY = (
    ("Lighting", "Adjust the backlight on your wired K80."),
    ("Key tester", "Check each physical key and see simultaneous presses."),
    ("Windows shortcuts", "Run actions from key combinations on this K80."),
    ("Keyboard guide", "Use the controls built into the keyboard."),
)


def label(text, style=None):
    widget = QLabel(text)
    if style:
        widget.setObjectName(style)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(action)
    if primary:
        widget.setObjectName("primary")
    return widget


def card(parent):
    frame = QFrame()
    frame.setObjectName("card")
    parent.addWidget(frame)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(17, 15, 17, 15)
    layout.setSpacing(10)
    return layout


class ControlCenter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1060, 735)
        self.setMinimumSize(890, 680)
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.task = None
        self.device = self.state = None
        self.device_generation = 0
        self.lighting_pending = {}
        self.refresh_requested = False
        self.close_requested = False
        self.input = None
        self.pressed = {}
        self.pending = None
        self.captured = None
        self.capturing = False
        self.seen = set()
        self.profile_error = None
        try:
            self.profiles = load()
        except ValueError as exc:
            self.profiles = defaults()
            self.profile_error = str(exc)

        self.apply_timer = self.timer(170, self.flush_lighting, single=True)
        self.pause_timer = self.timer(170, lambda: self.release(0x245), single=True)
        self.task_timer = self.timer(15, self.poll_job)
        self.input_timer = self.timer(15, self.drain_input)
        self.scan_timer = self.timer(1300, self.scan)
        self.build()
        self.refresh_profile()
        self.update_controls()
        QApplication.instance().applicationStateChanged.connect(self.application_state_changed)
        QTimer.singleShot(0, self.start)

    def timer(self, delay, callback, single=False):
        timer = QTimer(self)
        timer.setInterval(delay)
        timer.setSingleShot(single)
        timer.timeout.connect(callback)
        return timer

    def start(self):
        try:
            self.input = RawInput(int(self.winId()))
        except OSError as exc:
            self.action_status.setText(f"Windows Raw Input is unavailable. {exc}")
            self.key_status.setText("Windows Raw Input is unavailable.")
        else:
            self.input_timer.start()
        self.scan_timer.start()
        self.scan()
        self.update_controls()

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(198)
        shell.addWidget(bar)
        sidebar = QVBoxLayout(bar)
        sidebar.setContentsMargins(15, 22, 15, 18)
        sidebar.setSpacing(7)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICON)).pixmap(39, 39))
        brand.addWidget(logo)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        identity.addWidget(label("FENGLINGDU K80", "brand"))
        identity.addWidget(label("Wireless gaming keyboard", "brandSubtitle"))
        brand.addLayout(identity)
        brand.addStretch()
        sidebar.addLayout(brand)
        sidebar.addSpacing(22)
        self.navigation = []
        for index, (title, _description) in enumerate(PAGE_COPY):
            entry = button(title, lambda _checked=False, i=index: self.open_page(i))
            entry.setCheckable(True)
            entry.setObjectName("nav")
            self.navigation.append(entry)
            sidebar.addWidget(entry)
        sidebar.addStretch()
        sidebar.addWidget(label("Active profile", "muted"))
        self.profile_picker = ComboBox()
        self.profile_picker.setAccessibleName("Active profile")
        self.profile_picker.currentTextChanged.connect(self.switch_profile)
        sidebar.addWidget(self.profile_picker)
        profile_buttons = QHBoxLayout()
        self.new_profile_button = button("New", self.create_profile)
        self.delete_profile_button = button("Delete", self.delete_profile)
        profile_buttons.addWidget(self.new_profile_button)
        profile_buttons.addWidget(self.delete_profile_button)
        sidebar.addLayout(profile_buttons)
        sidebar.addSpacing(9)
        credit = label(f'Created by <a href="{CREATOR_URL}" style="color:#c1caff">Mohamed Abdelhamed</a>', "credit")
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        sidebar.addWidget(credit)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        shell.addWidget(workspace, 1)
        content = QVBoxLayout(workspace)
        content.setContentsMargins(25, 21, 25, 19)
        content.setSpacing(13)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.setSpacing(1)
        self.title = label("", "title")
        self.subtitle = label("", "subtitle")
        headings.addWidget(self.title)
        headings.addWidget(self.subtitle)
        header.addLayout(headings)
        header.addStretch()
        self.connection = label("Looking for K80", "connection")
        self.connection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.connection, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(header)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        for build_page in (self.build_lighting, self.build_tester, self.build_shortcuts, self.build_guide):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            build_page(layout)
            self.pages.addWidget(page)
        self.open_page(0)

    def open_page(self, index):
        self.pages.setCurrentIndex(index)
        self.title.setText(PAGE_COPY[index][0])
        self.subtitle.setText(PAGE_COPY[index][1])
        for number, item in enumerate(self.navigation):
            item.setChecked(number == index)
        if self.capturing:
            self.reset_capture()

    def build_lighting(self, page):
        preview_card = card(page)
        top = QHBoxLayout()
        top.addWidget(label("Keyboard preview", "section"))
        top.addStretch()
        self.effect_preview = label("", "muted")
        top.addWidget(self.effect_preview)
        preview_card.addLayout(top)
        self.preview = KeyboardView(preview=True)
        preview_card.addWidget(self.preview)

        options = card(page)
        top = QHBoxLayout()
        top.addWidget(label("Onboard lighting", "section"))
        top.addStretch()
        self.read_button = button("Read keyboard", self.request_read)
        top.addWidget(self.read_button)
        options.addLayout(top)
        grid = QGridLayout()
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        options.addLayout(grid)
        grid.addWidget(label("Effect"), 0, 0)
        self.mode = ComboBox()
        self.mode.setAccessibleName("Effect")
        for mode, title in EFFECTS.items():
            self.mode.addItem(title, mode)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        grid.addWidget(self.mode, 0, 1, 1, 2)
        self.brightness, self.brightness_value = self.slider(grid, 1, "Brightness", 1, 100, 80)
        self.speed, self.speed_value = self.slider(grid, 2, "Effect speed", 0, 4, 2)
        self.brightness.valueChanged.connect(self.brightness_changed)
        self.speed.valueChanged.connect(self.speed_changed)
        self.enabled = QCheckBox("Backlight on")
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(self.backlight_changed)
        self.win_lock = QCheckBox("Windows key lock")
        self.win_lock.toggled.connect(lambda checked: self.queue_lighting({"win_lock": checked}))
        switches = QHBoxLayout()
        switches.setSpacing(22)
        switches.addWidget(self.enabled)
        switches.addWidget(self.win_lock)
        switches.addStretch()
        grid.addLayout(switches, 3, 1, 1, 2)

        footer = QHBoxLayout()
        self.save_light = button("Save to profile", self.save_lighting)
        self.load_light = button("Load profile lighting", self.load_lighting)
        footer.addWidget(self.save_light)
        footer.addWidget(self.load_light)
        footer.addStretch()
        options.addLayout(footer)
        self.hardware_status = label("Connect USB-C and set the switch to Cable.", "hardware")
        self.hardware_status.setWordWrap(True)
        options.addWidget(self.hardware_status)
        page.addStretch(1)

    def slider(self, layout, row, text, low, high, initial):
        layout.addWidget(label(text), row, 0)
        control = QSlider(Qt.Orientation.Horizontal)
        control.setAccessibleName(text)
        control.setRange(low, high)
        control.setValue(initial)
        control.setPageStep(5 if high == 100 else 1)
        control.sliderReleased.connect(self.flush_lighting)
        value = label("", "value")
        layout.addWidget(control, row, 1)
        layout.addWidget(value, row, 2)
        return control, value

    def build_tester(self, page):
        layout = card(page)
        row = QHBoxLayout()
        self.key_status = label("Connect the K80 to test its keys.", "section")
        row.addWidget(self.key_status)
        row.addStretch()
        row.addWidget(button("Clear test", self.reset_test))
        layout.addLayout(row)
        self.tester = KeyboardView()
        layout.addWidget(self.tester)
        layout.addWidget(label("Mint shows keys held now. Blue shows keys tested so far.", "muted"))
        page.addStretch()

    def build_shortcuts(self, page):
        layout = card(page)
        toggles = QHBoxLayout()
        self.shortcuts_enabled = QCheckBox("Enable shortcuts")
        self.background = QCheckBox("Run in background")
        for toggle in (self.shortcuts_enabled, self.background):
            toggle.toggled.connect(self.change_listening)
            toggles.addWidget(toggle)
        toggles.addStretch()
        layout.addLayout(toggles)
        layout.addWidget(label("Shortcuts start paused. The original chord still reaches Windows.", "muted"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Chord", "Action", "Value"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(173)
        layout.addWidget(self.table)
        editor = QGridLayout()
        editor.setColumnStretch(2, 1)
        self.capture_button = button("Capture K80 chord", self.capture)
        self.action = ComboBox()
        self.action.setAccessibleName("Shortcut action")
        self.action.addItems(ACTIONS)
        self.action.currentTextChanged.connect(self.action_changed)
        self.value = QLineEdit()
        self.value.setAccessibleName("Shortcut value")
        self.value.setMaxLength(2048)
        self.media = ComboBox()
        self.media.setAccessibleName("Media action")
        self.media.addItems(list(MEDIA))
        self.browse = button("Browse", self.pick_file)
        for column, control in enumerate((self.capture_button, self.action, self.value, self.browse)):
            editor.addWidget(control, 0, column)
        editor.addWidget(self.media, 0, 2)
        editor.addWidget(button("Save shortcut", self.save_binding, primary=True), 1, 0)
        editor.addWidget(button("Remove selected", self.remove_binding), 1, 1)
        layout.addLayout(editor)
        self.action_status = label("Shortcuts are paused.", "hardware")
        self.action_status.setWordWrap(True)
        layout.addWidget(self.action_status)
        self.action_changed(self.action.currentText())
        page.addStretch()

    @staticmethod
    def build_guide(page):
        layout = card(page)
        guide = QGridLayout()
        guide.setVerticalSpacing(13)
        guide.setHorizontalSpacing(22)
        for row, (keys, description) in enumerate((
            ("Fn + PrtSc", "Cycle the onboard lighting modes."),
            ("Fn + ScrLk", "Toggle the backlight."),
            ("Fn + ↑ / ↓", "Increase or decrease brightness."),
            ("Fn + ← / →", "Decrease or increase lighting speed."),
            ("Fn + Tab", "Switch Windows and Mac layouts."),
            ("Fn + Left Win", "Toggle the Windows key lock in Windows mode."),
            ("Fn + Q / W / E", "Select a Bluetooth slot. Hold for 3 seconds to pair."),
            ("Fn + R", "Select 2.4 GHz. Hold for 3 seconds to pair."),
            ("Fn + Space", "Show battery level on the number row in wireless mode."),
        )):
            guide.addWidget(label(keys, "value"), row, 0)
            detail = label(description, "muted")
            detail.setWordWrap(True)
            guide.addWidget(detail, row, 1)
        guide.setColumnStretch(1, 1)
        layout.addLayout(guide)
        note = label("USB control is unverified for per-key lighting, onboard remaps, battery, wireless settings, "
                     "and Windows/Mac layout.", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        page.addStretch()

    def set_connection(self, text, online):
        self.connection.setText(text)
        self.connection.setProperty("online", online)
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)

    def update_controls(self):
        ready = self.device is not None and self.state is not None
        self.mode.setEnabled(ready)
        self.brightness.setEnabled(ready and self.enabled.isChecked())
        for control in (self.speed, self.enabled, self.win_lock):
            control.setEnabled(ready)
        self.read_button.setEnabled(self.device is not None and not self.refresh_requested)
        self.save_light.setEnabled(ready and self.profile_error is None)
        self.load_light.setEnabled(ready and self.profile["lighting"] is not None)
        self.shortcuts_enabled.setEnabled(self.input is not None and self.profile_error is None)
        self.background.setEnabled(self.shortcuts_enabled.isChecked())
        self.capture_button.setEnabled(self.device is not None and self.input is not None)
        self.new_profile_button.setEnabled(self.profile_error is None)
        self.delete_profile_button.setEnabled(self.profile_error is None and len(self.profiles["profiles"]) > 1)
        self.brightness_value.setText(f"{self.brightness.value()}%")
        self.speed_value.setText(f"{self.speed.value()} / 4")
        self.effect_preview.setText(self.mode.currentText() if ready else "Connect via USB-C")
        self.preview.brightness = self.brightness.value() if ready and self.enabled.isChecked() else 0
        self.preview.update()

    def scan(self):
        if self.task:
            return
        try:
            device = discover()
        except OSError as exc:
            self.change_device(None)
            self.set_connection("Connection unavailable", False)
            self.hardware_status.setText(str(exc))
            return
        if device != self.device:
            self.change_device(device)
        elif not device:
            self.set_connection("K80 disconnected", False)

    def change_device(self, device):
        self.device_generation += 1
        self.device, self.state = device, None
        self.lighting_pending.clear()
        self.refresh_requested = False
        self.apply_timer.stop()
        self.reset_capture()
        self.reset_test()
        self.set_connection("USB-C connected" if device else "K80 disconnected", bool(device))
        self.hardware_status.setText("Reading keyboard…" if device else "Connect USB-C and set the switch to Cable.")
        self.update_controls()
        if device:
            self.request_read()

    def request_read(self):
        if not self.device:
            return
        self.refresh_requested = True
        self.update_controls()
        self.flush_lighting()

    def mode_changed(self, _index):
        if self.mode.currentData() is not None:
            self.queue_lighting({"mode": self.mode.currentData()})

    def brightness_changed(self, value):
        if self.enabled.isChecked():
            self.queue_lighting({"brightness": value}, slider=True)

    def speed_changed(self, value):
        self.queue_lighting({"speed": value}, slider=True)

    def backlight_changed(self, checked):
        self.queue_lighting({"brightness": self.brightness.value() if checked else 0})

    def queue_lighting(self, delta, slider=False):
        if self.state is None:
            return
        self.lighting_pending.update(delta)
        self.update_controls()
        self.hardware_status.setText("Updating keyboard…")
        # Coalesce rapid slider edits into one persistent write.
        self.apply_timer.start(170 if slider else 0)

    def flush_lighting(self):
        self.apply_timer.stop()
        if self.task or self.device is None:
            return
        if self.lighting_pending and self.state is not None:
            light = self.lighting_pending
            self.lighting_pending = {}
            base = self.state
            changes = {}
            for name, value in light.items():
                if name == "win_lock":
                    changes[26] = (base[26] & 0xFE) | int(value)
                elif name == "speed":
                    changes[13] = 4 - value
                else:
                    changes[11 if name == "mode" else 12] = value
            changes = {offset: value for offset, value in changes.items() if base[offset] != value}
            if changes:
                self.launch_job(changes, base)
                return
            self.hardware_status.setText("Lighting is synced. Changes apply automatically.")
        if self.refresh_requested:
            self.refresh_requested = False
            self.hardware_status.setText("Reading keyboard…")
            self.launch_job(None, None)
        elif self.close_requested:
            QTimer.singleShot(0, self.close)

    def launch_job(self, changes, base):
        self.task = (
            self.worker.submit(settings, self.device, changes, base),
            self.device_generation,
            bool(changes),
        )
        self.task_timer.start()

    def poll_job(self):
        future, generation, writing = self.task
        if not future.done():
            return
        self.task_timer.stop()
        self.task = None
        if generation != self.device_generation:
            self.scan()
            if self.close_requested:
                self.close()
            return
        try:
            state = future.result()
        except (OSError, ValueError) as exc:
            self.state = None
            self.lighting_pending.clear()
            self.refresh_requested = False
            self.hardware_status.setText(f"{exc} Select Read keyboard to reconnect to its current settings.")
        else:
            self.state = state
            light = self.decode(state)
            light.update(self.lighting_pending)
            self.show_light(light)
            self.hardware_status.setText("Updating keyboard…" if self.lighting_pending
                                         else "Lighting is synced. Changes apply automatically.")
        self.update_controls()
        if not self.apply_timer.isActive() or self.close_requested or not writing:
            self.flush_lighting()

    @staticmethod
    def decode(state):
        return {"mode": state[11], "brightness": state[12], "speed": 4 - state[13],
                "win_lock": bool(state[26] & 1)}

    def show_light(self, light):
        with QSignalBlocker(self.mode), QSignalBlocker(self.brightness), QSignalBlocker(self.speed), \
                QSignalBlocker(self.enabled), QSignalBlocker(self.win_lock):
            index = self.mode.findData(light["mode"])
            if index < 0:
                self.mode.addItem(f"Onboard effect {light['mode']}", light["mode"])
                index = self.mode.count() - 1
            self.mode.setCurrentIndex(index)
            if light["brightness"]:
                self.brightness.setValue(light["brightness"])
            self.enabled.setChecked(bool(light["brightness"]))
            self.speed.setValue(light["speed"])
            self.win_lock.setChecked(light["win_lock"])

    @property
    def profile(self):
        return self.profiles["profiles"][self.profiles["active"]]

    def refresh_profile(self):
        with QSignalBlocker(self.profile_picker):
            self.profile_picker.clear()
            self.profile_picker.addItems(list(self.profiles["profiles"]))
            self.profile_picker.setCurrentText(self.profiles["active"])
        self.table.setRowCount(len(self.profile["shortcuts"]))
        for row, item in enumerate(self.profile["shortcuts"]):
            values = ("+".join([*item["modifiers"], KEY_NAMES[item["key"]]]),
                      item["action"], item["value"].replace("\n", " ")[:140])
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        if self.profile_error:
            self.action_status.setText(self.profile_error)
        self.pending = None
        self.update_controls()

    def update_profiles(self, edit):
        if self.profile_error:
            QMessageBox.warning(self, "Profiles unavailable", self.profile_error)
            return False
        updated = deepcopy(self.profiles)
        edit(updated)
        try:
            save(updated)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not save profile", str(exc))
            self.refresh_profile()
            return False
        self.profiles = updated
        self.refresh_profile()
        return True

    def switch_profile(self, name):
        if name and name != self.profiles["active"]:
            self.update_profiles(lambda data: data.update(active=name))
            self.reset_capture()

    def create_profile(self):
        name, accepted = QInputDialog.getText(self, "New profile", "Profile name")
        name = name.strip()
        if not accepted:
            return
        if not name or len(name) > 50 or name.casefold() in {
            saved.casefold() for saved in self.profiles["profiles"]
        }:
            QMessageBox.warning(self, "Profile name", "Use a unique name with up to 50 characters.")
            return

        def edit(data):
            data["profiles"][name] = default_profile()
            data["active"] = name
        if self.update_profiles(edit):
            self.reset_capture()

    def delete_profile(self):
        name = self.profiles["active"]
        if QMessageBox.question(self, "Delete profile", f"Delete {name} and its shortcuts?") != QMessageBox.StandardButton.Yes:
            return

        def edit(data):
            del data["profiles"][name]
            data["active"] = next(iter(data["profiles"]))
        if self.update_profiles(edit):
            self.reset_capture()

    def save_lighting(self):
        light = {"mode": self.mode.currentData(), "brightness": self.brightness.value() if self.enabled.isChecked() else 0,
                 "speed": self.speed.value(), "win_lock": self.win_lock.isChecked()}
        if light["mode"] not in EFFECTS:
            self.hardware_status.setText("Select a supported effect before saving it to a profile.")
            return
        name = self.profiles["active"]
        if self.update_profiles(lambda data: data["profiles"][name].update(lighting=light)):
            self.hardware_status.setText(f"Lighting saved to {name}.")

    def load_lighting(self):
        light = self.profile["lighting"]
        if light:
            self.show_light(light)
            self.queue_lighting(light)

    def action_changed(self, action):
        self.value.clear()
        self.value.setVisible(action != "Media")
        self.media.setVisible(action == "Media")
        self.browse.setVisible(action == "Open file or app")
        self.value.setPlaceholderText({
            "Open file or app": "Path to a local file or app",
            "Type text": "Text to type",
            "Send keys": "Ctrl+S, Enter",
        }.get(action, ""))

    def pick_file(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Choose a file or app")
        if path:
            self.value.setText(path)

    def change_listening(self):
        self.reset_test()
        self.reset_capture()
        enabled = self.shortcuts_enabled.isChecked()
        if self.input:
            self.input.listen(enabled and self.background.isChecked())
        self.action_status.setText("Shortcuts enabled." if enabled else "Shortcuts are paused.")
        self.update_controls()

    def capture(self):
        self.captured = self.pending = None
        self.capturing = True
        self.capture_button.setText("Press a K80 chord…")
        self.action_status.setText("Hold a modifier and press a regular key on the K80.")
        self.capture_button.setFocus()

    def reset_capture(self):
        self.captured = None
        self.capturing = False
        self.capture_button.setText("Capture K80 chord")

    def save_binding(self):
        if self.captured is None:
            self.action_status.setText("Capture a K80 chord first.")
            return
        modifiers, key = self.captured
        action = self.action.currentText()
        try:
            item = new_binding(modifiers, key, action, self.media.currentText() if action == "Media" else self.value.text())
        except ValueError as exc:
            self.action_status.setText(str(exc))
            return
        name = self.profiles["active"]

        def edit(data):
            entries = data["profiles"][name]["shortcuts"]
            for index, existing in enumerate(entries):
                if existing["key"] == key and existing["modifiers"] == list(modifiers):
                    entries[index] = item
                    return
            entries.append(item)
        if self.update_profiles(edit):
            self.reset_capture()
            self.action_status.setText(f"Shortcut saved to {name}.")

    def remove_binding(self):
        index = self.table.currentRow()
        name = self.profiles["active"]
        if index >= 0 and self.update_profiles(lambda data: data["profiles"][name]["shortcuts"].pop(index)):
            self.action_status.setText("Shortcut removed.")

    def drain_input(self):
        for _ in range(256):
            try:
                path, scan, down = self.input.events.get_nowait()
            except Empty:
                return
            if scan is not None:
                self.key_event(path, scan, down)
            elif self.device and path in self.device.keyboard_paths and not down:
                self.change_device(None)
            elif path and "hid#vid_5566&pid_0008&" in path and down:
                self.scan()

    def application_state_changed(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.reset_capture()
            if not (self.shortcuts_enabled.isChecked() and self.background.isChecked()):
                self.clear_held()

    def reset_test(self):
        self.seen.clear()
        self.clear_held()
        if self.device:
            self.key_status.setText("0 of 87 keys tested")
        elif self.input:
            self.key_status.setText("Connect the K80 to test its keys.")

    def clear_held(self):
        self.pause_timer.stop()
        self.pressed.clear()
        self.pending = None
        self.paint_keys()

    def paint_keys(self):
        self.tester.held = self.pressed
        self.tester.seen = self.seen
        self.tester.update()
        self.preview.held = self.pressed
        self.preview.update()

    def release(self, scan):
        self.pressed.pop(scan, None)
        self.paint_keys()
        if not self.pressed and self.pending is not None:
            item, self.pending = self.pending, None
            try:
                perform(item["action"], item["value"])
                self.action_status.setText(f"Ran {item['action'].lower()}.")
            except OSError as exc:
                self.action_status.setText(str(exc))

    def key_event(self, path, scan, down):
        if not self.device or path not in self.device.keyboard_paths:
            return
        if not down:
            if self.pressed.get(scan) == path:
                self.release(scan)
            return
        if scan in self.pressed:
            return
        self.pressed[scan] = path
        if self.pages.currentIndex() == 1:
            self.seen.add(scan)
            self.key_status.setText(f"{len(self.seen)} of 87 keys tested")
        self.paint_keys()
        if scan == 0x245:
            self.pause_timer.start()
        if scan in MODIFIERS:
            return
        modifiers = canonical(MODIFIERS[key] for key in self.pressed if key in MODIFIERS)
        if self.capturing:
            if modifiers:
                self.captured = (modifiers, scan)
                self.capturing = False
                self.capture_button.setText("+".join((*modifiers, KEY_NAMES[scan])))
                self.action_status.setText("Choose an action and save the shortcut.")
            return
        if self.shortcuts_enabled.isChecked():
            self.pending = next((item for item in self.profile["shortcuts"]
                                 if item["key"] == scan and tuple(item["modifiers"]) == modifiers), None)

    def closeEvent(self, event):
        if self.task or self.lighting_pending:
            event.ignore()
            self.close_requested = True
            self.flush_lighting()
            return
        self.pending = None
        for timer in (self.apply_timer, self.task_timer, self.input_timer, self.scan_timer, self.pause_timer):
            timer.stop()
        if self.input:
            self.input.close()
            self.input = None
        self.worker.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main():
    create_mutex = bind(kernel, "CreateMutexW", W.HANDLE, P, W.BOOL, W.LPCWSTR)
    mutex = create_mutex(None, False, "Local\\FEnglingduK80ControlCenter")
    error = C.get_last_error()
    if not mutex:
        raise C.WinError(error)
    if error == 183:  # ERROR_ALREADY_EXISTS
        close(mutex)
        return
    shell = C.WinDLL("shell32")
    set_app_id = bind(shell, "SetCurrentProcessExplicitAppUserModelID", W.LONG, W.LPCWSTR)
    set_app_id("FEnglingdu.K80.ControlCenter")
    try:
        app = QApplication(sys.argv)
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion("1.0.0")
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)
        app.setWindowIcon(QIcon(str(ICON)))
        window = ControlCenter()
        window.show()
        return app.exec()
    finally:
        close(mutex)


if __name__ == "__main__":
    sys.exit(main())
