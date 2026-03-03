"""
plugin/providers/base.py
Abstract base class all AI providers must implement.

Prompt assembly is driven by three user-configurable settings:

  system_prompt
      Sent as the API "system" role message. Sets the assistant's persona
      and output constraints. No placeholders — this is static context.

  completion_instruction
      Appended after the prefix/suffix block. Tells the model what to do.
      Supports placeholders: {language}, {file_name}

  alternate_instruction
      Appended instead of (not in addition to) completion_instruction when
      alternate=True. Same placeholder support.

Defaults live in settings.py (DEFAULTS) and are mirrored in
fast_autocomplete.sublime-settings for discoverability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generator, Optional, Union

from st_fast_autocomplete.plugin.context_builder import ContextPayload


# Type alias for provider return — either a full string or a token stream
CompletionResult = Union[str, Generator[str, None, None]]

# ---------------------------------------------------------------------------
# Prompt defaults — imported from constants to avoid circular imports
# ---------------------------------------------------------------------------

from st_fast_autocomplete.plugin.constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_COMPLETION_INSTRUCTION,
    DEFAULT_ALTERNATE_INSTRUCTION,
)


class BaseProvider(ABC):
    """
    Interface contract for completion providers.

    Subclasses must implement:
      - complete()        : blocking full-response completion
      - complete_stream() : streaming token-by-token completion

    Shared helpers (build_prompt, build_system_prompt) read from
    FastAutocompleteSettings at call time so live setting changes
    are reflected without a plugin reload.
    """

    #: Default model identifier — subclasses must set this
    DEFAULT_MODEL: str = ""

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model   = model or self.DEFAULT_MODEL

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def complete(
        self,
        context: ContextPayload,
        max_tokens: int,
        alternate: bool = False,
    ) -> str:
        """
        Return a completion string for the given context.

        Args:
            context:    Assembled prefix/suffix/syntax payload.
            max_tokens: Hard cap on response length.
            alternate:  If True, use alternate_instruction + higher temperature.

        Returns:
            The completion text to insert at the cursor position.

        Raises:
            ProviderError: on API / network failure.
        """

    @abstractmethod
    def complete_stream(
        self,
        context: ContextPayload,
        max_tokens: int,
        alternate: bool = False,
    ) -> Generator[str, None, None]:
        """
        Yield completion tokens as they arrive from the API.

        Args:
            context:    Assembled prefix/suffix/syntax payload.
            max_tokens: Hard cap on response length.
            alternate:  If True, use alternate_instruction + higher temperature.

        Yields:
            Individual text tokens (strings) as they stream in.

        Raises:
            ProviderError: on API / network failure.
        """

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def build_system_prompt(self) -> str:
        """
        Return the system prompt string from settings, falling back to the
        built-in default. No placeholder substitution — system prompt is static.
        """
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
        return FastAutocompleteSettings.get_value(
            "system_prompt", DEFAULT_SYSTEM_PROMPT
        ) or DEFAULT_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # User-turn prompt (FIM block + instruction)
    # ------------------------------------------------------------------

    def build_prompt(self, context: ContextPayload, alternate: bool = False) -> str:
        """
        Build a Fill-in-Middle (FIM) style user-turn prompt.

        Structure:
          [prefix block]
          [suffix block — omitted if empty]
          [instruction line with placeholders resolved]
        """
        parts: list[str] = []

        # Prefix block
        parts.append("<prefix>\n")
        parts.append(context.prefix)
        parts.append("\n</prefix>\n")

        # Suffix block (fill-in-middle)
        if context.suffix:
            parts.append("\n<suffix>\n")
            parts.append(context.suffix)
            parts.append("\n</suffix>\n")

        # Instruction line
        parts.append("\n")
        parts.append(self._resolve_instruction(context, alternate))

        return "".join(parts)

    # ------------------------------------------------------------------
    # Temperature
    # ------------------------------------------------------------------

    @staticmethod
    def temperature(alternate: bool) -> float:
        """Return a temperature value appropriate for normal vs alternate completions."""
        return 0.8 if alternate else 0.2

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_instruction(self, context: ContextPayload, alternate: bool) -> str:
        """
        Fetch the appropriate instruction template from settings and resolve
        all supported placeholders.

        Placeholders:
          {language}        — human-readable language name (e.g. "Python")
          {file_name}       — basename of the open file, or empty string
          {file_name_clause}— natural-language clause e.g. " in file main.py",
                              or empty string when file_name is unknown.
                              Use this in sentence-embedded positions.
        """
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings

        if alternate:
            template = FastAutocompleteSettings.get_value(
                "alternate_instruction", DEFAULT_ALTERNATE_INSTRUCTION
            ) or DEFAULT_ALTERNATE_INSTRUCTION
        else:
            template = FastAutocompleteSettings.get_value(
                "completion_instruction", DEFAULT_COMPLETION_INSTRUCTION
            ) or DEFAULT_COMPLETION_INSTRUCTION

        file_name        = context.file_name or ""
        file_name_clause = f" in file {file_name}" if file_name else ""

        try:
            return template.format(
                language=context.language,
                file_name=file_name,
                file_name_clause=file_name_clause,
            )
        except KeyError as exc:
            # Unknown placeholder in user template — warn and fall back
            print(
                f"[fast_autocomplete] WARNING: unknown placeholder {exc} in prompt template. "
                "Falling back to default instruction."
            )
            fallback = DEFAULT_ALTERNATE_INSTRUCTION if alternate else DEFAULT_COMPLETION_INSTRUCTION
            return fallback.format(
                language=context.language,
                file_name=file_name,
                file_name_clause=file_name_clause,
            )


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Raised by providers on API or network failure."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(ProviderError):
    """Raised on 401 / invalid API key."""


class RateLimitError(ProviderError):
    """Raised on 429 / quota exceeded."""


class ProviderTimeoutError(ProviderError):
    """Raised when the request exceeds the configured timeout."""
    