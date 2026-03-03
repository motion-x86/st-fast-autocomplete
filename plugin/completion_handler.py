"""
plugin/completion_handler.py
Ghost text rendering, accept/dismiss, and streaming update logic.

Ghost text is rendered using ST4's minihtml phantom API:
  view.add_phantom() inserts a read-only styled overlay after the cursor.

State is tracked per view.id() so multiple open files are fully isolated.
All UI mutations (add/erase phantoms, insert text) are marshalled back to
the UI thread via sublime.set_timeout().
"""

from __future__ import annotations

import threading
from typing import Optional

import sublime

from st_fast_autocomplete.plugin import debounce
from st_fast_autocomplete.plugin.context_builder import ContextPayload
from st_fast_autocomplete.plugin.providers.base import BaseProvider, ProviderError, AuthError, RateLimitError, ProviderTimeoutError
from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings

# ---------------------------------------------------------------------------
# Per-view state
# ---------------------------------------------------------------------------

class _ViewState:
    """Holds the current ghost text state for a single view."""

    def __init__(self) -> None:
        self.completion_text: str          = ""
        self.cursor_point:    int          = -1
        self.phantom_set:     Optional[sublime.PhantomSet] = None
        self.lock:            threading.Lock = threading.Lock()

    def clear(self) -> None:
        with self.lock:
            self.completion_text = ""
            self.cursor_point    = -1


# view.id() → _ViewState
_states: dict[int, _ViewState] = {}
_states_lock = threading.Lock()

# ST phantom key — used to identify/erase our phantoms
_PHANTOM_KEY = "fast_autocomplete_ghost"


def _get_state(view: sublime.View) -> _ViewState:
    view_id = view.id()
    with _states_lock:
        if view_id not in _states:
            _states[view_id] = _ViewState()
        return _states[view_id]


# ---------------------------------------------------------------------------
# Public API (called from fast_autocomplete.py commands + event listener)
# ---------------------------------------------------------------------------

class CompletionHandler:

    @staticmethod
    def request(
        view: sublime.View,
        cursor_point: int,
        context: ContextPayload,
        provider: BaseProvider,
        streaming: bool,
        max_tokens: int,
        alternate: bool = False,
    ) -> None:
        """
        Dispatch an async completion request for view.
        Any previously in-flight request for this view is cancelled first.
        """
        state = _get_state(view)
        with state.lock:
            state.cursor_point = cursor_point

        sublime.status_message("[fast_autocomplete] Requesting completion…")

        if streaming:
            task = _make_stream_task(view, context, provider, max_tokens, alternate)
        else:
            task = _make_full_task(view, context, provider, max_tokens, alternate)

        debounce.dispatch(view, task)

    @staticmethod
    def accept(view: sublime.View, edit: sublime.Edit) -> None:
        """Insert the ghost text at the cursor and clear the phantom."""
        state = _get_state(view)
        with state.lock:
            text  = state.completion_text
            point = state.cursor_point

        if not text or point < 0:
            return

        view.insert(edit, point, text)
        CompletionHandler.dismiss(view)
        sublime.status_message("[fast_autocomplete] Completion accepted.")

    @staticmethod
    def dismiss(view: sublime.View) -> None:
        """Erase the ghost text phantom without inserting anything."""
        state = _get_state(view)
        state.clear()
        debounce.cancel(view)
        _erase_phantom(view)
        sublime.status_message("")

    @staticmethod
    def cancel(view: sublime.View) -> None:
        """Cancel any in-flight request without clearing existing ghost text."""
        debounce.cancel(view)

    @staticmethod
    def cancel_all() -> None:
        """Cancel all requests across all views (plugin_unloaded)."""
        debounce.cancel_all()

    @staticmethod
    def has_pending(view: sublime.View) -> bool:
        """Return True if ghost text is currently displayed in this view."""
        state = _get_state(view)
        with state.lock:
            return bool(state.completion_text)

    @staticmethod
    def cursor_at_completion_point(view: sublime.View) -> bool:
        """Return True if the cursor is still at the original completion point."""
        state = _get_state(view)
        with state.lock:
            expected = state.cursor_point
        if expected < 0:
            return False
        sel = view.sel()
        return len(sel) == 1 and sel[0].b == expected


# ---------------------------------------------------------------------------
# Task factories — return callables for debounce.dispatch()
# ---------------------------------------------------------------------------

