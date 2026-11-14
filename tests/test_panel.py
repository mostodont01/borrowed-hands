"""The real QML window in-process: panel text can be copied."""

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from borrowed_hands.app import Backend, create_window


def test_copy_button_copies_instruction(qapp, qtbot, tmp_path):
    backend = Backend()
    engine = QQmlApplicationEngine()
    window = create_window(engine, backend, "about:blank", tmp_path / "profile")
    backend.handle({"cmd": "say", "text": "Type 'wifi usb adaptér' and press Enter"}, lambda r: None)

    text = window.findChild(QObject, "instructionText")
    assert text.property("readOnly") and text.property("selectByMouse")
    qtbot.waitUntil(lambda: text.property("text") == "Type 'wifi usb adaptér' and press Enter")

    button = window.findChild(QObject, "copyButton")
    button.clicked.emit()
    assert QGuiApplication.clipboard().text() == "Type 'wifi usb adaptér' and press Enter"
    window.close()
