"""GUI login flow for users running the packaged EXE with no Python/terminal
access.

Wraps the existing OAuth helpers in src/data/upstox_auth.py (build_login_url,
exchange_code_for_token, save_token) behind a small dialog: open the login
URL in the system browser, paste back the authorization code, done. No
command line required.
"""

import os
import webbrowser

from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.data import upstox_auth


class UpstoxLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upstox Login")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                "Upstox requires logging in once per trading day.\n\n"
                "1. Click 'Open Login Page' below.\n"
                "2. Log in to Upstox in your browser.\n"
                "3. After login, your browser is redirected to a page whose "
                "URL contains '?code=...'. Copy that code.\n"
                "4. Paste it below and click 'Submit Code'."
            )
        )

        self.open_button = QPushButton("Open Login Page")
        self.open_button.clicked.connect(self._open_login_page)
        layout.addWidget(self.open_button)

        layout.addWidget(QLabel("Authorization code:"))
        self.code_input = QLineEdit()
        layout.addWidget(self.code_input)

        self.submit_button = QPushButton("Submit Code")
        self.submit_button.clicked.connect(self._submit_code)
        layout.addWidget(self.submit_button)

    def _credentials(self):
        api_key = os.environ.get("UPSTOX_API_KEY")
        api_secret = os.environ.get("UPSTOX_API_SECRET")
        redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI")
        if not api_key or not api_secret or not redirect_uri:
            QMessageBox.warning(
                self,
                "Missing configuration",
                "UPSTOX_API_KEY, UPSTOX_API_SECRET and UPSTOX_REDIRECT_URI "
                "must be set in a .env file placed next to the application.",
            )
            return None
        return api_key, api_secret, redirect_uri

    def _open_login_page(self) -> None:
        creds = self._credentials()
        if creds is None:
            return
        api_key, _, redirect_uri = creds
        url = upstox_auth.build_login_url(api_key, redirect_uri)
        webbrowser.open(url)

    def _submit_code(self) -> None:
        creds = self._credentials()
        if creds is None:
            return
        api_key, api_secret, redirect_uri = creds
        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "Missing code", "Paste the authorization code first.")
            return
        try:
            access_token = upstox_auth.exchange_code_for_token(
                api_key, api_secret, redirect_uri, code
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            QMessageBox.critical(self, "Login failed", str(exc))
            return
        upstox_auth.save_token(access_token)
        QMessageBox.information(self, "Login successful", "You're logged in for today.")
        self.accept()
