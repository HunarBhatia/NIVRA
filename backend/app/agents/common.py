"""Shared helpers: validated LLM calls with retries, and step logging."""

import time
from collections.abc import Callable
from typing import Any

from app.llm import LLMError, LLMProvider

MAX_ATTEMPTS = 3


class AgentInputError(Exception):
    """The run refers to something that doesn't exist or isn't the user's."""


def step(state: dict, name: str, ok: bool = True, note: str | None = None) -> list[dict]:
    """Execution log entry. Notes are short codes - never content."""
    return [*state.get("steps", []), {"node": name, "ok": ok, "note": note, "at": time.time()}]


def llm_validated(
    llm: LLMProvider,
    *,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    validate: Callable[[dict[str, Any]], list[str]],
    max_tokens: int = 4000,
) -> tuple[dict[str, Any] | None, int, list[str]]:
    """Calls the LLM until its output passes `validate` (max 3 attempts).

    Validation problems are sent back to the model so it can fix them.
    Returns (output or None, attempts used, notes). None means: use the
    deterministic fallback.
    """
    notes: list[str] = []
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = llm.generate_json(system=system, prompt=prompt + feedback, schema=schema,
                                     max_tokens=max_tokens)
        except LLMError as e:
            notes.append(f"llm_error:{e.code}")
            if not e.retryable:
                return None, attempt, notes
            continue
        problems = validate(data)
        if not problems:
            return data, attempt, notes
        notes.append(f"invalid:{len(problems)}")
        feedback = (
            "\n\nYour previous answer was rejected for these reasons. Fix all of them:\n- "
            + "\n- ".join(problems)
        )
    return None, MAX_ATTEMPTS, notes
