"""
OpenAI Structured Outputs – JSON schemas for response_format.

Use with get_response_from_llm(..., response_format=...) when the model
supports it (e.g. gpt-4o, gpt-4.1, gpt-4o-mini). Ensures the model returns
valid JSON that adheres to the schema.
See: https://developers.openai.com/api/docs/guides/structured-outputs/
"""

from typing import Any, Dict

# All nested objects must have "additionalProperties": false and explicit "required".

# ---------------------------------------------------------------------------
# Phase 2: Gaps and Hypotheses
# ---------------------------------------------------------------------------

GAP_HYPOTHESES_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "gap_hypotheses",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Short identifier e.g. gap_1"},
                            "description": {"type": "string", "description": "Description of the gap"},
                            "related_entries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Source names or indices from the review",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "Priority of this gap",
                            },
                        },
                        "required": ["id", "description", "related_entries", "priority"],
                        "additionalProperties": False,
                    },
                    "description": "List of research gaps",
                },
                "hypotheses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Lowercase with underscores"},
                            "short_hypothesis": {"type": "string", "description": "1-3 sentences"},
                            "linked_gap_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Ids of gaps this hypothesis addresses",
                            },
                            "rationale": {"type": "string", "description": "Why this is a good direction"},
                        },
                        "required": ["name", "short_hypothesis", "linked_gap_ids", "rationale"],
                        "additionalProperties": False,
                    },
                    "description": "Proposed hypotheses",
                },
            },
            "required": ["gaps", "hypotheses"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Feasibility selection
# ---------------------------------------------------------------------------

FEASIBILITY_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "feasibility_selection",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "chosen_hypothesis_name": {
                    "type": "string",
                    "description": "Exact 'name' field of the chosen hypothesis",
                },
                "rationale": {
                    "type": "string",
                    "description": "2-4 sentences why this hypothesis is most feasible",
                },
                "feasibility_scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hypothesis_name": {"type": "string"},
                            "score_1_to_5": {"type": "integer", "description": "1-5, 5 most feasible"},
                            "brief_reason": {"type": "string"},
                        },
                        "required": ["hypothesis_name", "score_1_to_5", "brief_reason"],
                        "additionalProperties": False,
                    },
                    "description": "Score for each hypothesis",
                },
            },
            "required": ["chosen_hypothesis_name", "rationale", "feasibility_scores"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Phase 4: Experiment plan
# ---------------------------------------------------------------------------

EXPERIMENT_PLAN_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "experiment_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "proposal_ref": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["name", "title"],
                    "additionalProperties": False,
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
                        "additionalProperties": False,
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
                        "required": ["name", "description", "source", "citation"],
                        "additionalProperties": False,
                    },
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
                        "required": ["name", "description", "size_or_source", "license_or_access"],
                        "additionalProperties": False,
                    },
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
                        "required": ["order", "step", "description", "deliverables"],
                        "additionalProperties": False,
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
                    "required": ["hardware", "min_data", "framework", "estimated_time"],
                    "additionalProperties": False,
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
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Critique (single persona review)
# ---------------------------------------------------------------------------

CRITIQUE_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "critique_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "2-3 sentence summary of the proposal"},
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of strengths",
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of weaknesses",
                },
                "score": {"type": "integer", "description": "Score 1-10"},
                "recommendation": {
                    "type": "string",
                    "description": "e.g. Accept / Weak Accept / Borderline / Reject or Go / Revise",
                },
                "detailed_review": {"type": "string", "description": "Optional longer feedback"},
            },
            "required": ["summary", "strengths", "weaknesses", "score", "recommendation", "detailed_review"],
            "additionalProperties": False,
        },
    },
}
