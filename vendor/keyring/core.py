"""
vendor/keyring/core.py
Backend resolution and public get/set/delete API.
"""

import sys
from typing import Optional

from .errors import KeyringError, NoKeyringError
from .backends.base import BaseKeyring


_backend: Optional[BaseKeyring] = None


def get_keyring() -> BaseKeyring:
    """Return the best available backend for the current platform."""
    global _backend
    if _backend is not None:
        return _backend

    _backend = _resolve_backend()
    return _backend


def _resolve_backend() -> BaseKeyring:
    platform = sys.platform

    if platform == "darwin":
        from .backends.macos import MacOSKeyring
        b = MacOSKeyring()
        if b.is_available():
            return b

    elif platform == "win32":
        from .backends.windows import WindowsKeyring
        b = WindowsKeyring()
        if b.is_available():
            return b

    elif platform.startswith("linux"):
        from .backends.secretservice import SecretServiceKeyring
        b = SecretServiceKeyring()
        if b.is_available():
            return b

    from .backends.fail import FailKeyring
    return FailKeyring()


def get_password(service: str, username: str) -> Optional[str]:
    """
    Retrieve a password from the OS keychain.

    Returns the password string, or None if no credential is stored.
    Raises KeyringError on backend failure.
    """
    return get_keyring().get_password(service, username)


def set_password(service: str, username: str, password: str) -> None:
    """
    Store a password in the OS keychain.

    Raises KeyringError on backend failure.
    """
    get_keyring().set_password(service, username, password)


def delete_password(service: str, username: str) -> None:
    """
    Delete a stored credential from the OS keychain.

    Raises PasswordDeleteError if the credential does not exist.
    Raises KeyringError on other backend failures.
    """
    get_keyring().delete_password(service, username)
