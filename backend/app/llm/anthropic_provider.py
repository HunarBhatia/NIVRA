"""Claude through the official Anthropic SDK.

- Model claude-opus-5-5 with adaptive thinking; effort is configurable
  (default "low": these are short, well-specified drafting tasks).
- Structured output (output_config.format = JSON schema) so replies are
  machine-readable; we still validate them (guardrails.py).
- Server-side refusal fallbacks are on by default (beta
  server-side-fallback-2026-07-01, fallbacks="default"); a gateway such as
  Prune may not accept that beta, so it is switchable.
- Errors are mapped to LLMError with a retryable flag; the SDK itself
  already retries 429/5xx/connection errors twice.
"""

import json
from typing import Any

import anthropic

from app.llm.base import LLMError

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str | None, model: str = "claude-opus-5-5", effort: str = "low",
                 base_url: str | None = None, use_fallbacks: bool = True, timeout: float = 60.0,
                 provider_name: str = "anthropic", max_retries: int = 2,
                 http_client: Any = None):
        self.model = model
        self.effort = effort
        self.use_fallbacks = use_fallbacks
        self.name = provider_name
        self._configured = bool(api_key)
        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url, timeout=timeout,
                                           max_retries=max_retries,
                                           http_client=http_client) if api_key else None

    @property
    def available(self) -> bool:
        return self._configured

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any],
                      max_tokens: int = 4000) -> dict[str, Any]:
        if self._client is None:
            raise LLMError("not_configured")
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if self.use_fallbacks:
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        try:
            response = self._client.beta.messages.create(**kwargs)
        except anthropic.AuthenticationError:
            raise LLMError("auth") from None
        except anthropic.PermissionDeniedError:
            raise LLMError("permission") from None
        except anthropic.BadRequestError:
            raise LLMError("bad_request") from None
        except anthropic.RateLimitError:
            raise LLMError("rate_limited", retryable=True) from None
        except anthropic.APIStatusError as e:
            raise LLMError("server_error" if e.status_code >= 500 else "api_error",
                           retryable=e.status_code >= 500) from None
        except anthropic.APIConnectionError:
            raise LLMError("connection", retryable=True) from None

        if response.stop_reason == "refusal":
            raise LLMError("refusal")
        if response.stop_reason == "max_tokens":
            raise LLMError("truncated", retryable=True)
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("empty", retryable=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise LLMError("invalid_json", retryable=True) from None
        if not isinstance(data, dict):
            raise LLMError("invalid_json", retryable=True)
        return data
