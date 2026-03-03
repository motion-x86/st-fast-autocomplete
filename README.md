# st-fast-autocomplete

Lightweight AI-powered inline ghost text autocomplete for Sublime Text 4.  
Supports **Claude** (Anthropic) and **OpenAI** as completion providers.

---

## Requirements

- Sublime Text 4 (Build 4107+)
- Python 3.8+ (bundled with ST4)
- An API key for Claude or OpenAI

---

## Installation

### Via Package Control _(recommended)_
1. Open the command palette: `Ctrl+Shift+P` / `Cmd+Shift+P`
2. Run `Package Control: Install Package`
3. Search for `st-fast-autocomplete`

### Manual
```bash
# 1. Build the package
python build.py --version 0.1.0 --clean

# 2. Copy the unpacked folder into ST's Packages directory.
#    Use the unpacked/ output — NOT the .sublime-package zip.
#    ST4 only adds unpacked Packages/ directories to sys.path;
#    zipped installs are for Package Control distribution only.

# macOS
cp -r dist/unpacked/st_fast_autocomplete/. \
   ~/Library/Application\ Support/Sublime\ Text/Packages/st_fast_autocomplete/

# Linux
mkdir -p ~/.config/sublime-text/Packages/st_fast_autocomplete
cp -r dist/unpacked/st_fast_autocomplete/. ~/.config/sublime-text/Packages/st_fast_autocomplete/

# Windows (PowerShell)
Copy-Item -Recurse dist\unpacked\st_fast_autocomplete \
   "$env:APPDATA\Sublime Text\Packages\"

# IMPORTANT: verify the .python-version dotfile was copied
# macOS/Linux:
ls -la ~/.config/sublime-text/Packages/st_fast_autocomplete/.python-version
# Should print: 3.8
# If missing, copy it manually:
# cp dist/unpacked/st_fast_autocomplete/.python-version \
#    ~/.config/sublime-text/Packages/st_fast_autocomplete/

# 3. Restart Sublime Text
```

---

## Setup

### 1. Store your API key

Open the command palette and run one of:

```
FastAutocomplete: Set API Key (claude)
FastAutocomplete: Set API Key (openai)
```

Keys are stored securely in your **OS keychain** (Keychain on macOS, Secret Service on Linux, Credential Manager on Windows). They are never written to disk in plaintext.

### 2. Select your provider

```
FastAutocomplete: Select Provider
```

Or set it directly in your settings file:

```json
{
    "provider": "claude"
}
```

---

## Usage

### Commands & Keybindings

All default keybindings can be customised — see [Customising Keybindings](#customising-keybindings).

| Action | Default Keybinding | Command Palette |
|---|---|---|
| **Trigger completion** | `Ctrl+Space` | `FastAutocomplete: Trigger` |
| **Accept ghost text** | `Tab` | — |
| **Dismiss ghost text** | `Escape` | — |
| **Request alternative completion** | `Ctrl+Shift+N` | `FastAutocomplete: Next Completion` |
| **Select provider** | — | `FastAutocomplete: Select Provider` |
| **Set API key** | — | `FastAutocomplete: Set API Key` |
| **Toggle streaming** | — | `FastAutocomplete: Toggle Streaming` |

#### Workflow

1. Position your cursor where you want a completion.
2. Press `Ctrl+Space` — ghost text appears inline.
3. Press `Tab` to accept, `Escape` to dismiss.
4. Not happy with the suggestion? Press `Ctrl+Shift+N` to request an alternative without moving your cursor.

---

## Settings

Open via: `Preferences > Package Settings > st-fast-autocomplete > Settings`

```jsonc
{
    // AI provider: "claude" or "openai"
    "provider": "claude",

    // Model to use for completions
    // Claude:  "claude-sonnet-4-20250514" | "claude-haiku-4-5-20251001"
    // OpenAI:  "gpt-4o" | "gpt-4o-mini"
    "model": "claude-sonnet-4-20250514",

    // Maximum number of tokens in the completion response.
    // Lower values = faster, cheaper, shorter completions.
    // Hard ceiling: 4096. Default: 128.
    "max_completion_tokens": 128,

    // Number of lines above/below the cursor sent as context
    "context_lines": 50,

    // Enable streaming (tokens appear as they arrive)
    "streaming": false,
}
```

### `max_completion_tokens`

This setting bounds the length of every completion response. It maps directly to the `max_tokens` parameter of the underlying API call.

- **Default:** `128` — suitable for single-line and short block completions.
- **Increase** to `256–512` for multi-line completions (functions, classes).
- **Hard ceiling** of `4096` is enforced by the plugin regardless of what is set here.

---

## Customising Keybindings

The plugin ships with sensible defaults but all keys are overridable.

Open `Preferences > Key Bindings` and add your overrides to the **User** keymap:

```json
[
    // Change trigger to Alt+/ 
    {
        "keys": ["alt+/"],
        "command": "fast_autocomplete_trigger",
        "context": [{ "key": "setting.is_widget", "operator": "equal", "operand": false }]
    },

    // Change accept to Enter instead of Tab
    {
        "keys": ["enter"],
        "command": "fast_autocomplete_accept",
        "context": [{ "key": "fast_autocomplete_visible", "operator": "equal", "operand": true }]
    },

    // Change "next completion" to Ctrl+Alt+N
    {
        "keys": ["ctrl+alt+n"],
        "command": "fast_autocomplete_next",
        "context": [{ "key": "fast_autocomplete_visible", "operator": "equal", "operand": true }]
    }
]
```

The `fast_autocomplete_visible` context key is `true` only when ghost text is currently displayed, so accept/dismiss bindings won't interfere with normal editing.

---

## LSP Compatibility

`st-fast-autocomplete` is designed to coexist with [LSP for Sublime Text](https://github.com/sublimelsp/LSP). When an LSP completion popup is active, ghost text is suppressed to avoid conflicts. LSP completions always take priority.

---

## Privacy

- Only the content of the **current file** (bounded by `context_lines`) and the file's **syntax scope** are sent to the API.
- No file paths, project names, or other metadata are transmitted.
- API keys are stored in the OS keychain and never logged or written to disk.

---

## License

MIT