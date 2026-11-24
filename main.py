"""Punto de entrada de Vision Tracker."""
import sys

from PySide6.QtWidgets import QApplication

from config.settings import APP_NAME, RESULTS_DIR, STYLES_PATH
from interface.main_window import MainWindow


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if STYLES_PATH.exists():
        app.setStyleSheet(STYLES_PATH.read_text(encoding="utf-8"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
