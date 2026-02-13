"""
Optional novelty scoring for generated ideas.
Uses an LLM to rate how novel the idea is (0.0 – 1.0).
"""

import json
import logging
import re
from typing import Any

from .llm import get_response_from_llm

logger = logging.getLogger(__name__)

NOVELTY_SYSTEM_PROMPT = """You are an expert scientific reviewer specializing in assessing the novelty of research proposals.
Given a research idea, evaluate its novelty on a scale from 0.0 to 1.0 where:
  0.0 = completely derivative, already well-explored in the literature
  0.5 = moderately novel, has some new angles but builds heavily on existing work
  1.0 = highly novel, proposes a genuinely new direction or insight

Respond ONLY with a JSON object in this exact format:
```json
{"score": <float>, "reasoning": "<one-paragraph explanation>"}
```
"""

NOVELTY_USER_PROMPT = """Please evaluate the novelty of the following research idea:

Title: {title}

Short Hypothesis: {hypothesis}

Abstract: {abstract}

Related Work: {related_work}
"""


def score_novelty(idea: dict, client: Any, model: str) -> float:
    """Score the novelty of an idea using an LLM.

    Args:
        idea: The idea dict (must contain Title, Abstract, etc.).
        client: The LLM client object.
        model: The model identifier string.

    Returns:
        A float between 0.0 and 1.0.
    """
    prompt = NOVELTY_USER_PROMPT.format(
        title=idea.get("Title", ""),
        hypothesis=idea.get("Short Hypothesis", ""),
        abstract=idea.get("Abstract", ""),
        related_work=idea.get("Related Work", ""),
    )

    try:
        response_text, _ = get_response_from_llm(
            prompt=prompt,
            client=client,
            model=model,
            system_message=NOVELTY_SYSTEM_PROMPT,
            temperature=0.3,
        )

        # Extract JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            # Try direct parse
            brace = re.search(r"\{.*\}", response_text, re.DOTALL)
            if brace:
                data = json.loads(brace.group(0))
            else:
                logger.warning("Could not parse novelty response, defaulting to 0.5")
                return 0.5

        score = float(data.get("score", 0.5))
        reasoning = data.get("reasoning", "")
        logger.info("Novelty score=%.2f  reasoning=%s", score, reasoning[:120])
        return max(0.0, min(1.0, score))

    except Exception as e:
        logger.error("Novelty scoring failed: %s", e)
        return 0.5
