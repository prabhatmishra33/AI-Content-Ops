PROMPTS = {
    "moderation": {
        "version": "v1",
        "system": "You are a video safety moderation model. Return strict JSON only.",
        "user_template": (
            "Classify safety flags for filename/context: {filename}. "
            "Return JSON: {{\"flags\": {{\"violence\": bool, \"abuse\": bool, \"adult\": bool}}, "
            "\"severity\": \"LOW|MEDIUM|HIGH\", \"confidence\": 0.0-1.0}}"
        ),
    },
    "classification": {
        "version": "v1",
        "system": "You classify enterprise video content taxonomy. Return JSON only.",
        "user_template": (
            "Classify content for filename/context: {filename}. "
            "Return JSON: {{\"primary_category\": str, \"tags\": [str], \"confidence\": 0.0-1.0}}"
        ),
    },
    "impact_scoring": {
        "version": "v1",
        "system": "You score impact urgency from 0.0 to 1.0. Return JSON only.",
        "user_template": (
            "Given moderation={moderation} and classification={classification}, "
            "return JSON: {{\"impact_score\": 0.0-1.0, \"reason\": str, \"confidence\": 0.0-1.0}}"
        ),
    },
    "compliance": {
        "version": "v1",
        "system": "You are a governance checker for brand/legal compliance. Return JSON only.",
        "user_template": (
            "Given moderation={moderation} classification={classification}, return JSON: "
            "{{\"status\": \"PASS|PASS_WITH_WARNINGS|FAIL\", \"violations\": [str], "
            "\"required_disclaimer\": str, \"confidence\": 0.0-1.0}}"
        ),
    },
    "content_creation": {
        "version": "v1",
        "system": "You generate concise enterprise content assets. Return JSON only.",
        "user_template": (
            "Create title, summary, caption for filename={filename}, tags={tags}, score={score}. "
            "Return JSON: {{\"title\": str, \"summary\": str, \"caption\": str, \"confidence\": 0.0-1.0}}"
        ),
    },
    "localization": {
        "version": "v1",
        "system": "You localize content preserving tone and meaning. Return JSON only.",
        "user_template": (
            "Localize content={content} to locale={locale}. Return JSON: "
            "{{\"locale\": str, \"title\": str, \"summary\": str, \"caption\": str, \"confidence\": 0.0-1.0}}"
        ),
    },
    "reporter": {
        "version": "v1",
        "system": "You produce concise moderation lifecycle reports.",
        "user_template": (
            "Create a report summary for payload={payload}. Return plain text under 250 words."
        ),
    },
}


def get_prompt(name: str) -> dict:
    return PROMPTS[name]

