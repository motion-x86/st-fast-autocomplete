"""
vendor/keyring/errors.py
Exception hierarchy for the vendored keyring package.
"""


class KeyringError(Exception):
    """Base class for all keyring errors."""


class InitError(KeyringError):
    """Raised when a backend cannot be initialised on the current platform."""


class PasswordDeleteError(KeyringError):
    """Raised when a credential cannot be deleted (e.g. not found)."""


class NoKeyringError(KeyringError):
    """Raised when no suitable backend is available."""
