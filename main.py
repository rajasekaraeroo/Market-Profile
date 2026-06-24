"""Entry point: launches the Market Profile desktop UI.

Usage: python main.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def _load_env() -> None:
    """Load a .env file placed next to the application.

    When frozen by PyInstaller, the project root isn't __file__'s directory
    but sys.executable's directory (the folder the user drops the .exe in).
    """
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")


def main() -> None:
    _load_env()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 700)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
