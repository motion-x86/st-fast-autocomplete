"""
plugin/completion_handler.py
Ghost text rendering, accept/dismiss, and streaming update logic.
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
    def __init__(self) -> None:
        self.completion_text: str                      = ""
        self.cursor_point:    int                      = -1
        self.phantom_set:     Optional[sublime.PhantomSet] = None
        self.rendering:       bool                     = False
        self.lock:            threading.Lock           = threading.Lock()

    def clear(self) -> None:
        with self.lock:
            self.completion_text = ""
            self.cursor_point    = -1


_states: dict[int, _ViewState] = {}
_states_lock = threading.Lock()
_PHANTOM_KEY = "fast_autocomplete_ghost"


def _get_state(view: sublime.View) -> _ViewState:
    view_id = view.id()
    with _states_lock:
        if view_id not in _states:
            _states[view_id] = _ViewState()
        return _states[view_id]


# ---------------------------------------------------------------------------
# Public API
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
        state = _get_state(view)
        state.clear()
        debounce.cancel(view)
        _erase_phantom(view)
        sublime.status_message("")

    @staticmethod
    def cancel(view: sublime.View) -> None:
        debounce.cancel(view)

    @staticmethod
    def cancel_all() -> None:
        debounce.cancel_all()

    @staticmethod
    def has_pending(view: sublime.View) -> bool:
        state = _get_state(view)
        with state.lock:
            return bool(state.completion_text) or state.rendering

    @staticmethod
    def is_rendering(view: sublime.View) -> bool:
        """True while a phantom is being inserted — suppress event-driven dismissal."""
        state = _get_state(view)
        with state.lock:
            return state.rendering

    @staticmethod
    def cursor_at_completion_point(view: sublime.View) -> bool:
        state = _get_state(view)
        with state.lock:
            expected = state.cursor_point
        if expected < 0:
            return False
        sel = view.sel()
        return len(sel) == 1 and sel[0].b == expected


# ---------------------------------------------------------------------------
# Task factories
# ---------------------------------------------------------------------------

def _make_full_task(
    view: sublime.View,
    context: ContextPayload,
    provider: BaseProvider,
    max_tokens: int,
    alternate: bool,
):
    def task(token: debounce.RequestToken) -> None:
        if token.is_cancelled:
            return

        text = None
        err_msg = None
        is_auth_err = False

        try:
            text = provider.complete(context, max_tokens, alternate)
        except AuthError as exc:
            err_msg = (
                f"[fast_autocomplete] Authentication failed:\n{exc}\n\n"
                "Update your API key via Tools > st-fast-autocomplete > Set API Key."
            )
            is_auth_err = True
        except RateLimitError as exc:
            err_msg = f"[fast_autocomplete] Rate limit: {exc}"
        except ProviderTimeoutError:
            err_msg = "[fast_autocomplete] Request timed out."
        except ProviderError as exc:
            err_msg = f"[fast_autocomplete] Error: {exc}"

        if err_msg is not None:
            _show_error(err_msg, is_auth_err)
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
    def task(token: debounce.RequestToken) -> None:
        if token.is_cancelled:
            return

        accumulated = ""
        err_msg = None
        is_auth_err = False

        try:
            for chunk in provider.complete_stream(context, max_tokens, alternate):
                if token.is_cancelled:
                    return
                accumulated += chunk
                _snapshot = accumulated
                _ui(lambda s=_snapshot: _show_ghost_text(view, s))
        except AuthError as exc:
            err_msg = (
                f"[fast_autocomplete] Authentication failed:\n{exc}\n\n"
                "Update your API key via Tools > st-fast-autocomplete > Set API Key."
            )
            is_auth_err = True
        except RateLimitError as exc:
            err_msg = f"[fast_autocomplete] Rate limit: {exc}"
        except ProviderTimeoutError:
            err_msg = "[fast_autocomplete] Request timed out."
        except ProviderError as exc:
            err_msg = f"[fast_autocomplete] Error: {exc}"

        if err_msg is not None:
            _show_error(err_msg, is_auth_err)

    return task


# ---------------------------------------------------------------------------
# Ghost text rendering
# ---------------------------------------------------------------------------

def _show_ghost_text(view: sublime.View, text: str) -> None:
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
    html = (
        f'<body id="fast_autocomplete_ghost">'
        f'<span class="{scope}" style="font-style: italic; opacity: 0.55;">'
        f'{escaped}'
        f'</span>'
        f'</body>'
    )
    state = _get_state(view)
    with state.lock:
        state.rendering = True
    phantom_set = _get_phantom_set(view)
    phantom_set.update([
        sublime.Phantom(
            region=sublime.Region(cursor_point, cursor_point),
            content=html,
            layout=sublime.LAYOUT_INLINE,
        )
    ])
    with state.lock:
        state.rendering = False
    sublime.status_message(
        "[fast_autocomplete] Tab to accept · Escape to dismiss · Ctrl+Shift+N for alternative"
    )


def _erase_phantom(view: sublime.View) -> None:
    _get_phantom_set(view).update([])


def _get_phantom_set(view: sublime.View) -> sublime.PhantomSet:
    state = _get_state(view)
    with state.lock:
        if state.phantom_set is None:
            state.phantom_set = sublime.PhantomSet(view, _PHANTOM_KEY)
        return state.phantom_set


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _ui(fn) -> None:
    """Marshal a callable to the ST UI thread."""
    sublime.set_timeout(fn, 0)


def _show_error(message: str, is_error: bool = False) -> None:
    """
    Show an error or status message on the UI thread.
    message is captured as a local variable before set_timeout is called —
    no lambdas, no closures, no exc scope issues.
    """
    if is_error:
        sublime.set_timeout(lambda: sublime.error_message(message), 0)
    else:
        sublime.set_timeout(lambda: sublime.status_message(message), 0)


def _html_escape(text: str) -> str:
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