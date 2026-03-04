"""
vendor/keyring/backends/secretservice.py
Linux SecretService backend using the `secret-tool` CLI.
Avoids the dbus Python module which is not available in ST's embedded Python.
Requires: libsecret-tools (apt: libsecret-tools, dnf: libsecret)
"""

import shutil
import subprocess
import sys
from typing import Optional

from .base import BaseKeyring
from ..errors import KeyringError, PasswordDeleteError


class SecretServiceKeyring(BaseKeyring):

    def is_available(self) -> bool:
        return (
            sys.platform.startswith("linux")
            and shutil.which("secret-tool") is not None
        )

    def get_password(self, service: str, username: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["secret-tool", "lookup", "service", service, "username", username],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except OSError as exc:
            raise KeyringError(f"secret-tool lookup failed: {exc}") from exc

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            result = subprocess.run(
                [
                    "secret-tool", "store",
                    "--label", f"{service}/{username}",
                    "service", service,
                    "username", username,
                ],
                input=password,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise KeyringError(
                    f"secret-tool store failed: {result.stderr.strip()}"
                )
        except OSError as exc:
            raise KeyringError(f"secret-tool store failed: {exc}") from exc

    def delete_password(self, service: str, username: str) -> None:
        try:
            result = subprocess.run(
                ["secret-tool", "clear", "service", service, "username", username],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise PasswordDeleteError(
                    f"Credential not found: service={service!r} username={username!r}"
                )
        except OSError as exc:
            raise KeyringError(f"secret-tool clear failed: {exc}") from exc