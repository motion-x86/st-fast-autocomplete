"""
plugin/privacy.py
Context redaction engine for st-fast-autocomplete.

Applies user-configured privacy filters to the prefix and suffix strings
before they are sent to any AI provider. All filtering is done in-process —
nothing is logged or stored.

Available filters (each independently toggled in settings):
  redact_comments         — remove single-line and block comments
  redact_string_literals  — replace string contents with a placeholder
  redact_patterns         — apply user-defined regex redaction rules

All filters are applied in the order listed above.
Comment and string literal stripping is scope-aware per language where
possible; a universal regex fallback handles unknown languages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

from st_fast_autocomplete.plugin.context_builder import ContextPayload


# ---------------------------------------------------------------------------
# Placeholder tokens inserted in place of redacted content
# ---------------------------------------------------------------------------
_STRING_PLACEHOLDER = '""'       # replaces string contents, keeps delimiters
_COMMENT_PLACEHOLDER = ""        # comments removed entirely (blank line kept)


# ---------------------------------------------------------------------------
# Language-specific comment patterns
# ---------------------------------------------------------------------------

# (single_line_prefix, block_start, block_end) — None means not supported
_COMMENT_STYLES: dict[str, tuple[Optional[str], Optional[str], Optional[str]]] = {
    "Python":      ("#",    None,  None),
    "Ruby":        ("#",    None,  None),
    "Shell":       ("#",    None,  None),
    "R":           ("#",    None,  None),
    "JavaScript":  ("//",   "/*",  "*/"),
    "TypeScript":  ("//",   "/*",  "*/"),
    "TypeScript JSX": ("//","/*",  "*/"),
    "JavaScript JSX": ("//","/*",  "*/"),
    "Rust":        ("//",   "/*",  "*/"),
    "Go":          ("//",   "/*",  "*/"),
    "C":           ("//",   "/*",  "*/"),
    "C++":         ("//",   "/*",  "*/"),
    "Java":        ("//",   "/*",  "*/"),
    "Kotlin":      ("//",   "/*",  "*/"),
    "Swift":       ("//",   "/*",  "*/"),
    "C#":          ("//",   "/*",  "*/"),
    "Scala":       ("//",   "/*",  "*/"),
    "Dart":        ("//",   "/*",  "*/"),
    "PHP":         ("//",   "/*",  "*/"),
    "CSS":         (None,   "/*",  "*/"),
    "SCSS":        ("//",   "/*",  "*/"),
    "Less":        ("//",   "/*",  "*/"),
    "SQL":         ("--",   "/*",  "*/"),
    "Lua":         ("--",   "--[[","]]"),
    "HTML":        (None,   "<!--","-->"),
    "XML":         (None,   "<!--","-->"),
    "YAML":        ("#",    None,  None),
    "TOML":        ("#",    None,  None),
}

# ---------------------------------------------------------------------------
# Language-specific string literal patterns
# ---------------------------------------------------------------------------
# Ordered list of regex patterns that match complete string tokens.
# Capture group 1 is the opening delimiter (used to reconstruct placeholder).

_PY_STRING_RE = re.compile(
    r'(f?b?r?"""|\'{3}|f?b?r?\'\'\')'  # triple-quoted
    r'.*?'
    r'(?:\1)'                           # matching close
    r'|(f?b?r?")'                       # double-quoted
    r'(?:[^"\\]|\\.)*'
    r'"'
    r'|(f?b?r?\')'                      # single-quoted
    r'(?:[^\'\\]|\\.)*'
    r'\'',
    re.DOTALL,
)

_C_STRING_RE = re.compile(
    r'(")'
    r'(?:[^"\\]|\\.)*'
    r'"'
    r"|(')"
    r"(?:[^'\\]|\\.)*"
    r"'",
    re.DOTALL,
)

_GENERIC_STRING_RE = _C_STRING_RE   # fallback

_STRING_PATTERNS: dict[str, re.Pattern] = {
    "Python": _PY_STRING_RE,
    "Ruby":   _PY_STRING_RE,
}

