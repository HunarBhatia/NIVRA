"""Legal grounds for notices (India-first, D2).

Server-side source of truth for AI drafting; mirrors web/src/lib/notices.ts.
Each ground lists the sections/rules it cites so guardrails can reject any
law the model invents. PROTOTYPE TEXT: needs review by a lawyer (3.5).
"""

CATEGORY_LABEL = {
    "intimate": "Intimate image shared without consent",
    "morphed": "Morphed or AI-generated (deepfake) image",
    "impersonation": "Fake profile using my photos",
}

IT_RULES = {
    "id": "it_rules_3_2_b",
    "text": ("Rule 3(1)(b) and Rule 3(2)(b) of the Information Technology (Intermediary Guidelines "
             "and Digital Media Ethics Code) Rules, 2021: removal within 24 hours of a complaint "
             "about content that exposes a person's private area, shows them in full or partial "
             "nudity or a sexual act, or is impersonation, including artificially morphed images."),
    "sections": [],
    "rules": ["3(1)(b)", "3(2)(b)"],
}
BY_CATEGORY = {
    "intimate": {
        "id": "it_act_66e_67",
        "text": ("Section 66E of the Information Technology Act, 2000 (violation of privacy) and "
                 "Sections 67 and 67A (publishing obscene or sexually explicit material)."),
        "sections": ["66E", "67", "67A"], "rules": [],
    },
    "morphed": {
        "id": "it_act_66e_67_morphed",
        "text": ("Sections 66E, 67 and 67A of the Information Technology Act, 2000; the image was "
                 "altered or generated to depict the person without consent."),
        "sections": ["66E", "67", "67A"], "rules": [],
    },
    "impersonation": {
        "id": "it_act_66c_66d",
        "text": ("Section 66C (identity theft) and Section 66D (cheating by personation using a "
                 "computer resource) of the Information Technology Act, 2000."),
        "sections": ["66C", "66D"], "rules": [],
    },
}
COPYRIGHT = {
    "id": "copyright_self_taken",
    "text": "The person took the photograph themselves and owns its copyright; publication is unauthorised.",
    "sections": [], "rules": [],
}
PLATFORM_POLICY = {
    "id": "platform_policy",
    "text": "The platform's own community guidelines and terms of service.",
    "sections": [], "rules": [],
}


def grounds_for(category: str, self_taken: bool | None) -> list[dict]:
    grounds = [IT_RULES, BY_CATEGORY[category]]
    if self_taken:
        grounds.append(COPYRIGHT)
    grounds.append(PLATFORM_POLICY)
    return grounds


def allowed_citations(grounds: list[dict]) -> tuple[set[str], set[str]]:
    sections = {s for g in grounds for s in g["sections"]}
    rules = {r for g in grounds for r in g["rules"]}
    return sections, rules
