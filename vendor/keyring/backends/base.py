"""
vendor/keyring/backends/base.py
Abstract base class for keyring backends.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseKeyring(ABC):

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend is usable on the current system."""

    @abstractmethod
    def get_password(self, service: str, username: str) -> Optional[str]:
        """Return the stored password or None."""

    @abstractmethod
    def set_password(self, service: str, username: str, password: str) -> None:
        """Persist a credential."""

    @abstractmethod
    def delete_password(self, service: str, username: str) -> None:
        """Remove a credential. Raises PasswordDeleteError if not found."""
