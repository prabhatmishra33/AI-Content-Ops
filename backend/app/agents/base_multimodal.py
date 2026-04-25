import json
import logging
import re
from typing import Any

import httpx
from google.genai import types

logger = logging.getLogger(__name__)

MAX_TOOL_TURNS = 5

GOOGLE_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

ENTITY_LOOKUP_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="lookup_entity_info",
            description=(
                "Fetch real-world background information about a named entity "
                "(person, place, organization, or event) from Wikipedia. "
                "Call this for any recognizable name or location you identify in the video."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "entity_name": {
                        "type": "STRING",
                        "description": "The full name of the entity (e.g. 'Narendra Modi', 'Gaza Strip')",
                    },
                    "entity_type": {
                        "type": "STRING",
                        "enum": ["person", "place", "organization", "event"],
                        "description": "The category of the entity",
                    },
                },
                "required": ["entity_name", "entity_type"],
            },
        )
    ]
)


def fetch_entity_info(entity_name: str, entity_type: str) -> dict:
    """Call Wikipedia REST API to get a summary for a named entity.
    Returns a dict with found=True/False and title/extract on success."""
    slug = entity_name.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    try:
        headers = {"User-Agent": "AI-Content-Ops/1.0 (contact@example.com)"}
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "found": True,
                "entity_name": entity_name,
                "entity_type": entity_type,
                "title": data.get("title", entity_name),
                "extract": data.get("extract", ""),
            }
    except Exception as exc:
        logger.warning(f"Wikipedia lookup failed for '{entity_name}': {exc}")
    return {"found": False, "entity_name": entity_name, "entity_type": entity_type}


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise ValueError("No JSON object found in model response")
        return json.loads(m.group(0))


def extract_grounding_metadata(response: Any) -> list[dict]:
    """Extract web sources from a Gemini response's grounding metadata."""
    sources = []
    try:
        candidate = response.candidates[0]
        grounding = getattr(candidate, "grounding_metadata", None)
        if not grounding:
            return sources
        for chunk in getattr(grounding, "grounding_chunks", []):
            web = getattr(chunk, "web", None)
            if web:
                sources.append({
                    "title": getattr(web, "title", ""),
                    "url": getattr(web, "uri", ""),
                })
    except Exception:
        pass
    return sources


def run_tool_loop(client: Any, model: str, contents: list, config: Any) -> tuple[str, Any]:
    """Run an agentic Gemini tool loop until no function_call parts remain.
    Returns (final_text, final_response). Raises RuntimeError if MAX_TOOL_TURNS exceeded.
    Google Search grounding happens transparently — no function_call parts are produced."""
    final_response = None
    for turn in range(MAX_TOOL_TURNS):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        final_response = response

        candidate_parts = response.candidates[0].content.parts
        function_calls = [p for p in candidate_parts if getattr(p, "function_call", None)]

        if not function_calls:
            return response.text, response

        # Append model's response turn, then tool result turn
        contents.append(response.candidates[0].content)
        tool_parts = []
        for part in function_calls:
            fc = part.function_call
            result = fetch_entity_info(
                entity_name=fc.args.get("entity_name", ""),
                entity_type=fc.args.get("entity_type", "person"),
            )
            logger.info(f"Entity lookup: {fc.args.get('entity_name')} -> found={result['found']}")
            tool_parts.append(
                types.Part.from_function_response(name=fc.name, response=result)
            )
        contents.append(types.Content(role="user", parts=tool_parts))

    raise RuntimeError(f"Tool loop exceeded {MAX_TOOL_TURNS} turns without a final response")
