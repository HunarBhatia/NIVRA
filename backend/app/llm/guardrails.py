"""Checks applied to every LLM output before it is used (section 17.7).

An LLM can invent laws, make claims we can't back, or drop the placeholders
we fill in later. Each check returns a list of problems; an empty list means
the output may be used. Problems are fed back to the model on retry.
"""

import re

PLACEHOLDERS_REQUIRED = ("{{URL}}", "{{NAME}}")
PLACEHOLDERS_ALLOWED = {"{{URL}}", "{{NAME}}", "{{DATE}}", "{{SENT_DATE}}"}

# Statements Nivra must never make on a user's behalf or about a match.
FORBIDDEN_IN_DRAFTS = [
    (r"\bi am (a|an|your) (lawyer|advocate|attorney)\b", "claims to be a lawyer"),
    (r"\b(guarantee|guaranteed)\b", "makes a guarantee"),
    (r"\b(kill|hurt|destroy) (you|your)\b", "contains a threat"),
    (r"\bwe will sue\b|\bi will sue\b", "threatens a lawsuit"),
]
FORBIDDEN_IN_EXPLANATIONS = [
    (r"\bnon[- ]?consensual\b", "declares the image non-consensual"),
    (r"\b(definitely|certainly|undoubtedly|proves?|proven|confirmed)\b", "claims certainty"),
    (r"\b(illegal|unlawful|crime|criminal|guilty)\b", "makes a legal judgement"),
    (r"\b(this|it) is (definitely |clearly )?your (image|photo)\b", "decides it is the user's image"),
]

SECTION_RE = re.compile(r"\b(?:section|sec\.|s\.)\s*(\d+[A-Z]*)", re.IGNORECASE)
RULE_RE = re.compile(r"\brule\s*(\d+\s*\(\s*\d+\s*\)(?:\s*\(\s*[a-z]\s*\))?)", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def _norm_rule(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def check_draft(text: str, *, allowed_sections: set[str], allowed_rules: set[str],
                min_len: int = 300, max_len: int = 6000,
                required_placeholders: tuple[str, ...] = PLACEHOLDERS_REQUIRED) -> list[str]:
    problems = []
    if not (min_len <= len(text) <= max_len):
        problems.append(f"length must be between {min_len} and {max_len} characters")
    for ph in required_placeholders:
        if ph not in text:
            problems.append(f"missing placeholder {ph}")
    for ph in set(PLACEHOLDER_RE.findall(text)) - PLACEHOLDERS_ALLOWED:
        problems.append(f"unknown placeholder {ph}")
    # No URLs or emails of its own: the only link allowed is {{URL}}.
    if re.search(r"https?://|www\.|\b[\w.+-]+@[\w-]+\.[\w.]+\b", text):
        problems.append("contains a link or email address; use {{URL}} only")
    cited_sections = {m.upper() for m in SECTION_RE.findall(text)}
    for sec in sorted(cited_sections - {s.upper() for s in allowed_sections}):
        problems.append(f"cites Section {sec}, which is not in the provided legal grounds")
    cited_rules = {_norm_rule(m) for m in RULE_RE.findall(text)}
    for rule in sorted(cited_rules - {_norm_rule(r) for r in allowed_rules}):
        problems.append(f"cites Rule {rule}, which is not in the provided legal grounds")
    lower = text.lower()
    for pattern, why in FORBIDDEN_IN_DRAFTS:
        if re.search(pattern, lower):
            problems.append(why)
    return problems


def check_explanation(text: str, max_len: int = 1200) -> list[str]:
    problems = []
    if not text.strip() or len(text) > max_len:
        problems.append(f"must be 1-{max_len} characters")
    lower = text.lower()
    for pattern, why in FORBIDDEN_IN_EXPLANATIONS:
        if re.search(pattern, lower):
            problems.append(why)
    return problems


def fill(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out
