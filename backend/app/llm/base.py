"""The provider interface every LLM backend implements."""

from typing import Any, Protocol


class LLMError(Exception):
    """A failed LLM call. `retryable` says whether trying again may help;
    `code` is safe to store and show (never contains prompt content)."""

    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str
    model: str | None

    @property
    def available(self) -> bool: ...

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any],
                      max_tokens: int = 4000) -> dict[str, Any]:
        """Returns a dict matching `schema`, or raises LLMError."""
        ...


class NoLLM:
    """No model configured: agents use their deterministic rules/templates."""

    name = "none"
    model = None

    @property
    def available(self) -> bool:
        return False

    def generate_json(self, **_: Any) -> dict[str, Any]:
        raise LLMError("not_configured")
