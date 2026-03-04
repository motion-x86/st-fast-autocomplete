"""
vendor/keyring/backends/fail.py
Fallback backend used when no platform backend is available.
Every operation raises NoKeyringError with a clear, actionable message.
"""

import sys
from typing import Optional

from .base import BaseKeyring
from ..errors import NoKeyringError


def _build_message() -> str:
    if sys.platform.startswith("linux"):
        return (
            "No keychain backend found. On Linux, st-fast-autocomplete uses "
            "the 'secret-tool' CLI (part of libsecret-tools).\n\n"
            "Install it with:\n"
            "  Ubuntu/Debian: sudo apt install libsecret-tools\n"
            "  Fedora/RHEL:   sudo dnf install libsecret\n"
            "  Arch:          sudo pacman -S libsecret\n\n"
            "Then restart Sublime Text and set your API key again via:\n"
            "  Tools > st-fast-autocomplete > Set API Key"
        )
    if sys.platform == "darwin":
        return (
            "No keychain backend found. The 'security' CLI should be available "
            "on macOS by default. If it is missing, please reinstall Xcode Command Line Tools:\n"
            "  xcode-select --install"
        )
    return (
        "No supported keychain backend found for this platform. "
        "Set your API key as an environment variable instead:\n"
        "  ANTHROPIC_API_KEY=... or OPENAI_API_KEY=..."
    )


class FailKeyring(BaseKeyring):

    def is_available(self) -> bool:
        return True  # always selected as last-resort fallback

    def get_password(self, service: str, username: str) -> Optional[str]:
        raise NoKeyringError(_build_message())

    def set_password(self, service: str, username: str, password: str) -> None:
        raise NoKeyringError(_build_message())

    def delete_password(self, service: str, username: str) -> None:
        raise NoKeyringError(_build_message())