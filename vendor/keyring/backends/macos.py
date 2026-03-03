"""
vendor/keyring/backends/macos.py
macOS Keychain backend using the `security` CLI tool.
No compiled extensions required — pure subprocess calls.
"""

import shutil
import subprocess
from typing import Optional

from .base import BaseKeyring
from ..errors import KeyringError, PasswordDeleteError


class MacOSKeyring(BaseKeyring):

    def is_available(self) -> bool:
        return shutil.which("security") is not None

    def get_password(self, service: str, username: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-s", service,
                    "-a", username,
                    "-w",  # print password only
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None  # item not found
        except OSError as exc:
            raise KeyringError(f"macOS keychain get failed: {exc}") from exc

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            # Delete first to allow update (add-generic-password errors on duplicate)
            self._delete_silent(service, username)
            result = subprocess.run(
                [
                    "security", "add-generic-password",
                    "-s", service,
                    "-a", username,
                    "-w", password,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise KeyringError(f"macOS keychain set failed: {result.stderr.strip()}")
        except OSError as exc:
            raise KeyringError(f"macOS keychain set failed: {exc}") from exc

    def delete_password(self, service: str, username: str) -> None:
        try:
            result = subprocess.run(
                [
                    "security", "delete-generic-password",
                    "-s", service,
                    "-a", username,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise PasswordDeleteError(
                    f"Credential not found or could not be deleted: "
                    f"service={service!r} username={username!r}"
                )
        except OSError as exc:
            raise KeyringError(f"macOS keychain delete failed: {exc}") from exc

    # ------------------------------------------------------------------
    def _delete_silent(self, service: str, username: str) -> None:
        """Delete without raising if the item does not exist."""
        subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", username],
            capture_output=True,
        )
