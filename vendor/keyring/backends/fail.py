"""
vendor/keyring/backends/fail.py
Fallback backend used when no platform backend is available.
Every operation raises NoKeyringError with a clear, actionable message.
"""

from typing import Optional

from .base import BaseKeyring
from ..errors import NoKeyringError

_MSG = (
    "No supported keychain backend found for this platform. "
    "Please store your API key in an environment variable or set it manually:\n"
    "  Tools > st-fast-autocomplete > Set API Key"
)


class FailKeyring(BaseKeyring):

    def is_available(self) -> bool:
        return True  # always selected as last-resort fallback

    def get_password(self, service: str, username: str) -> Optional[str]:
        raise NoKeyringError(_MSG)

    def set_password(self, service: str, username: str, password: str) -> None:
        raise NoKeyringError(_MSG)

    def delete_password(self, service: str, username: str) -> None:
        raise NoKeyringError(_MSG)
