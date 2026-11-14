"""Chooses the LLM provider from settings (NIVRA_LLM_PROVIDER).

none      - default; agents use rules and templates only.
anthropic - Claude directly (NIVRA_ANTHROPIC_API_KEY).
prune     - Claude via the Prune gateway (NIVRA_PRUNE_API_KEY). OPTIONAL and
            UNVERIFIED: Prune's docs give an Anthropic-SDK base URL but don't
            confirm Messages API support or data retention (section 13.15).
"""

from functools import lru_cache

from app.core.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider, NoLLM

_override: LLMProvider | None = None


def set_llm_for_tests(provider: LLMProvider | None) -> None:
    global _override
    _override = provider


@lru_cache
def _configured() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "anthropic":
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model, effort=s.llm_effort)
    if s.llm_provider == "prune":
        return AnthropicProvider(api_key=s.prune_api_key, model=s.llm_model, effort=s.llm_effort,
                                 base_url=s.prune_base_url, use_fallbacks=False,
                                 provider_name="prune")
    return NoLLM()


def get_llm() -> LLMProvider:
    return _override if _override is not None else _configured()
