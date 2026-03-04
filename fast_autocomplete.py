"""
fast_autocomplete.py
Entry point for st-fast-autocomplete — AI-powered inline ghost text completion
for Sublime Text 4. Supports Claude and OpenAI providers.
"""

from __future__ import annotations

import sublime
import sublime_plugin

# ---------------------------------------------------------------------------
# Absolute imports
# ---------------------------------------------------------------------------
# ST4 loads plugins as sub-modules of a module named after the package,
# e.g. st_fast_autocomplete.fast_autocomplete. The Packages/ directory is
# on sys.path in the Python 3.8 host so absolute imports work directly.
# The .python-version file in the package root ensures ST uses Python 3.8.
from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
from st_fast_autocomplete.plugin.completion_handler import CompletionHandler
from st_fast_autocomplete.plugin.context_builder import ContextBuilder
from st_fast_autocomplete.plugin.keychain import KeychainManager
from st_fast_autocomplete.plugin.providers import get_provider


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------

def plugin_loaded() -> None:
    """Called by ST4 after the plugin is fully loaded."""
    FastAutocompleteSettings.load()
    KeychainManager.initialize()
    _install_keybindings()
    print("[fast_autocomplete] Plugin loaded.")


def _install_keybindings() -> None:
    """
    Install Tab/Escape/Ctrl+Shift+N bindings into the User package on first load.
    This is necessary because ST evaluates keymaps alphabetically — 'Default'
    package always sorts before any third-party package, so its unconditional
    Tab → insert binding would always win. User keybindings have highest priority.
    Existing User bindings are preserved; ours are prepended so they take priority.
    Re-runs are idempotent — existing fast_autocomplete bindings are replaced.
    """
    import json
    import os
    import sys

    platform = {"linux": "Linux", "darwin": "OSX", "win32": "Windows"}.get(sys.platform, "Linux")
    user_keymap_path = os.path.join(
        sublime.packages_path(), "User", f"Default ({platform}).sublime-keymap"
    )

    our_bindings = [
        {
            "keys": ["tab"],
            "command": "fast_autocomplete_accept",
            "context": [{"key": "fast_autocomplete_visible", "operator": "equal", "operand": True, "match_all": True}]
        },
        {
            "keys": ["escape"],
            "command": "fast_autocomplete_decline",
            "context": [{"key": "fast_autocomplete_visible", "operator": "equal", "operand": True, "match_all": True}]
        },
        {
            "keys": ["ctrl+shift+n"],
            "command": "fast_autocomplete_next",
            "context": [{"key": "fast_autocomplete_visible", "operator": "equal", "operand": True, "match_all": True}]
        },
    ]

    existing = []
    if os.path.exists(user_keymap_path):
        try:
            existing = sublime.decode_value(open(user_keymap_path).read())
        except Exception:
            existing = []

    # Remove any stale fast_autocomplete bindings then prepend fresh ones
    existing = [b for b in existing if not str(b.get("command", "")).startswith("fast_autocomplete_")]
    merged = our_bindings + existing

    os.makedirs(os.path.dirname(user_keymap_path), exist_ok=True)
    with open(user_keymap_path, "w") as f:
        f.write(sublime.encode_value(merged, pretty=True))

    if FastAutocompleteSettings.debug():
        print(f"[fast_autocomplete] Keybindings installed to {user_keymap_path}")


