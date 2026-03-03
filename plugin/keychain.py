"""
plugin/keychain.py
OS keychain integration for st-fast-autocomplete.
Wraps the vendored keyring library with a clean interface and graceful
fallback to environment variables when no keychain backend is available.
"""

from __future__ import annotations

import os
from typing import Optional

import sublime

# Ensure vendor is on sys.path before importing keyring
import st_fast_autocomplete.vendor  # noqa: F401 — ensures vendor path bootstrap
from keyring import get_password, set_password, delete_password
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

# ---------------------------------------------------------------------------
# Service namespace — one entry per provider in the OS keychain
# ---------------------------------------------------------------------------
_SERVICE_PREFIX = "st-fast-autocomplete"

# Environment variable fallback names per provider
_ENV_VARS: dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class KeychainManager:
    """
    Static manager for API key storage and retrieval.

    Priority order for get_key():
      1. OS keychain (set via set_key() or Tools menu)
      2. Environment variable (ANTHROPIC_API_KEY / OPENAI_API_KEY)
      3. None — caller should prompt the user
    """

    _initialized: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def initialize(cls) -> None:
        """
        Called once from plugin_loaded().
        Validates that a keychain backend is reachable and logs the result.
        """
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
        debug = FastAutocompleteSettings.debug()

        try:
            from keyring import get_keyring
            backend = get_keyring()
            if debug:
                print(f"[fast_autocomplete] Keychain backend: {type(backend).__name__}")
        except Exception as exc:
            print(f"[fast_autocomplete] WARNING: Keychain initialisation failed: {exc}")

        cls._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def get_key(cls, provider: str) -> Optional[str]:
        """
        Return the API key for the given provider, or None if not set.

        Tries the OS keychain first, then falls back to the environment.
        """
        # 1. OS keychain
        try:
            key = get_password(_service(provider), provider)
            if key:
                return key
        except NoKeyringError:
            pass  # no backend — fall through to env var
        except KeyringError as exc:
            _warn(f"Keychain read error for {provider!r}: {exc}")

        # 2. Environment variable fallback
        env_var = _ENV_VARS.get(provider)
        if env_var:
            key = os.environ.get(env_var)
            if key:
                return key

        return None

    @classmethod
    def set_key(cls, provider: str, api_key: str) -> bool:
        """
        Store an API key in the OS keychain.
        Returns True on success, False on failure (error is shown to user).
        """
        try:
            set_password(_service(provider), provider, api_key)
            return True
        except NoKeyringError:
            sublime.error_message(
                "[fast_autocomplete] No keychain backend available on this platform.\n\n"
                f"Set the {_ENV_VARS.get(provider, 'API key')} environment variable instead."
            )
            return False
        except KeyringError as exc:
            sublime.error_message(
                f"[fast_autocomplete] Failed to save API key for {provider!r}:\n{exc}"
            )
            return False

    @classmethod
    def delete_key(cls, provider: str) -> bool:
        """
        Remove a stored API key from the OS keychain.
        Returns True on success, False if the key was not found or on error.
        """
        try:
            delete_password(_service(provider), provider)
            return True
        except PasswordDeleteError:
            return False  # key simply wasn't stored — not an error worth surfacing
        except KeyringError as exc:
            _warn(f"Keychain delete error for {provider!r}: {exc}")
            return False

    @classmethod
    def has_key(cls, provider: str) -> bool:
        """Return True if a key is available (keychain or environment)."""
        return cls.get_key(provider) is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service(provider: str) -> str:
    """Return the keychain service identifier for a provider."""
    return f"{_SERVICE_PREFIX}/{provider}"


def _warn(message: str) -> None:
    print(f"[fast_autocomplete] WARNING: {message}")