"""
plugin/providers/openai.py
OpenAI completion provider.
Uses urllib (stdlib) for HTTP — no third-party SDK required.
Supports both full-response and streaming (SSE) modes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Generator

from st_fast_autocomplete.plugin.providers.base import BaseProvider, ProviderError, AuthError, RateLimitError, ProviderTimeoutError
from st_fast_autocomplete.plugin.context_builder import ContextPayload
from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings

_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(BaseProvider):

    DEFAULT_MODEL = "gpt-4o"

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
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected OpenAI response shape: {data}") from exc

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

                    # Extract delta content token
                    try:
                        token = event["choices"][0]["delta"].get("content", "")
                        if token:
                            yield token
                    except (KeyError, IndexError):
                        continue

        except urllib.error.HTTPError as exc:
            raise _map_http_error(exc) from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError("OpenAI request timed out.") from exc
        except OSError as exc:
            raise ProviderError(f"OpenAI network error: {exc}") from exc

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
            "model":       self.model,
            "max_tokens":  max_tokens,
            "temperature": self.temperature(alternate),
            "stream":      stream,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert code completion engine. "
                        "Return ONLY the completion text — no explanation, "
                        "no markdown, no code fences."
                    ),
                },
                {
                    "role":    "user",
                    "content": self.build_prompt(context, alternate),
                },
            ],
        }

    def _headers(self) -> dict:
        from st_fast_autocomplete.plugin.settings import FastAutocompleteSettings
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # OpenAI Zero Data Retention is an enterprise account setting, but
        # the header signals intent and is forwarded where supported.
        if FastAutocompleteSettings.get_value("privacy_no_retention", False):
            headers["OpenAI-Data-Retention"] = "none"
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
        raise ProviderTimeoutError("OpenAI request timed out.") from exc
    except OSError as exc:
        raise ProviderError(f"OpenAI network error: {exc}") from exc


def _map_http_error(exc: urllib.error.HTTPError) -> ProviderError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        message = body.get("error", {}).get("message", str(exc))
    except Exception:
        message = str(exc)

    if exc.code == 401:
        return AuthError(f"Invalid OpenAI API key. {message}", status_code=401)
    if exc.code == 429:
        return RateLimitError(f"OpenAI rate limit exceeded. {message}", status_code=429)
    return ProviderError(f"OpenAI API error {exc.code}: {message}", status_code=exc.code)