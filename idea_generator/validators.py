"""
JSON schema validation for generated research ideas.
"""

import logging
from typing import List, Tuple

import jsonschema

logger = logging.getLogger(__name__)

# JSON schema that every finalized idea must satisfy.
IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "Name": {
            "type": "string",
            "minLength": 1,
            "description": "Short descriptor. Lowercase, no spaces, underscores allowed.",
        },
        "Title": {
            "type": "string",
            "minLength": 5,
            "description": "Catchy and informative title for the proposal.",
        },
        "Short Hypothesis": {
            "type": "string",
            "minLength": 10,
            "description": "Concise statement of the main hypothesis or research question.",
        },
        "Related Work": {
            "type": "string",
            "minLength": 10,
            "description": "Brief discussion of the most relevant related work.",
        },
        "Abstract": {
            "type": "string",
            "minLength": 50,
            "description": "Conference-format abstract (~250 words).",
        },
        "Experiments": {
            "description": "List of experiments or a description string.",
            "oneOf": [
                {"type": "string", "minLength": 20},
                {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object"},
                        ]
                    },
                    "minItems": 1,
                },
            ],
        },
        "Risk Factors and Limitations": {
            "description": "Potential risks and limitations.",
            "oneOf": [
                {"type": "string", "minLength": 10},
                {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            ],
        },
    },
    "required": [
        "Name",
        "Title",
        "Short Hypothesis",
        "Related Work",
        "Abstract",
        "Experiments",
        "Risk Factors and Limitations",
    ],
}


def validate_idea(idea: dict) -> Tuple[bool, List[str]]:
    """Validate an idea dict against the schema.

    Returns:
        (is_valid, list_of_error_messages)
    """
    validator = jsonschema.Draft7Validator(IDEA_SCHEMA)
    errors = sorted(validator.iter_errors(idea), key=lambda e: list(e.path))
    if not errors:
        return True, []
    messages = []
    for err in errors:
        path = " -> ".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
        messages.append(f"[{path}] {err.message}")
    return False, messages
