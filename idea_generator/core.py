"""
Core idea-generation logic.
Orchestrates the LLM conversation loop with tool calls, validation, novelty scoring,
and checkpoint/resume support.
"""

import json
import logging
import os
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm import create_client, get_response_from_llm
from .prompts import (
    FINALIZE_IDEA_TOOL,
    IDEA_GENERATION_PROMPT,
    IDEA_REFLECTION_PROMPT,
    VALIDATION_FIX_PROMPT,
    build_tool_descriptions,
    build_tool_names,
    get_system_prompt,
)
from .tools.base import BaseTool
from .tools.semantic_scholar import SemanticScholarSearchTool
from .tools.arxiv import ArxivSearchTool
from .tools.pubmed import PubMedSearchTool
from .tools.openalex import OpenAlexSearchTool
from .validators import validate_idea
from .utils.checkpoint import load_checkpoint, save_checkpoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration data-class
# ---------------------------------------------------------------------------

@dataclass
class IdeaGeneratorConfig:
    """Runtime configuration for the idea generator."""

    model: str = "gpt-4o-2024-05-13"
    max_generations: int = 20
    num_reflections: int = 5
    output_dir: str = "output"
    validate: bool = True
    novelty_scoring: bool = False
    novelty_model: str = ""  # defaults to same as model if empty
    checkpoint_interval: int = 1
    arxiv_enabled: bool = True
    pubmed_enabled: bool = False
    openalex_enabled: bool = False
    resume: bool = False
    # Allow overriding the system prompt entirely (empty = use default)
    system_prompt_override: str = ""
    # Research pipeline (4-phase) settings
    pipeline_mode: bool = False
    pipeline_literature_reflections: int = 8
    pipeline_direction_reflections: int = 5
    pipeline_max_hypotheses: int = 10


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_ideas(
    topic_path: str,
    config: IdeaGeneratorConfig,
    output_path: Optional[str] = None,
) -> List[Dict]:
    """Generate research ideas from a topic description file.

    Args:
        topic_path: Path to a Markdown file describing the research topic.
        config: An IdeaGeneratorConfig instance.
        output_path: Where to write the JSON output. If None, derived from topic_path.

    Returns:
        List of idea dicts.
    """

    # --- resolve paths ---
    topic_path = str(Path(topic_path).resolve())
    if output_path is None:
        output_path = topic_path.rsplit(".", 1)[0] + ".json"
    output_path = str(Path(output_path).resolve())

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # --- read topic ---
    with open(topic_path, "r", encoding="utf-8") as f:
        workshop_description = f.read()
    logger.info("Loaded topic from %s (%d chars)", topic_path, len(workshop_description))

    # --- setup LLM client ---
    client, client_model = create_client(config.model)
    logger.info("LLM client ready: model=%s", client_model)

    # --- setup tools ---
    tools: list = [SemanticScholarSearchTool()]
    if config.arxiv_enabled:
        tools.append(ArxivSearchTool())
    if config.pubmed_enabled:
        tools.append(PubMedSearchTool())
    if config.openalex_enabled:
        tools.append(OpenAlexSearchTool())
    tools.append(FINALIZE_IDEA_TOOL)

    tools_dict: Dict[str, BaseTool] = {
        t.name: t for t in tools if isinstance(t, BaseTool)
    }
    tool_descriptions = build_tool_descriptions(tools)
    tool_names_str = build_tool_names(tools)

    # --- system prompt ---
    if config.system_prompt_override:
        system_prompt = config.system_prompt_override
    else:
        system_prompt = get_system_prompt(tool_descriptions, tool_names_str)

    # --- checkpoint / resume ---
    idea_str_archive: List[str] = []
    start_gen_idx = 0

    if config.resume:
        cp = load_checkpoint(output_path)
        if cp is not None:
            idea_str_archive = [json.dumps(idea) for idea in cp["ideas"]]
            start_gen_idx = cp["gen_idx"]
            logger.info("Resumed from checkpoint: %d ideas, gen_idx=%d", len(idea_str_archive), start_gen_idx)
    else:
        # Load existing ideas file if present (same behaviour as original)
        if os.path.exists(output_path):
            with open(output_path, "r") as f:
                existing = json.load(f)
            idea_str_archive = [json.dumps(idea) for idea in existing]
            logger.info("Loaded %d existing ideas from %s", len(idea_str_archive), output_path)

    # --- novelty scoring setup ---
    novelty_client = None
    novelty_model = None
    if config.novelty_scoring:
        from .novelty import score_novelty  # lazy import
        nm = config.novelty_model or config.model
        novelty_client, novelty_model = create_client(nm)

    # --- generation loop ---
    for gen_idx in range(start_gen_idx, config.max_generations):
        logger.info("=== Generating idea %d / %d ===", gen_idx + 1, config.max_generations)

        try:
            prev_ideas_string = "\n\n".join(idea_str_archive)
            last_tool_results = ""
            idea_finalized = False
            msg_history: list = []
            parse_retried_for_idea = False

            for reflection_round in range(config.num_reflections):
                # Build prompt
                if reflection_round == 0:
                    prompt_text = IDEA_GENERATION_PROMPT.format(
                        workshop_description=workshop_description,
                        prev_ideas_string=prev_ideas_string,
                    )
                else:
                    prompt_text = IDEA_REFLECTION_PROMPT.format(
                        current_round=reflection_round + 1,
                        num_reflections=config.num_reflections,
                        last_tool_results=last_tool_results or "No new results.",
                    )

                response_text, msg_history = get_response_from_llm(
                    prompt=prompt_text,
                    client=client,
                    model=client_model,
                    system_message=system_prompt,
                    msg_history=msg_history,
                )

                # Parse ACTION / ARGUMENTS (with optional one-time retry on format failure)
                try:
                    action, arguments_text = _parse_action_arguments(response_text)
                    logger.info("Round %d – action=%s", reflection_round + 1, action)

                    if action in tools_dict:
                        # It's a search tool
                        tool = tools_dict[action]
                        arguments_json = _safe_parse_json(arguments_text)
                        try:
                            result = tool.use_tool(**arguments_json)
                            last_tool_results = result or "No results."
                        except Exception as e:
                            last_tool_results = f"Error using tool {action}: {e}"

                    elif action == "FinalizeIdea":
                        arguments_json = _safe_parse_json(arguments_text)
                        idea = arguments_json.get("idea")
                        if not idea:
                            raise ValueError("Missing 'idea' key in FinalizeIdea arguments.")

                        # Validation
                        if config.validate:
                            is_valid, errors = validate_idea(idea)
                            if not is_valid:
                                logger.warning("Idea validation failed: %s", errors)
                                # Give the LLM a chance to fix
                                last_tool_results = VALIDATION_FIX_PROMPT.format(
                                    errors="\n".join(errors)
                                )
                                continue  # next reflection round

                        # Novelty scoring (optional)
                        if config.novelty_scoring and novelty_client is not None:
                            from .novelty import score_novelty
                            ns = score_novelty(idea, novelty_client, novelty_model)
                            idea["novelty_score"] = ns
                            logger.info("Novelty score: %.2f", ns)

                        idea_str_archive.append(json.dumps(idea))
                        idea_finalized = True
                        logger.info("Idea finalized: %s", idea.get("Name", idea.get("Title", "?")))
                        break
                    else:
                        logger.warning("Unknown action '%s'. Available: %s", action, tool_names_str)

                except Exception:
                    logger.error("Failed to parse LLM response:\n%s", traceback.format_exc())
                    raw_preview = response_text[-2000:] if len(response_text) > 2000 else response_text
                    logger.error("Raw LLM response (preview):\n%s", raw_preview)
                    if not parse_retried_for_idea:
                        parse_retried_for_idea = True
                        last_tool_results = (
                            "Your previous response could not be parsed. You must reply with exactly "
                            "the lines 'ACTION:' and 'ARGUMENTS:' (with the action name and JSON arguments). Try again."
                        )
                        continue
                    break

            if not idea_finalized:
                logger.warning("Idea %d was NOT finalized after %d reflection rounds.", gen_idx + 1, config.num_reflections)

            # Checkpoint
            if (gen_idx + 1) % config.checkpoint_interval == 0:
                ideas_so_far = [json.loads(s) for s in idea_str_archive]
                save_checkpoint(output_path, ideas_so_far, gen_idx + 1)

        except Exception:
            logger.error("Failed to generate idea %d:\n%s", gen_idx + 1, traceback.format_exc())
            continue

    # --- save final output ---
    ideas = [json.loads(s) for s in idea_str_archive]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ideas, f, indent=4, ensure_ascii=False)
    logger.info("Saved %d ideas to %s", len(ideas), output_path)

    # Clean up checkpoint after successful completion
    cp_path = output_path + ".checkpoint.json"
    if os.path.exists(cp_path):
        os.remove(cp_path)
        logger.info("Removed checkpoint file %s", cp_path)

    return ideas


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_action_arguments(response_text: str) -> tuple[str, str]:
    """Extract ACTION and ARGUMENTS from the LLM response. Tries multiple patterns for robustness."""
    # Normalize: strip and treat common markdown/whitespace
    text = response_text.strip()

    # Try several action patterns (strict first, then relaxed)
    action_patterns = [
        r"ACTION:\s*(.*?)\s*(?:ARGUMENTS:|$)",
        r"\*\*ACTION:\*\*\s*(.*?)\s*(?:\*\*ARGUMENTS:\*\*|ARGUMENTS:|$)",
        r"\"ACTION\":\s*\"(.*?)\"",
        r"(?:^|\n)\s*ACTION\s*:\s*(.+?)(?=\n\s*ARGUMENTS|\n\s*\*\*ARGUMENTS|$)",
    ]
    action_match = None
    for pat in action_patterns:
        action_match = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if action_match:
            break
    # Fallback: line that starts with ACTION (case-insensitive)
    if not action_match:
        for line in text.splitlines():
            if re.match(r"^\s*ACTION\s*:\s*", line, re.IGNORECASE):
                action_match = re.match(r"^\s*ACTION\s*:\s*(.+)", line, re.IGNORECASE)
                break

    if not action_match:
        raise ValueError("Could not find ACTION in response.")

    action = action_match.group(1).strip().strip('"').strip("'").strip()

    # Arguments: same idea, multiple patterns
    arguments_patterns = [
        r"ARGUMENTS:\s*(.*?)(?:$|\n\s*THOUGHT:|\n\s*$)",
        r"\*\*ARGUMENTS:\*\*\s*(.*?)(?:$|\n)",
    ]
    arguments_text = ""
    for pat in arguments_patterns:
        arguments_match = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if arguments_match:
            arguments_text = arguments_match.group(1).strip()
            break

    # Unwrap ```json blocks
    json_block = re.search(r"```json\s*(.*?)\s*```", arguments_text, re.DOTALL)
    if json_block:
        arguments_text = json_block.group(1)

    return action, arguments_text


def _safe_parse_json(text: str) -> dict:
    """Try to parse JSON, stripping markdown fences if needed."""
    text = text.strip()
    # Remove ```json ... ``` wrapper if still present
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the outermost { ... }
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))
        raise
