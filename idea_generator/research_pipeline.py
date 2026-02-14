"""
Research pipeline: 4-phase flow (Literature Review -> Gap/Hypotheses -> Direction -> Experiment Plan).
"""

import json
import logging
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import _parse_action_arguments, _safe_parse_json
from .llm import create_client, get_response_from_llm
from .prompts import (
    DIRECTION_INITIAL_PROMPT,
    DIRECTION_REFLECTION_PROMPT,
    EXPERIMENT_PLAN_PROMPT,
    FINALIZE_DIRECTION_TOOL,
    FINALIZE_LITERATURE_REVIEW_TOOL,
    GAP_HYPOTHESES_PROMPT,
    LITERATURE_REVIEW_INITIAL_PROMPT,
    LITERATURE_REVIEW_REFLECTION_PROMPT,
    build_tool_descriptions,
    build_tool_names,
    get_direction_system_prompt,
    get_literature_review_system_prompt,
)
from .tools.base import BaseTool
from .tools.semantic_scholar import SemanticScholarSearchTool
from .tools.arxiv import ArxivSearchTool
from .tools.pubmed import PubMedSearchTool
from .tools.openalex import OpenAlexSearchTool
from .validators import (
    validate_idea,
    validate_literature_review,
    validate_experiment_plan,
)

logger = logging.getLogger(__name__)


def _tools_for_config(arxiv_enabled: bool, pubmed_enabled: bool, openalex_enabled: bool) -> List[Any]:
    """Build list of search tools + given finalize tool (caller adds finalize)."""
    tools: List[Any] = [SemanticScholarSearchTool()]
    if arxiv_enabled:
        tools.append(ArxivSearchTool())
    if pubmed_enabled:
        tools.append(PubMedSearchTool())
    if openalex_enabled:
        tools.append(OpenAlexSearchTool())
    return tools


def run_literature_review(
    topic_path: str,
    config: Any,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase 1: From topic file, run agent loop to produce structured literature review."""
    topic_path = str(Path(topic_path).resolve())
    if output_path is None:
        base = Path(topic_path).stem
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / f"{base}.lit_review.json")
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(topic_path, "r", encoding="utf-8") as f:
        topic_content = f.read()
    logger.info("Phase 1: Literature review for %s", topic_path)

    client, client_model = create_client(config.model)
    tools = _tools_for_config(
        getattr(config, "arxiv_enabled", True),
        getattr(config, "pubmed_enabled", False),
        getattr(config, "openalex_enabled", False),
    )
    tools.append(FINALIZE_LITERATURE_REVIEW_TOOL)
    tools_dict: Dict[str, BaseTool] = {t.name: t for t in tools if isinstance(t, BaseTool)}
    tool_descriptions = build_tool_descriptions(tools)
    tool_names_str = build_tool_names(tools)
    system_prompt = get_literature_review_system_prompt(tool_descriptions, tool_names_str)

    num_reflections = getattr(config, "pipeline_literature_reflections", 8)
    last_tool_results = ""
    msg_history: List[Dict[str, Any]] = []
    parse_retried = False

    for reflection_round in range(num_reflections):
        if reflection_round == 0:
            prompt_text = LITERATURE_REVIEW_INITIAL_PROMPT.format(topic_content=topic_content)
        else:
            prompt_text = LITERATURE_REVIEW_REFLECTION_PROMPT.format(
                current_round=reflection_round + 1,
                num_reflections=num_reflections,
                last_tool_results=last_tool_results or "No new results.",
            )

        response_text, msg_history = get_response_from_llm(
            prompt=prompt_text,
            client=client,
            model=client_model,
            system_message=system_prompt,
            msg_history=msg_history,
        )

        try:
            action, arguments_text = _parse_action_arguments(response_text)
            logger.info("Phase 1 round %d – action=%s", reflection_round + 1, action)

            if action in tools_dict:
                tool = tools_dict[action]
                arguments_json = _safe_parse_json(arguments_text)
                try:
                    result = tool.use_tool(**arguments_json)
                    last_tool_results = result or "No results."
                except Exception as e:
                    last_tool_results = f"Error using tool {action}: {e}"

            elif action == "FinalizeLiteratureReview":
                arguments_json = _safe_parse_json(arguments_text)
                literature_review = arguments_json.get("literature_review")
                if not literature_review:
                    raise ValueError("Missing 'literature_review' key in FinalizeLiteratureReview arguments.")

                if getattr(config, "validate", True):
                    is_valid, errors = validate_literature_review(literature_review)
                    if not is_valid:
                        logger.warning("Literature review validation failed: %s", errors)
                        last_tool_results = (
                            "The literature review has validation errors:\n" + "\n".join(errors) + "\nPlease fix and call FinalizeLiteratureReview again."
                        )
                        continue

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(literature_review, f, indent=2, ensure_ascii=False)
                logger.info("Phase 1 complete: saved to %s", output_path)
                return literature_review

            else:
                logger.warning("Unknown action '%s'. Available: %s", action, tool_names_str)

        except Exception:
            logger.error("Failed to parse LLM response:\n%s", traceback.format_exc())
            if not parse_retried:
                parse_retried = True
                last_tool_results = (
                    "Your previous response could not be parsed. You must reply with ACTION: and ARGUMENTS: (action name and JSON). Try again."
                )
            else:
                break

    raise RuntimeError("Phase 1 did not finalize literature review within reflection limit.")


def run_gap_hypotheses(
    lit_review_path: str,
    config: Any,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase 2: From lit_review.json, produce gaps and hypotheses (single LLM call)."""
    lit_review_path = str(Path(lit_review_path).resolve())
    with open(lit_review_path, "r", encoding="utf-8") as f:
        lit_review = json.load(f)

    if output_path is None:
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / (Path(lit_review_path).stem.replace(".lit_review", "") + ".hypotheses.json"))
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info("Phase 2: Gap and hypotheses from %s", lit_review_path)
    client, client_model = create_client(config.model)
    max_hypotheses = getattr(config, "pipeline_max_hypotheses", 10)
    max_hypotheses = max(5, min(max_hypotheses, 20))

    lit_review_json_str = json.dumps(lit_review, indent=2, ensure_ascii=False)
    prompt_text = GAP_HYPOTHESES_PROMPT.format(
        lit_review_json=lit_review_json_str,
        max_hypotheses=max_hypotheses,
    )
    system_message = "You are a research advisor. Output only a valid JSON object with keys 'gaps' and 'hypotheses', no other text or markdown."

    response_text, _ = get_response_from_llm(
        prompt=prompt_text,
        client=client,
        model=client_model,
        system_message=system_message,
        msg_history=[],
        temperature=0.7,
    )

    data = _extract_json_object(response_text)
    if not data or "gaps" not in data or "hypotheses" not in data:
        raise RuntimeError("Phase 2 LLM did not return valid JSON with 'gaps' and 'hypotheses'.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Phase 2 complete: saved to %s", output_path)
    return data


