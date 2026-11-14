"""Chooses the LLM provider from settings (NIVRA_LLM_PROVIDER), D25.

gemini - default. Google Gemini (NIVRA_GEMINI_API_KEY or GEMINI_API_KEY),
         model NIVRA_LLM_MODEL (default gemini-3.1-flash-lite). With no key
         set, agents fall back to templates and rules automatically.
none   - never call a model; templates and rules only.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider, NoLLM
from app.llm.gemini_provider import GeminiProvider

_override: LLMProvider | None = None


def set_llm_for_tests(provider: LLMProvider | None) -> None:
    global _override
    _override = provider


@lru_cache
def _configured() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "gemini" and s.gemini_api_key:
        return GeminiProvider(api_key=s.gemini_api_key, model=s.llm_model)
    return NoLLM()


def get_llm() -> LLMProvider:
    return _override if _override is not None else _configured()