def plugin_unloaded() -> None:
    """Called by ST4 before the plugin is unloaded / reloaded."""
    CompletionHandler.cancel_all()
    print("[fast_autocomplete] Plugin unloaded.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class FastAutocompleteTriggerCommand(sublime_plugin.TextCommand):
    """
    Trigger an AI completion at the current cursor position.
    Default keybinding: Ctrl+Space
    """

    def run(self, edit: sublime.Edit) -> None:
        view = self.view

        sel = view.sel()
        if len(sel) != 1:
            return

        cursor_point = sel[0].b
        context      = ContextBuilder.build(view, cursor_point)
        settings     = FastAutocompleteSettings.get()

        try:
            provider = get_provider(settings)
        except ValueError as exc:
            sublime.error_message(f"[fast_autocomplete] {exc}")
            return

        max_tokens = max(1, min(
            int(settings.get("max_completion_tokens", 128)),
            4096,
        ))

        CompletionHandler.request(
            view=view,
            cursor_point=cursor_point,
            context=context,
            provider=provider,
            streaming=settings.get("streaming", False),
            max_tokens=max_tokens,
        )

    def is_enabled(self) -> bool:
        return not self.view.is_read_only()


class FastAutocompleteNextCommand(sublime_plugin.TextCommand):
    """
    Request an alternative completion, discarding the current ghost text.
    Default keybinding: Ctrl+Shift+N
    """

    def run(self, edit: sublime.Edit) -> None:
        view = self.view
        CompletionHandler.dismiss(view)

        sel = view.sel()
        if len(sel) != 1:
            return

        cursor_point = sel[0].b
        context      = ContextBuilder.build(view, cursor_point)
        settings     = FastAutocompleteSettings.get()

        try:
            provider = get_provider(settings)
        except ValueError as exc:
            sublime.error_message(f"[fast_autocomplete] {exc}")
            return

        max_tokens = max(1, min(
            int(settings.get("max_completion_tokens", 128)),
            4096,
        ))

        CompletionHandler.request(
            view=view,
            cursor_point=cursor_point,
            context=context,
            provider=provider,
            streaming=settings.get("streaming", False),
            max_tokens=max_tokens,
            alternate=True,
        )

    def is_enabled(self) -> bool:
        return CompletionHandler.has_pending(self.view) and not self.view.is_read_only()

    def is_visible(self) -> bool:
        return True


class FastAutocompleteAcceptCommand(sublime_plugin.TextCommand):
    """
    Accept the currently displayed ghost text completion.
    Default keybinding: Tab
    """

    def run(self, edit: sublime.Edit) -> None:
        CompletionHandler.accept(self.view, edit)

    def is_enabled(self) -> bool:
        return CompletionHandler.has_pending(self.view)

    def is_visible(self) -> bool:
        return True


class FastAutocompleteDeclineCommand(sublime_plugin.TextCommand):
    """
    Dismiss the currently displayed ghost text completion.
    Default keybinding: Escape
    """

    def run(self, edit: sublime.Edit) -> None:
        CompletionHandler.dismiss(self.view)

    def is_enabled(self) -> bool:
        return CompletionHandler.has_pending(self.view)

    def is_visible(self) -> bool:
        return True


class FastAutocompleteSetApiKeyCommand(sublime_plugin.ApplicationCommand):
    """
    Prompt the user to enter / update an API key for a given provider.
    Accessible via: Tools > st-fast-autocomplete > Set API Key
    """

    def run(self, provider: str = "claude") -> None:
        window = sublime.active_window()
        if not window:
            return

        def on_done(api_key: str) -> None:
            api_key = api_key.strip()
            if not api_key:
                sublime.status_message("[fast_autocomplete] API key not saved (empty input).")
                return
            KeychainManager.set_key(provider, api_key)
            sublime.status_message(f"[fast_autocomplete] API key saved for provider: {provider}")

        window.show_input_panel(
            caption=f"Enter API key for {provider}:",
            initial_text="",
            on_done=on_done,
            on_change=None,
            on_cancel=None,
        )


class FastAutocompleteSelectProviderCommand(sublime_plugin.ApplicationCommand):
    """
    Quick-panel selector to switch between AI providers.
    Accessible via command palette: FastAutocomplete: Select Provider
    """

    PROVIDERS = ["claude", "openai"]

    def run(self) -> None:
        window = sublime.active_window()
        if not window:
            return

        current = FastAutocompleteSettings.get().get("provider", "claude")
        items = [
            f"{'✓ ' if p == current else '  '}{p.capitalize()}"
            for p in self.PROVIDERS
        ]

        def on_select(index: int) -> None:
            if index == -1:
                return
            selected = self.PROVIDERS[index]
            FastAutocompleteSettings.set("provider", selected)
            sublime.status_message(f"[fast_autocomplete] Provider switched to: {selected}")

        window.show_quick_panel(items, on_select)


class FastAutocompleteToggleStreamingCommand(sublime_plugin.ApplicationCommand):
    """
    Toggle streaming on/off.
    Accessible via command palette: FastAutocomplete: Toggle Streaming
    """

    def run(self) -> None:
        current = FastAutocompleteSettings.get().get("streaming", False)
        FastAutocompleteSettings.set("streaming", not current)
        state = "enabled" if not current else "disabled"
        sublime.status_message(f"[fast_autocomplete] Streaming {state}.")


class FastAutocompleteResetPromptsCommand(sublime_plugin.ApplicationCommand):
    """
    Reset system_prompt, completion_instruction, and alternate_instruction
    to their built-in defaults, erasing any User overrides.
    Accessible via command palette: FastAutocomplete: Reset Prompts to Default
    """

    def run(self) -> None:
        if sublime.ok_cancel_dialog(
            "Reset all prompt settings to their built-in defaults?\n\n"
            "This will erase your custom system_prompt, completion_instruction, "
            "and alternate_instruction from User settings.",
            ok_title="Reset",
        ):
            FastAutocompleteSettings.reset_prompts()
            sublime.status_message("[fast_autocomplete] Prompts reset to defaults.")


# ---------------------------------------------------------------------------
# Event listener
# ---------------------------------------------------------------------------

class FastAutocompleteEventListener(sublime_plugin.EventListener):

    def on_modified(self, view: sublime.View) -> None:
        """Clear pending ghost text if the user types anything."""
        if CompletionHandler.is_rendering(view):
            return  # phantom insertion triggers on_modified — ignore it
        if CompletionHandler.has_pending(view):
            CompletionHandler.dismiss(view)

    def on_selection_modified(self, view: sublime.View) -> None:
        """Clear ghost text if cursor moves away from completion point."""
        if CompletionHandler.is_rendering(view):
            return  # phantom insertion may shift selection — ignore it
        if CompletionHandler.has_pending(view):
            if not CompletionHandler.cursor_at_completion_point(view):
                CompletionHandler.dismiss(view)

    def on_activated(self, view: sublime.View) -> None:
        """Cancel any in-flight request when switching views."""
        CompletionHandler.cancel(view)

    def on_query_context(
        self,
        view: sublime.View,
        key: str,
        operator: int,
        operand: object,
        match_all: bool,
    ) -> bool | None:
        """
        Resolve the fast_autocomplete_visible context key used in keybindings.
        ST passes operator as an integer constant, not a string.
        Returns True/False when key matches, None to pass through to ST.
        """
        if key != "fast_autocomplete_visible":
            return None
        is_visible = CompletionHandler.has_pending(view)
        # sublime.OP_EQUAL = 0, sublime.OP_NOT_EQUAL = 1
        if operator == sublime.OP_EQUAL:
            return is_visible == operand
        if operator == sublime.OP_NOT_EQUAL:
            return is_visible != operand
        return None