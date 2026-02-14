"""
Hypothesis expansion: from a topic or an existing idea, generate a list of
sub-hypotheses or theory variants that can be researched independently.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .llm import create_client, get_response_from_llm
from .prompts import (
    HYPOTHESIS_EXPANSION_FROM_IDEA,
    HYPOTHESIS_EXPANSION_FROM_TOPIC,
)

logger = logging.getLogger(__name__)


def expand_hypotheses(
    topic_text: Optional[str] = None,
    idea_dict: Optional[Dict[str, Any]] = None,
    client: Any = None,
    model: str = "",
    max_sub: int = 10,
) -> List[Dict[str, Any]]:
    """Generate sub-hypotheses or theory variants from a topic or an idea.

    Exactly one of topic_text or idea_dict must be provided.
    If client/model are not provided, they are created from the default config
    (requires OPENAI_API_KEY or similar).

    Args:
        topic_text: Full topic description (e.g. content of a topic .md file).
        idea_dict: A single idea object with at least "Title" and "Short Hypothesis".
        client: LLM client (if None, created from model).
        model: Model name (used if client is None to create client).
        max_sub: Maximum number of sub-hypotheses to request (cap 5–max_sub).

    Returns:
        List of dicts with at least "Name" and "Short Hypothesis".
    """
    if (topic_text is None) == (idea_dict is None):
        raise ValueError("Exactly one of topic_text or idea_dict must be provided.")

    if model and client is None:
        client, model = create_client(model)
    if client is None:
        raise ValueError("Either provide client+model or a valid model name to create a client.")

    max_sub = max(5, min(max_sub, 20))

    if topic_text is not None:
        prompt = HYPOTHESIS_EXPANSION_FROM_TOPIC.format(
            topic_text=topic_text.strip(),
            max_sub=max_sub,
        )
        system_message = "You are a research advisor. Output only a valid JSON array, no other text."
    else:
        title = idea_dict.get("Title", "")
        short_hyp = idea_dict.get("Short Hypothesis", "")
        prompt = HYPOTHESIS_EXPANSION_FROM_IDEA.format(
            title=title,
            short_hypothesis=short_hyp,
            max_sub=max_sub,
        )
        system_message = "You are a research advisor. Output only a valid JSON array, no other text."

    response_text, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=model,
        system_message=system_message,
        msg_history=[],
        temperature=0.7,
    )

    return _parse_expansion_response(response_text)


def _parse_expansion_response(response_text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from the LLM response."""
    text = response_text.strip()

    # Strip ```json ... ``` if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_match:
        text = json_match.group(1).strip()

    # Find the first [ ... ] array
    start = text.find("[")
    if start == -1:
        logger.warning("No JSON array found in expansion response")
        return []
    depth = 0
    end = -1
    for i, c in enumerate(text[start:], start=start):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        logger.warning("Unclosed JSON array in expansion response")
        return []

    try:
        arr = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse expansion JSON: %s", e)
        return []

    if not isinstance(arr, list):
        return []

    result = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        name = item.get("Name") or item.get("name")
        hyp = item.get("Short Hypothesis") or item.get("short_hypothesis") or item.get("hypothesis")
        if name and hyp:
            result.append({
                "Name": name if isinstance(name, str) else str(name),
                "Short Hypothesis": hyp if isinstance(hyp, str) else str(hyp),
            })
    return result
