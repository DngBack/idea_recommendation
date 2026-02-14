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
        "References": {
            "type": "array",
            "description": "Structured citations: each source cited in Related Work must have an entry here.",
            "items": {
                "type": "object",
                "properties": {
                    "author": {"type": "string"},
                    "year": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "doi": {"type": "string"},
                },
                "required": ["author", "year", "title"],
            },
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


# ---------------------------------------------------------------------------
# Literature Review (Phase 1) schema
# ---------------------------------------------------------------------------

LITERATURE_REVIEW_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "minLength": 1},
        "citation": {
            "type": "object",
            "properties": {
                "author": {"type": "string"},
                "year": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
                "title": {"type": "string"},
                "url": {"type": "string"},
                "doi": {"type": "string"},
            },
            "required": ["author", "year", "title"],
        },
        "approach_summary": {"type": "string", "minLength": 1},
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
        },
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
        },
        "research_gaps": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
        },
    },
    "required": ["source", "citation", "approach_summary", "strengths", "weaknesses", "research_gaps"],
}

LITERATURE_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "topic_summary": {"type": "string", "minLength": 1},
        "entries": {
            "type": "array",
            "items": LITERATURE_REVIEW_ENTRY_SCHEMA,
            "minItems": 1,
        },
        "synthesis": {"type": "string", "minLength": 1},
    },
    "required": ["topic_summary", "entries", "synthesis"],
}


def validate_literature_review(data: dict) -> Tuple[bool, List[str]]:
    """Validate a literature review dict against the schema.

    Returns:
        (is_valid, list_of_error_messages)
    """
    validator = jsonschema.Draft7Validator(LITERATURE_REVIEW_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return True, []
    messages = []
    for err in errors:
        path = " -> ".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
        messages.append(f"[{path}] {err.message}")
    return False, messages


# ---------------------------------------------------------------------------
# Experiment Plan (Phase 4) schema
# ---------------------------------------------------------------------------

EXPERIMENT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "proposal_ref": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["name", "title"],
        },
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "primary": {"type": "boolean"},
                },
                "required": ["name", "description", "primary"],
            },
            "minItems": 1,
        },
        "baselines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "source": {"type": "string"},
                    "citation": {"type": "string"},
                },
                "required": ["name", "description"],
            },
            "minItems": 0,
        },
        "datasets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "size_or_source": {"type": "string"},
                    "license_or_access": {"type": "string"},
                },
                "required": ["name", "description"],
            },
            "minItems": 0,
        },
        "implementation_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "step": {"type": "string"},
                    "description": {"type": "string"},
                    "deliverables": {"type": "string"},
                },
                "required": ["order", "step", "description"],
            },
            "minItems": 1,
        },
        "min_config": {
            "type": "object",
            "properties": {
                "hardware": {"type": "string"},
                "min_data": {"type": "string"},
                "framework": {"type": "string"},
                "estimated_time": {"type": "string"},
            },
        },
    },
    "required": [
        "proposal_ref",
        "metrics",
        "baselines",
        "datasets",
        "implementation_steps",
        "min_config",
    ],
}


def validate_experiment_plan(data: dict) -> Tuple[bool, List[str]]:
    """Validate an experiment plan dict against the schema.

    Returns:
        (is_valid, list_of_error_messages)
    """
    validator = jsonschema.Draft7Validator(EXPERIMENT_PLAN_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return True, []
    messages = []
    for err in errors:
        path = " -> ".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
        messages.append(f"[{path}] {err.message}")
    return False, messages
