"""
plugin/settings.py
Settings loader, validation, and runtime accessors for st-fast-autocomplete.
Wraps sublime.load_settings / sublime.save_settings with typed defaults
and range guards so the rest of the plugin never touches the ST settings
API directly.
"""

from __future__ import annotations

import sublime
from typing import Any, Optional

SETTINGS_FILE = "fast_autocomplete.sublime-settings"

from st_fast_autocomplete.plugin.constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_COMPLETION_INSTRUCTION,
    DEFAULT_ALTERNATE_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# Defaults — mirrors fast_autocomplete.sublime-settings
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    # Provider & model
    "provider":                  "claude",
    "model":                     "claude-sonnet-4-20250514",
    # Completion length
    "max_completion_tokens":     128,
    # Context window
    "context_lines_before":      50,
    "context_lines_after":       10,
    # Streaming
    "streaming":                 False,
    # Prompts
    "system_prompt":             DEFAULT_SYSTEM_PROMPT,
    "completion_instruction":    DEFAULT_COMPLETION_INSTRUCTION,
    "alternate_instruction":     DEFAULT_ALTERNATE_INSTRUCTION,
    # Ghost text
    "ghost_text_scope":          "comment",
    # Request behaviour
    "request_timeout_seconds":   10,
    "max_retries":               2,
    # LSP
    "lsp_coexistence":           True,
    # Privacy
    "privacy_redact_comments":        False,
    "privacy_redact_string_literals": False,
    "privacy_no_retention":           False,
    "privacy_redact_patterns":        [],
    # Debug
    "debug":                          False,
}

# Prompt keys — used by reset_prompts()
PROMPT_KEYS = ("system_prompt", "completion_instruction", "alternate_instruction")

# Hard limits
_MAX_COMPLETION_TOKENS_CEILING = 4096
_MIN_COMPLETION_TOKENS         = 1
_MAX_CONTEXT_LINES             = 500
_MAX_TIMEOUT                   = 60
_MAX_RETRIES                   = 10

_VALID_PROVIDERS = {"claude", "openai"}