def run_direction(
    lit_review_path: str,
    hypotheses_path: str,
    config: Any,
    output_path: Optional[str] = None,
    chosen_hypothesis_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase 3: From lit review + hypotheses, choose direction and produce detailed proposal."""
    lit_review_path = str(Path(lit_review_path).resolve())
    hypotheses_path = str(Path(hypotheses_path).resolve())
    with open(lit_review_path, "r", encoding="utf-8") as f:
        lit_review = json.load(f)
    with open(hypotheses_path, "r", encoding="utf-8") as f:
        hypotheses_data = json.load(f)

    if output_path is None:
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / (Path(hypotheses_path).stem.replace(".hypotheses", "") + ".direction.json"))
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info("Phase 3: Direction from %s + %s", lit_review_path, hypotheses_path)
    client, client_model = create_client(config.model)
    tools = _tools_for_config(
        getattr(config, "arxiv_enabled", True),
        getattr(config, "pubmed_enabled", False),
        getattr(config, "openalex_enabled", False),
    )
    tools.append(FINALIZE_DIRECTION_TOOL)
    tools_dict = {t.name: t for t in tools if isinstance(t, BaseTool)}
    tool_descriptions = build_tool_descriptions(tools)
    tool_names_str = build_tool_names(tools)
    system_prompt = get_direction_system_prompt(tool_descriptions, tool_names_str)

    lit_review_synthesis = lit_review.get("synthesis", "") or json.dumps(lit_review.get("entries", [])[:3])
    hypotheses_list = "\n".join(
        f"- {h.get('name', '?')}: {h.get('short_hypothesis', '')}"
        for h in hypotheses_data.get("hypotheses", [])
    )
    if chosen_hypothesis_id:
        hypotheses_list += f"\n(Preferred: {chosen_hypothesis_id})"

    num_reflections = getattr(config, "pipeline_direction_reflections", 5)
    last_tool_results = ""
    msg_history = []
    parse_retried = False

    for reflection_round in range(num_reflections):
        if reflection_round == 0:
            prompt_text = DIRECTION_INITIAL_PROMPT.format(
                lit_review_synthesis=lit_review_synthesis,
                hypotheses_list=hypotheses_list,
            )
        else:
            prompt_text = DIRECTION_REFLECTION_PROMPT.format(
                current_round=reflection_round + 1,
                num_reflections=num_reflections,
                last_tool_results=last_tool_results or "No new results.",
            )

        response_text, msg_history = get_response_from_llm(
            prompt=prompt_text,
            client=client,
            model=client_model,
            system_message=system_prompt,
            msg_history=msg_history,
        )

        try:
            action, arguments_text = _parse_action_arguments(response_text)
            logger.info("Phase 3 round %d – action=%s", reflection_round + 1, action)

            if action in tools_dict:
                tool = tools_dict[action]
                arguments_json = _safe_parse_json(arguments_text)
                try:
                    result = tool.use_tool(**arguments_json)
                    last_tool_results = result or "No results."
                except Exception as e:
                    last_tool_results = f"Error using tool {action}: {e}"

            elif action == "FinalizeDirection":
                arguments_json = _safe_parse_json(arguments_text)
                direction = arguments_json.get("direction")
                if not direction:
                    raise ValueError("Missing 'direction' key in FinalizeDirection arguments.")

                if getattr(config, "validate", True):
                    is_valid, errors = validate_idea(direction)
                    if not is_valid:
                        logger.warning("Direction validation failed: %s", errors)
                        last_tool_results = (
                            "The direction (idea) has validation errors:\n" + "\n".join(errors) + "\nPlease fix and call FinalizeDirection again."
                        )
                        continue

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(direction, f, indent=2, ensure_ascii=False)
                logger.info("Phase 3 complete: saved to %s", output_path)
                return direction

            else:
                logger.warning("Unknown action '%s'. Available: %s", action, tool_names_str)

        except Exception:
            logger.error("Failed to parse LLM response:\n%s", traceback.format_exc())
            if not parse_retried:
                parse_retried = True
                last_tool_results = "Your response could not be parsed. Reply with ACTION: and ARGUMENTS:. Try again."
            else:
                break

    raise RuntimeError("Phase 3 did not finalize direction within reflection limit.")


def run_experiment_plan(
    direction_path: str,
    config: Any,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase 4: From direction.json, produce structured experiment plan."""
    direction_path = str(Path(direction_path).resolve())
    with open(direction_path, "r", encoding="utf-8") as f:
        direction = json.load(f)

    if output_path is None:
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / (Path(direction_path).stem.replace(".direction", "") + ".experiment_plan.json"))
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info("Phase 4: Experiment plan from %s", direction_path)
    client, client_model = create_client(config.model)
    direction_json_str = json.dumps(direction, indent=2, ensure_ascii=False)
    prompt_text = EXPERIMENT_PLAN_PROMPT.format(direction_json=direction_json_str)
    system_message = "You are a research methodologist. Output only a valid JSON object with the exact structure requested (proposal_ref, metrics, baselines, datasets, implementation_steps, min_config). No markdown, no explanation."

    response_text, _ = get_response_from_llm(
        prompt=prompt_text,
        client=client,
        model=client_model,
        system_message=system_message,
        msg_history=[],
        temperature=0.5,
    )

    data = _extract_json_object(response_text)
    if not data:
        raise RuntimeError("Phase 4 LLM did not return valid JSON.")

    if getattr(config, "validate", True):
        is_valid, errors = validate_experiment_plan(data)
        if not is_valid:
            logger.warning("Experiment plan validation failed: %s", errors)
            for e in errors:
                logger.warning("  %s", e)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Phase 4 complete: saved to %s", output_path)
    return data


