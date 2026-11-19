"""Qt styling and the shared 87-key keyboard display."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QWidget

from k80_input import LAYOUT

STYLE = """
QWidget { color: #eef0fa; font-family: "Segoe UI"; font-size: 13px; }
QMainWindow, QDialog, QMessageBox, QWidget#workspace { background: #101421; }
QFrame#sidebar { background: #131827; border-right: 1px solid #262e45; }
QLabel#brand { font-size: 14px; font-weight: 700; }
QLabel#brandSubtitle { color: #a8b2cf; font-size: 10px; }
QLabel#credit { color: #a8b2cf; font-size: 11px; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #a8b2cf; }
QLabel#value { color: #c1c7ff; font-weight: 700; min-width: 40px; }
QLabel#section { font-size: 16px; font-weight: 700; }
QLabel#connection { color: #74e6cb; font-weight: 600; background: #192d32;
    border: 1px solid #284a4c; border-radius: 13px; padding: 5px 11px; }
QLabel#connection[online="false"] { color: #f0c098; background: #302722; border-color: #4a392f; }
QLabel#hardware { color: #b8c0d9; }
QFrame#card { background: #181e30; border: 1px solid #2a334d; border-radius: 14px; }
QPushButton, QComboBox, QLineEdit { padding: 7px 12px; background: #232b43;
    border: 1px solid #35415f; border-radius: 8px; color: #eef0fa; min-height: 20px; }
QPushButton:hover, QComboBox:hover { background: #2d3857; border-color: #58678c; }
QPushButton:focus-visible, QLineEdit:focus, QComboBox:focus { border-color: #a6afff; }
QPushButton:disabled, QComboBox:disabled, QLineEdit:disabled, QCheckBox:disabled {
    background: #1b2337; color: #7f89a6; border-color: #2a334d; }
QPushButton#primary { background: #a6afff; color: #121733; font-weight: 700; border-color: #a6afff; }
QPushButton#primary:hover { background: #c2c9ff; }
QPushButton#primary:disabled { background: #28314d; color: #7f89a6; border-color: #2a334d; }
QPushButton#nav { text-align: left; padding: 10px 13px; background: transparent;
    color: #aeb8d4; border: 1px solid transparent; font-weight: 600; }
QPushButton#nav:hover { background: #202940; color: #eef0fa; }
QPushButton#nav:checked { background: #283152; color: #d2d7ff; border-color: #3d4b74; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { width: 22px; border: none; }
QComboBox QAbstractItemView { background: #202940; color: #eef0fa; padding: 4px;
    border: 1px solid #455472; selection-background-color: #404f78; }
QSlider::groove:horizontal { height: 5px; background: #303955; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #8f9bff; border-radius: 2px; }
QSlider::handle:horizontal { width: 15px; margin: -5px 0; background: #c7ceff; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: #67728d; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 15px; height: 15px; background: #222b44;
    border: 1px solid #536184; border-radius: 4px; }
QCheckBox::indicator:checked { background: #a6afff; border: 3px solid #3e507e; width: 11px; height: 11px; }
QTableWidget { background: #171e30; alternate-background-color: #1d263b; color: #eef0fa;
    selection-background-color: #33436b; border: 1px solid #303c58; border-radius: 8px; }
QHeaderView::section { background: #242d46; border: 0; color: #ccd4f0;
    padding: 8px; font-weight: 600; }
QToolTip { background: #232b43; color: #eef0fa; border: 1px solid #58678c; padding: 5px; }
"""

UNIT = 38
WIDTHS = {
    "Backspace": 2, "Tab": 1.5, "\\": 1.5, "Caps Lock": 1.75, "Enter": 2.25,
    "L Shift": 2.25, "R Shift": 2.75, "Space": 6.25,
    **{name: 1.25 for name in ("L Ctrl", "L Win", "L Alt", "R Alt", "R Win", "Menu", "R Ctrl")},
}


class ComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#b8c4ec" if self.isEnabled() else "#64708a"), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        x, y = self.width() - 15, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


class KeyboardView(QWidget):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview
        self.held = set()
        self.seen = set()
        self.brightness = 0
        self.setAccessibleName("Keyboard layout preview" if preview else "87-key test status")
        self.setMinimumHeight(155 if preview else 210)

    def sizeHint(self):
        return QSize(730, 165 if self.preview else 245)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = 18.5 * UNIT
        height = 6 * UNIT
        scale = min((self.width() - 6) / width, (self.height() - 6) / height)
        painter.translate(QPointF((self.width() - width * scale) / 2, (self.height() - height * scale) / 2))
        painter.scale(scale, scale)
        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        y = 0
        for row, keys in enumerate(LAYOUT):
            x = 0
            for index, (label, scan) in enumerate(keys):
                if row == 0:
                    x += {1: UNIT, 5: UNIT / 2, 9: UNIT / 2, 13: UNIT / 2}.get(index, 0)
                elif label in ("Ins", "Del", "←"):
                    x = 15.5 * UNIT
                elif label == "↑":
                    x = 16.5 * UNIT
                units = WIDTHS.get(label, 1)
                rect = QRectF(x + 1, y + 1, units * UNIT - 4, UNIT - 5)
                self.paint_key(painter, rect, label, scan, row, x)
                x += units * UNIT
            y += UNIT

    def paint_key(self, painter, rect, label, scan, row, x):
        if scan in self.held:
            fill, border, text = "#76e7cc", "#b4f8e9", "#12252f"
        elif scan in self.seen:
            fill, border, text = "#3a4879", "#687dc8", "#ecf0ff"
        elif self.preview and self.brightness:
            tint = (row * 15 + int(x / UNIT) * 4) % 70
            glow = self.brightness / 100
            fill = QColor.fromHsv(225 + tint // 3, 94, 51 + round(glow * (42 + tint // 2)))
            border = QColor.fromHsv(223 + tint // 3, 94, 79 + round(glow * (65 + tint)))
            text = "#e5eaff"
        else:
            fill, border, text = "#202840", "#34415d", "#bbc6e5"
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