class FastAutocompleteSettings:
    """
    Thin wrapper around sublime.Settings.

    Usage:
        FastAutocompleteSettings.load()               # call once in plugin_loaded()
        s = FastAutocompleteSettings.get()            # returns sublime.Settings proxy
        FastAutocompleteSettings.set(key, value)      # persists to User settings
        FastAutocompleteSettings.reset_prompts()      # restore all prompt fields to defaults
    """

    _settings: Optional[sublime.Settings] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def load(cls) -> None:
        """Load settings and register a change callback for live reload."""
        cls._settings = sublime.load_settings(SETTINGS_FILE)
        cls._settings.add_on_change(
            "fast_autocomplete_reload",
            cls._on_settings_changed,
        )
        cls._validate()

    @classmethod
    def unload(cls) -> None:
        if cls._settings:
            cls._settings.clear_on_change("fast_autocomplete_reload")
            cls._settings = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> sublime.Settings:
        """Return the raw sublime.Settings object (supports .get() with fallback)."""
        if cls._settings is None:
            cls.load()
        return cls._settings  # type: ignore[return-value]

    @classmethod
    def get_value(cls, key: str, fallback: Any = None) -> Any:
        """Return a single validated setting value."""
        if cls._settings is None:
            cls.load()
        value = cls._settings.get(key, DEFAULTS.get(key, fallback))  # type: ignore[union-attr]
        return cls._coerce(key, value)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """Persist a value to the User settings file."""
        if cls._settings is None:
            cls.load()
        cls._settings.set(key, value)  # type: ignore[union-attr]
        sublime.save_settings(SETTINGS_FILE)

    @classmethod
    def reset_prompts(cls) -> None:
        """
        Restore all three prompt fields to their built-in defaults and
        persist the change. Called by FastAutocompleteResetPromptsCommand.
        """
        if cls._settings is None:
            cls.load()
        for key in PROMPT_KEYS:
            cls._settings.erase(key)  # type: ignore[union-attr]
        sublime.save_settings(SETTINGS_FILE)
        if cls.debug():
            print("[fast_autocomplete] Prompt settings reset to defaults.")

    # ------------------------------------------------------------------
    # Convenience typed accessors
    # ------------------------------------------------------------------

    @classmethod
    def provider(cls) -> str:
        return cls.get_value("provider")

    @classmethod
    def model(cls) -> str:
        return cls.get_value("model")

    @classmethod
    def max_completion_tokens(cls) -> int:
        return cls.get_value("max_completion_tokens")

    @classmethod
    def context_lines_before(cls) -> int:
        return cls.get_value("context_lines_before")

    @classmethod
    def context_lines_after(cls) -> int:
        return cls.get_value("context_lines_after")

    @classmethod
    def streaming(cls) -> bool:
        return cls.get_value("streaming")

    @classmethod
    def system_prompt(cls) -> str:
        return cls.get_value("system_prompt")

    @classmethod
    def completion_instruction(cls) -> str:
        return cls.get_value("completion_instruction")

    @classmethod
    def alternate_instruction(cls) -> str:
        return cls.get_value("alternate_instruction")

    @classmethod
    def privacy_redact_comments(cls) -> bool:
        return cls.get_value("privacy_redact_comments")

    @classmethod
    def privacy_redact_string_literals(cls) -> bool:
        return cls.get_value("privacy_redact_string_literals")

    @classmethod
    def privacy_no_retention(cls) -> bool:
        return cls.get_value("privacy_no_retention")

    @classmethod
    def privacy_redact_patterns(cls) -> list:
        return cls.get_value("privacy_redact_patterns")

    @classmethod
    def ghost_text_scope(cls) -> str:
        return cls.get_value("ghost_text_scope")

    @classmethod
    def request_timeout_seconds(cls) -> int:
        return cls.get_value("request_timeout_seconds")

    @classmethod
    def max_retries(cls) -> int:
        return cls.get_value("max_retries")

    @classmethod
    def lsp_coexistence(cls) -> bool:
        return cls.get_value("lsp_coexistence")

    @classmethod
    def debug(cls) -> bool:
        return cls.get_value("debug")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _on_settings_changed(cls) -> None:
        cls._validate()
        if cls.debug():
            print("[fast_autocomplete] Settings reloaded.")

    @classmethod
    def _validate(cls) -> None:
        """
        Warn in the ST console if any setting is out of range or invalid.
        Does not raise — the plugin stays functional with coerced values.
        """
        if cls._settings is None:
            return

        provider = cls._settings.get("provider", DEFAULTS["provider"])
        if provider not in _VALID_PROVIDERS:
            print(
                f"[fast_autocomplete] WARNING: unknown provider {provider!r}. "
                f"Valid values: {sorted(_VALID_PROVIDERS)}. Falling back to 'claude'."
            )

        max_tokens = cls._settings.get("max_completion_tokens", DEFAULTS["max_completion_tokens"])
        if not isinstance(max_tokens, int) or max_tokens < _MIN_COMPLETION_TOKENS:
            print(
                f"[fast_autocomplete] WARNING: max_completion_tokens={max_tokens!r} is invalid. "
                f"Must be an integer >= {_MIN_COMPLETION_TOKENS}. "
                f"Using default {DEFAULTS['max_completion_tokens']}."
            )
        elif max_tokens > _MAX_COMPLETION_TOKENS_CEILING:
            print(
                f"[fast_autocomplete] WARNING: max_completion_tokens={max_tokens} exceeds hard "
                f"ceiling of {_MAX_COMPLETION_TOKENS_CEILING}. Value will be clamped."
            )

        timeout = cls._settings.get("request_timeout_seconds", DEFAULTS["request_timeout_seconds"])
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            print(
                f"[fast_autocomplete] WARNING: request_timeout_seconds={timeout!r} is invalid. "
                f"Using default {DEFAULTS['request_timeout_seconds']}."
            )

        # Warn if any prompt field is set to an empty string
        for key in PROMPT_KEYS:
            val = cls._settings.get(key)
            if val is not None and not str(val).strip():
                print(
                    f"[fast_autocomplete] WARNING: {key!r} is empty. "
                    "The built-in default will be used. "
                    "Run 'FastAutocomplete: Reset Prompts to Default' to restore."
                )

    @classmethod
    def _coerce(cls, key: str, value: Any) -> Any:
        """Apply range guards and type coercion for known keys."""
        if key == "provider":
            return value if value in _VALID_PROVIDERS else DEFAULTS["provider"]

        if key == "max_completion_tokens":
            try:
                v = int(value)
            except (TypeError, ValueError):
                return DEFAULTS["max_completion_tokens"]
            return max(_MIN_COMPLETION_TOKENS, min(v, _MAX_COMPLETION_TOKENS_CEILING))

        if key in ("context_lines_before", "context_lines_after"):
            try:
                v = int(value)
            except (TypeError, ValueError):
                return DEFAULTS[key]
            return max(0, min(v, _MAX_CONTEXT_LINES))

        if key == "request_timeout_seconds":
            try:
                v = float(value)
            except (TypeError, ValueError):
                return DEFAULTS["request_timeout_seconds"]
            return max(1.0, min(v, _MAX_TIMEOUT))

        if key == "max_retries":
            try:
                v = int(value)
            except (TypeError, ValueError):
                return DEFAULTS["max_retries"]
            return max(0, min(v, _MAX_RETRIES))

        if key in ("streaming", "lsp_coexistence", "debug",
                   "privacy_redact_comments", "privacy_redact_string_literals",
                   "privacy_no_retention"):
            return bool(value)

        if key == "privacy_redact_patterns":
            return value if isinstance(value, list) else []

        # Prompt fields — return as-is (empty string falls back in _resolve_instruction)
        if key in PROMPT_KEYS:
            return str(value) if value is not None else DEFAULTS[key]

        return value
        