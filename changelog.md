# Changelog

All notable changes to st-fast-autocomplete are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

## [0.1.0] — 2026-03-03

### Added
- Inline ghost text completions via Claude (Anthropic) and OpenAI
- Manual trigger (`Ctrl+Space`), accept (`Tab`), dismiss (`Escape`)
- `Ctrl+Shift+N` to request an alternative completion
- Streaming support (optional, configurable)
- OS keychain storage for API keys (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- Configurable context window (`context_lines_before` / `context_lines_after`)
- Bounded completion length via `max_completion_tokens` (default: 128, hard ceiling: 4096)
- User-configurable prompts (`system_prompt`, `completion_instruction`, `alternate_instruction`) with `{language}`, `{file_name}`, `{file_name_clause}` placeholder support
- "Reset Prompts to Default" command
- Privacy controls: comment stripping, string literal redaction, custom regex patterns, no-retention request headers
- LSP coexistence mode
- ST4 / Python 3.8+ only
- Package Control compatible