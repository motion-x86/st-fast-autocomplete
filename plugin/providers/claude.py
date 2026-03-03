"""
plugin/providers/claude.py
Anthropic Claude completion provider.
Uses urllib (stdlib) for HTTP — no third-party SDK required.
Supports both full-response and streaming (SSE) modes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Generator, Optional

from st_fast_autocomplete.plugin.providers.base import BaseProvider, ProviderError, AuthError, RateLimitError, ProviderTimeoutError
from st_fast_autocomplete.plugin.context_builder import ContextPayload
from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class ClaudeProvider(BaseProvider):

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    # ------------------------------------------------------------------
    # Full response
    # ------------------------------------------------------------------

    def complete(
        self,
        context: ContextPayload,
        max_tokens: int,
        alternate: bool = False,
    ) -> str:
        payload = self._build_payload(context, max_tokens, alternate, stream=False)
        headers = self._headers()
        timeout = FastAutocompleteSettings.request_timeout_seconds()

        data = _http_post(_API_URL, headers, payload, timeout)

        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected Claude response shape: {data}") from exc

    # ------------------------------------------------------------------
    # Streaming (SSE)
    # ------------------------------------------------------------------

    def complete_stream(
        self,
        context: ContextPayload,
        max_tokens: int,
        alternate: bool = False,
    ) -> Generator[str, None, None]:
        payload = self._build_payload(context, max_tokens, alternate, stream=True)
        headers = self._headers()
        timeout = FastAutocompleteSettings.request_timeout_seconds()

        req = urllib.request.Request(
            _API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").rstrip("\n")
                    if not line.startswith("data:"):
                        continue
                    raw_json = line[len("data:"):].strip()
                    if raw_json == "[DONE]":
                        break
                    try:
                        event = json.loads(raw_json)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    # content_block_delta carries the token text
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")

                    elif event_type == "message_stop":
                        break

        except urllib.error.HTTPError as exc:
            raise _map_http_error(exc) from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError("Claude request timed out.") from exc
        except OSError as exc:
            raise ProviderError(f"Claude network error: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        context: ContextPayload,
        max_tokens: int,
        alternate: bool,
        stream: bool,
    ) -> dict:
        return {
            "model":      self.model,
            "max_tokens": max_tokens,
            "temperature": self.temperature(alternate),
            "stream":     stream,
            "system": (
                "You are an expert code completion engine. "
                "Return ONLY the completion text — no explanation, "
                "no markdown, no code fences."
            ),
            "messages": [
                {
                    "role":    "user",
                    "content": self.build_prompt(context, alternate),
                }
            ],
        }

    def _headers(self) -> dict:
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         self.api_key,
            "anthropic-version": _API_VERSION,
        }
        # Opt out of Anthropic model training on this request
        if FastAutocompleteSettings.get_value("privacy_no_retention", False):
            headers["anthropic-beta"] = "no-train-1"
        return headers


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_post(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _map_http_error(exc) from exc
    except TimeoutError as exc:
        raise ProviderTimeoutError("Claude request timed out.") from exc
    except OSError as exc:
        raise ProviderError(f"Claude network error: {exc}") from exc


def _map_http_error(exc: urllib.error.HTTPError) -> ProviderError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        message = body.get("error", {}).get("message", str(exc))
    except Exception:
        message = str(exc)

    if exc.code == 401:
        return AuthError(f"Invalid Claude API key. {message}", status_code=401)
    if exc.code == 429:
        return RateLimitError(f"Claude rate limit exceeded. {message}", status_code=429)
    return ProviderError(f"Claude API error {exc.code}: {message}", status_code=exc.code)