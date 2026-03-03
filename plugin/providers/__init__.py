"""
plugin/providers/__init__.py
Provider registry and factory function.
"""

from __future__ import annotations

import sublime

from st_fast_autocomplete.plugin.providers.base import BaseProvider
from st_fast_autocomplete.plugin.providers.claude import ClaudeProvider
from st_fast_autocomplete.plugin.providers.openai import OpenAIProvider
from st_fast_autocomplete.plugin.keychain import KeychainManager


_REGISTRY: dict[str, type[BaseProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
}


def get_provider(settings: sublime.Settings) -> BaseProvider:
    """
    Resolve and return an initialised provider from the active settings.

    Raises:
        ValueError: if the provider name is unknown or the API key is missing.
    """
    name = settings.get("provider", "claude").lower()

    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown provider {name!r}. Valid options: {sorted(_REGISTRY.keys())}"
        )

    api_key = KeychainManager.get_key(name)
    if not api_key:
        raise ValueError(
            f"No API key found for provider {name!r}.\n"
            f"Set one via: Tools > st-fast-autocomplete > Set API Key"
        )

    model = settings.get("model", None)
    return _REGISTRY[name](api_key=api_key, model=model)


__all__ = ["get_provider", "BaseProvider", "ClaudeProvider", "OpenAIProvider"]