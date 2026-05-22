"""Entry point for the StructLab PyQt6 desktop application.

Run with:
    python -m ui_qt.main
or (from project root):
    python ui_qt/main.py
"""

import sys
import os
import traceback
from pathlib import Path

# Make sure the project root is on sys.path when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QMessageBox
from ui_qt.main_window import MainWindow
from ui_qt.theme import STYLESHEET

_CRASH_LOG = Path.home() / ".structlab" / "crash.log"


def _exception_handler(exc_type, exc_value, exc_tb) -> None:
    """Catch unhandled exceptions, show a dialog, and write a crash log."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        _CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        _CRASH_LOG.write_text(tb_text, encoding="utf-8")
    except Exception:
        pass

    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setWindowTitle("StructLab — Unexpected Error")
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText(
            "An unexpected error occurred.\n\n"
            "Your model has been autosaved and can be recovered on next launch.\n\n"
            f"Crash log written to:\n{_CRASH_LOG}"
        )
        msg.setDetailedText(tb_text)
        msg.exec()
    else:
        sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> None:
    sys.excepthook = _exception_handler
    app = QApplication(sys.argv)
    app.setApplicationName("StructLab")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
