"""
vendor/keyring/__init__.py
Minimal pure-Python keyring facade pinned to the interface used by
st-fast-autocomplete. Dispatches to the appropriate platform backend.

Supported platforms:
  macOS   → backends.macos   (security CLI)
  Windows → backends.windows (ctypes / wincred)
  Linux   → backends.secretservice (dbus-based SecretService)
  Fallback→ backends.fail    (raises KeyringError with a clear message)

Public API (mirrors keyring 25.x):
  get_password(service, username) -> str | None
  set_password(service, username, password) -> None
  delete_password(service, username) -> None
  get_keyring() -> BaseKeyring
"""

import sys
from .core import get_keyring, get_password, set_password, delete_password
from .errors import KeyringError, PasswordDeleteError, InitError

__version__ = "25.0.0+vendor"
__all__ = [
    "get_password",
    "set_password",
    "delete_password",
    "get_keyring",
    "KeyringError",
    "PasswordDeleteError",
    "InitError",
]
