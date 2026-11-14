"""LLM access behind one small interface (decision D16, section 17).

Agents call get_llm().generate_json(...). Which model answers - Google
Gemini (default, D25) or nothing (rules and templates only) - is
configuration, so the provider can change without touching agent code.
"""

from app.llm.base import LLMError, LLMProvider, NoLLM
from app.llm.factory import get_llm

__all__ = ["LLMError", "LLMProvider", "NoLLM", "get_llm"]
