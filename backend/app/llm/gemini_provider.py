"""Google Gemini through the official Google Gen AI SDK (google-genai).

- Model from NIVRA_LLM_MODEL, default "gemini-3.1-flash-lite" (D25).
- JSON output: response_mime_type="application/json" with
  response_json_schema, so replies are machine-readable; we still validate
  them (guardrails.py) - the schema shapes the answer, it doesn't police it.
- Safety blocks and truncation are detected from the finish reason.
- Errors map to LLMError with a retryable flag (429 and 5xx retry).
- The model only ever receives placeholders and case facts - never links,
  names or images (section 17.6).
"""

import json
from typing import Any

from google import genai
from google.genai import errors, types

from app.llm.base import LLMError

BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "MODEL_ARMOR"}


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str | None, model: str = "gemini-3.1-flash-lite",
                 timeout_ms: int = 60_000, http_client: Any = None):
        self.model = model
        self._configured = bool(api_key)
        self._client = None
        if api_key:
            options: dict[str, Any] = {"timeout": timeout_ms}
            if http_client is not None:  # tests inject a mock transport
                options["httpx_client"] = http_client
            self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(**options))

    @property
    def available(self) -> bool:
        return self._configured

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any],
                      max_tokens: int = 4000) -> dict[str, Any]:
        if self._client is None:
            raise LLMError("not_configured")
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=max_tokens,
        )
        try:
            response = self._client.models.generate_content(model=self.model, contents=prompt,
                                                            config=config)
        except errors.ClientError as e:
            if e.code == 429:
                raise LLMError("rate_limited", retryable=True) from None
            if e.code in (401, 403):
                raise LLMError("auth") from None
            if e.code == 404:
                raise LLMError("model_not_found") from None
            raise LLMError("bad_request") from None
        except errors.ServerError:
            raise LLMError("server_error", retryable=True) from None
        except errors.APIError:
            raise LLMError("api_error", retryable=True) from None
        except Exception as e:  # network failures surface as httpx/OS errors
            if type(e).__name__ in ("ConnectError", "ReadTimeout", "ConnectTimeout", "TimeoutException"):
                raise LLMError("connection", retryable=True) from None
            raise

        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise LLMError("refusal")
        candidates = response.candidates or []
        if not candidates:
            raise LLMError("empty", retryable=True)
        reason = getattr(candidates[0].finish_reason, "name", str(candidates[0].finish_reason or ""))
        if reason in BLOCKED:
            raise LLMError("refusal")
        if reason == "MAX_TOKENS":
            raise LLMError("truncated", retryable=True)
        text = response.text
        if not text:
            raise LLMError("empty", retryable=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise LLMError("invalid_json", retryable=True) from None
        if not isinstance(data, dict):
            raise LLMError("invalid_json", retryable=True)
        return data