_C_STYLE_LANGUAGES = {
    "JavaScript", "TypeScript", "TypeScript JSX", "JavaScript JSX",
    "Rust", "Go", "C", "C++", "Java", "Kotlin", "Swift", "C#",
    "Scala", "Dart", "PHP",
}
for _lang in _C_STYLE_LANGUAGES:
    _STRING_PATTERNS[_lang] = _C_STRING_RE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply(payload: ContextPayload) -> ContextPayload:
    """
    Apply all enabled privacy filters to the payload's prefix and suffix.
    Returns a new ContextPayload — the original is never mutated.
    Reads settings at call time so live changes take effect immediately.
    """
    from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings

    prefix = payload.prefix
    suffix = payload.suffix
    lang   = payload.language

    # 1. Strip comments
    if FastAutocompleteSettings.get_value("privacy_redact_comments", False):
        prefix = _strip_comments(prefix, lang)
        suffix = _strip_comments(suffix, lang)

    # 2. Strip string literal contents
    if FastAutocompleteSettings.get_value("privacy_redact_string_literals", False):
        prefix = _strip_strings(prefix, lang)
        suffix = _strip_strings(suffix, lang)

    # 3. User-defined regex patterns
    patterns = FastAutocompleteSettings.get_value("privacy_redact_patterns", [])
    if patterns:
        prefix = _apply_patterns(prefix, patterns)
        suffix = _apply_patterns(suffix, patterns)

    # Return a new payload with redacted text; all other fields unchanged
    return replace(payload, prefix=prefix, suffix=suffix)


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------

def _strip_comments(text: str, language: str) -> str:
    """Remove comments from text using language-appropriate patterns."""
    style = _COMMENT_STYLES.get(language)

    if style is None:
        # Unknown language — attempt generic // and # stripping
        text = re.sub(r"#[^\n]*", "", text)
        text = re.sub(r"//[^\n]*", "", text)
        return text

    single, block_start, block_end = style

    # Strip block comments first (greedy over newlines)
    if block_start and block_end:
        bs = re.escape(block_start)
        be = re.escape(block_end)
        text = re.sub(rf"{bs}.*?{be}", "", text, flags=re.DOTALL)

    # Strip single-line comments
    if single:
        sl = re.escape(single)
        text = re.sub(rf"{sl}[^\n]*", "", text)

    return text


# ---------------------------------------------------------------------------
# String literal stripping
# ---------------------------------------------------------------------------

def _strip_strings(text: str, language: str) -> str:
    """Replace string literal contents with a placeholder token."""
    pattern = _STRING_PATTERNS.get(language, _GENERIC_STRING_RE)

    def _replace(m: re.Match) -> str:
        # Reconstruct with empty content between original delimiters
        full = m.group(0)
        for delim in ('"""', "'''", '"', "'"):
            if full.startswith(delim) or (len(full) > 1 and full[1:].startswith(delim)):
                return _STRING_PLACEHOLDER
        return _STRING_PLACEHOLDER

    return pattern.sub(_replace, text)


# ---------------------------------------------------------------------------
# User-defined pattern redaction
# ---------------------------------------------------------------------------

def _apply_patterns(text: str, patterns: list) -> str:
    """
    Apply each pattern in the user's privacy_redact_patterns list.

    Each entry may be:
      - a plain string (treated as a literal match, case-sensitive)
      - a dict with keys "pattern" (required) and optionally "replacement"
        (defaults to "[REDACTED]") and "flags" (list of flag names).

    Supported flag names: "IGNORECASE", "MULTILINE", "DOTALL"
    """
    _flag_map = {
        "IGNORECASE": re.IGNORECASE,
        "MULTILINE":  re.MULTILINE,
        "DOTALL":     re.DOTALL,
    }

    for entry in patterns:
        if isinstance(entry, str):
            text = text.replace(entry, "[REDACTED]")

        elif isinstance(entry, dict):
            raw_pattern = entry.get("pattern")
            if not raw_pattern:
                continue
            replacement = entry.get("replacement", "[REDACTED]")
            flag_names  = entry.get("flags", [])
            flags       = 0
            for name in flag_names:
                flags |= _flag_map.get(name.upper(), 0)
            try:
                text = re.sub(raw_pattern, replacement, text, flags=flags)
            except re.error as exc:
                # Malformed user pattern — skip silently, log to console
                print(
                    f"[fast_autocomplete] WARNING: invalid privacy pattern "
                    f"{raw_pattern!r}: {exc}"
                )

    return text