"""
plugin/debounce.py
Request queue and cancellation management for st-fast-autocomplete.

ST4 plugin code runs on the UI thread. All API calls are dispatched to
a background thread via sublime.set_timeout_async() to keep the editor
responsive. This module tracks in-flight requests per view and provides
clean cancellation when the user types, switches views, or requests an
alternative completion.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import sublime

# ---------------------------------------------------------------------------
# Per-view request token
# ---------------------------------------------------------------------------

class RequestToken:
    """
    Cancellation token for a single in-flight completion request.
    Thread-safe — cancelled flag is set from the UI thread and read
    from the background thread.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._lock      = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled


# ---------------------------------------------------------------------------
# Request dispatcher
# ---------------------------------------------------------------------------

# view.id() → active RequestToken
_active_tokens: dict[int, RequestToken] = {}
_tokens_lock = threading.Lock()


def dispatch(
    view: sublime.View,
    task: Callable[[RequestToken], None],
    delay_ms: int = 0,
) -> RequestToken:
    """
    Cancel any in-flight request for view, then dispatch task on a
    background thread after delay_ms milliseconds.

    Args:
        view:     The view this request is associated with.
        task:     Callable that accepts a RequestToken. Must check
                  token.is_cancelled periodically (e.g. per streamed token).
        delay_ms: Optional delay before execution (not used for manual
                  trigger, kept for future idle-trigger support).

    Returns:
        The new RequestToken for the dispatched task.
    """
    token = _replace_token(view)

    def _run() -> None:
        if not token.is_cancelled:
            task(token)

    if delay_ms > 0:
        sublime.set_timeout_async(_run, delay_ms)
    else:
        sublime.set_timeout_async(_run, 0)

    return token


def cancel(view: sublime.View) -> None:
    """Cancel any in-flight request for the given view."""
    view_id = view.id()
    with _tokens_lock:
        token = _active_tokens.get(view_id)
    if token:
        token.cancel()


def cancel_all() -> None:
    """Cancel all in-flight requests across all views (called on plugin_unloaded)."""
    with _tokens_lock:
        tokens = list(_active_tokens.values())
        _active_tokens.clear()
    for token in tokens:
        token.cancel()


def has_active(view: sublime.View) -> bool:
    """Return True if there is an active (non-cancelled) request for this view."""
    view_id = view.id()
    with _tokens_lock:
        token = _active_tokens.get(view_id)
    return token is not None and not token.is_cancelled


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _replace_token(view: sublime.View) -> RequestToken:
    """Cancel existing token for view (if any) and register a fresh one."""
    view_id = view.id()
    with _tokens_lock:
        old_token = _active_tokens.get(view_id)
        new_token = RequestToken()
        _active_tokens[view_id] = new_token

    if old_token:
        old_token.cancel()

    return new_token