def run_full_research_pipeline(
    topic_path: str,
    config: Any,
    output_dir: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Run all 4 phases in sequence. Returns paths to generated artifacts."""
    topic_path = str(Path(topic_path).resolve())
    base = Path(topic_path).stem
    out_dir = output_dir or getattr(config, "output_dir", "output")
    out_dir = str(Path(out_dir).resolve())
    os.makedirs(out_dir, exist_ok=True)

    paths: Dict[str, List[str]] = {"literature_review": [], "hypotheses": [], "direction": [], "experiment_plan": []}

    lit_path = str(Path(out_dir) / f"{base}.lit_review.json")
    paths["literature_review"].append(lit_path)
    run_literature_review(topic_path, config, lit_path)

    hyp_path = str(Path(out_dir) / f"{base}.hypotheses.json")
    paths["hypotheses"].append(hyp_path)
    run_gap_hypotheses(lit_path, config, hyp_path)

    dir_path = str(Path(out_dir) / f"{base}.direction.json")
    paths["direction"].append(dir_path)
    run_direction(lit_path, hyp_path, config, dir_path)

    exp_path = str(Path(out_dir) / f"{base}.experiment_plan.json")
    paths["experiment_plan"].append(exp_path)
    run_experiment_plan(dir_path, config, exp_path)

    return paths


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract first JSON object from LLM output (handles ```json fences and raw object)."""
    text = text.strip()
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass
    return None
