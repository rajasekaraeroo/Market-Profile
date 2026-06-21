"""Entry point: launches the Market Profile desktop UI.

Usage: python main.py
"""

import sys

from PyQt5.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 700)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
