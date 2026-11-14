import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --no-sandbox").strip()

# Must run before the QApplication exists (pytest-qt creates it lazily).
from PySide6.QtWebEngineQuick import QtWebEngineQuick  # noqa: E402

QtWebEngineQuick.initialize()