def _make_full_task(
    view: sublime.View,
    context: ContextPayload,
    provider: BaseProvider,
    max_tokens: int,
    alternate: bool,
):
    """Returns a background task for a non-streaming completion."""

    def task(token: debounce.RequestToken) -> None:
        if token.is_cancelled:
            return
        try:
            text = provider.complete(context, max_tokens, alternate)
        except AuthError as exc:
            _ui(lambda e=exc: sublime.error_message(
                f"[fast_autocomplete] Authentication failed:\n{e}\n\n"
                "Update your API key via Tools > st-fast-autocomplete > Set API Key."
            ))
            return
        except RateLimitError as exc:
            _ui(lambda e=exc: sublime.status_message(f"[fast_autocomplete] Rate limit: {e}"))
            return
        except ProviderTimeoutError:
            _ui(lambda: sublime.status_message("[fast_autocomplete] Request timed out."))
            return
        except ProviderError as exc:
            _ui(lambda e=exc: sublime.status_message(f"[fast_autocomplete] Error: {e}"))
            return

        if token.is_cancelled or not text:
            return

        _ui(lambda: _show_ghost_text(view, text))

    return task


def _make_stream_task(
    view: sublime.View,
    context: ContextPayload,
    provider: BaseProvider,
    max_tokens: int,
    alternate: bool,
):
    """Returns a background task for a streaming completion."""

    def task(token: debounce.RequestToken) -> None:
        if token.is_cancelled:
            return

        accumulated = ""

        try:
            for chunk in provider.complete_stream(context, max_tokens, alternate):
                if token.is_cancelled:
                    return
                accumulated += chunk
                # Capture current value for the lambda closure
                _snapshot = accumulated
                _ui(lambda s=_snapshot: _show_ghost_text(view, s))

        except AuthError as exc:
            _ui(lambda e=exc: sublime.error_message(
                f"[fast_autocomplete] Authentication failed:\n{e}\n\n"
                "Update your API key via Tools > st-fast-autocomplete > Set API Key."
            ))
        except RateLimitError as exc:
            _ui(lambda e=exc: sublime.status_message(f"[fast_autocomplete] Rate limit: {e}"))
        except ProviderTimeoutError:
            _ui(lambda: sublime.status_message("[fast_autocomplete] Request timed out."))
        except ProviderError as exc:
            _ui(lambda e=exc: sublime.status_message(f"[fast_autocomplete] Error: {e}"))

    return task


# ---------------------------------------------------------------------------
# Ghost text rendering (must run on UI thread)
# ---------------------------------------------------------------------------

def _show_ghost_text(view: sublime.View, text: str) -> None:
    """
    Render text as a minihtml phantom immediately after the cursor.
    Updates the per-view state so accept() can insert the correct text.
    """
    if not text:
        return

    state = _get_state(view)
    with state.lock:
        cursor_point = state.cursor_point
        state.completion_text = text

    if cursor_point < 0:
        return

    scope   = FastAutocompleteSettings.ghost_text_scope()
    escaped = _html_escape(text)

    # Style ghost text to look like a "comment" — dimmed, italicised
    html = (
        f'<body id="fast_autocomplete_ghost">'
        f'<span class="{scope}" style="font-style: italic; opacity: 0.55;">'
        f'{escaped}'
        f'</span>'
        f'</body>'
    )

    phantom_set = _get_phantom_set(view)
    phantom_set.update([
        sublime.Phantom(
            region=sublime.Region(cursor_point, cursor_point),
            content=html,
            layout=sublime.LAYOUT_INLINE,
        )
    ])

    sublime.status_message("[fast_autocomplete] Tab to accept · Escape to dismiss · Ctrl+Shift+N for alternative")


def _erase_phantom(view: sublime.View) -> None:
    """Remove the ghost text phantom from the view."""
    phantom_set = _get_phantom_set(view)
    phantom_set.update([])


def _get_phantom_set(view: sublime.View) -> sublime.PhantomSet:
    """Return (or lazily create) the PhantomSet for this view."""
    state = _get_state(view)
    with state.lock:
        if state.phantom_set is None:
            state.phantom_set = sublime.PhantomSet(view, _PHANTOM_KEY)
        return state.phantom_set


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _ui(fn) -> None:
    """Marshal a callable back to the ST UI thread."""
    sublime.set_timeout(fn, 0)


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for phantom content."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace(" ", "&nbsp;")
        .replace("\n", "<br>")
        .replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
    )