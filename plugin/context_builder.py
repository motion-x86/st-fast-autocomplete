"""
plugin/context_builder.py
Assembles the completion context payload from the active view.

Produces a ContextPayload dataclass containing:
  - prefix  : text before the cursor (bounded by context_lines_before)
  - suffix  : text after the cursor  (bounded by context_lines_after)
  - syntax  : ST scope string at cursor (e.g. "source.python")
  - language: human-readable language name derived from the scope
  - cursor_row / cursor_col: 0-indexed position for debugging
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import sublime



# ---------------------------------------------------------------------------
# Scope → language name mapping (most common grammars)
# ---------------------------------------------------------------------------
_SCOPE_TO_LANGUAGE: dict[str, str] = {
    "source.python":         "Python",
    "source.js":             "JavaScript",
    "source.ts":             "TypeScript",
    "source.tsx":            "TypeScript JSX",
    "source.jsx":            "JavaScript JSX",
    "source.ruby":           "Ruby",
    "source.rust":           "Rust",
    "source.go":             "Go",
    "source.c":              "C",
    "source.c++":            "C++",
    "source.objc":           "Objective-C",
    "source.java":           "Java",
    "source.kotlin":         "Kotlin",
    "source.swift":          "Swift",
    "source.cs":             "C#",
    "source.php":            "PHP",
    "source.shell":          "Shell",
    "source.lua":            "Lua",
    "source.r":              "R",
    "source.scala":          "Scala",
    "source.elixir":         "Elixir",
    "source.haskell":        "Haskell",
    "source.clojure":        "Clojure",
    "source.dart":           "Dart",
    "source.yaml":           "YAML",
    "source.json":           "JSON",
    "source.toml":           "TOML",
    "source.sql":            "SQL",
    "source.css":            "CSS",
    "source.scss":           "SCSS",
    "source.sass":           "Sass",
    "source.less":           "Less",
    "text.html":             "HTML",
    "text.html.markdown":    "Markdown",
    "text.xml":              "XML",
    "text.plain":            "Plain Text",
}


@dataclass
class ContextPayload:
    """All data passed to a provider for a single completion request."""
    prefix:     str
    suffix:     str
    syntax:     str                    # raw ST scope string
    language:   str                    # human-readable name
    cursor_row: int                    # 0-indexed
    cursor_col: int                    # 0-indexed
    file_name:  Optional[str] = None   # basename only, no full path


class ContextBuilder:
    """
    Builds a ContextPayload from the current view state.

    All methods are static — no instantiation needed.
    """

    @staticmethod
    def build(view: sublime.View, cursor_point: int) -> ContextPayload:
        """
        Extract prefix, suffix, syntax scope, and cursor position from view.

        Args:
            view:         The active sublime.View.
            cursor_point: The character offset (sel[0].b) of the cursor.

        Returns:
            A fully populated ContextPayload.
        """
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
        lines_before = FastAutocompleteSettings.context_lines_before()
        lines_after  = FastAutocompleteSettings.context_lines_after()

        prefix = ContextBuilder._extract_prefix(view, cursor_point, lines_before)
        suffix = ContextBuilder._extract_suffix(view, cursor_point, lines_after)

        syntax   = ContextBuilder._get_syntax_scope(view, cursor_point)
        language = ContextBuilder._scope_to_language(syntax)

        row, col = view.rowcol(cursor_point)

        file_name: Optional[str] = None
        full_path = view.file_name()
        if full_path:
            import os
            file_name = os.path.basename(full_path)

        payload = ContextPayload(
            prefix=prefix,
            suffix=suffix,
            syntax=syntax,
            language=language,
            cursor_row=row,
            cursor_col=col,
            file_name=file_name,
        )

        # Apply privacy filters (redact comments, strings, custom patterns)
        from st_fast_autocomplete.plugin.privacy import apply as privacy_apply
        return privacy_apply(payload)

    # ------------------------------------------------------------------
    # Prefix extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_prefix(
        view: sublime.View,
        cursor_point: int,
        max_lines: int,
    ) -> str:
        """
        Return up to max_lines lines of text ending at cursor_point.
        Preserves the partial current line up to the cursor column.
        """
        if max_lines <= 0:
            return ""

        # Find the start point: walk back max_lines newlines
        row, _ = view.rowcol(cursor_point)
        start_row = max(0, row - max_lines)
        start_point = view.text_point(start_row, 0)

        region = sublime.Region(start_point, cursor_point)
        return view.substr(region)

    # ------------------------------------------------------------------
    # Suffix extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_suffix(
        view: sublime.View,
        cursor_point: int,
        max_lines: int,
    ) -> str:
        """
        Return up to max_lines lines of text starting from cursor_point.
        Starts from the character immediately after the cursor.
        """
        if max_lines <= 0:
            return ""

        row, _ = view.rowcol(cursor_point)
        total_lines = view.rowcol(view.size())[0]
        end_row = min(total_lines, row + max_lines)

        # text_point for the end of end_row
        end_point = view.text_point(end_row, 0)
        # include to end of that line
        end_line_region = view.line(end_point)
        end_point = end_line_region.b

        region = sublime.Region(cursor_point, end_point)
        return view.substr(region)

    # ------------------------------------------------------------------
    # Syntax / scope
    # ------------------------------------------------------------------

    @staticmethod
    def _get_syntax_scope(view: sublime.View, cursor_point: int) -> str:
        """
        Return the top-level scope name at the cursor position.
        E.g. "source.python", "text.html.markdown"
        """
        full_scope = view.scope_name(cursor_point).strip()
        # The first token is the top-level grammar scope
        top_scope = full_scope.split()[0] if full_scope else "text.plain"

        # Normalise to the root scope (e.g. "source.python.embedded.sql" → "source.python")
        parts = top_scope.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return top_scope

    @staticmethod
    def _scope_to_language(scope: str) -> str:
        """
        Convert a ST scope string to a human-readable language name.
        Falls back to a title-cased version of the scope suffix.
        """
        if scope in _SCOPE_TO_LANGUAGE:
            return _SCOPE_TO_LANGUAGE[scope]

        # Best-effort: capitalise the sub-scope (e.g. "source.zig" → "Zig")
        parts = scope.split(".")
        if len(parts) >= 2:
            return parts[-1].capitalize()
        return scope