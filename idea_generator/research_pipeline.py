"""
Research pipeline: Literature Review -> Hypotheses -> Feasibility Selection -> Direction -> Experiment Plan -> Critique (multi-persona).
"""

import json
import logging
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import _parse_action_arguments, _safe_parse_json
from .llm import create_client, get_response_from_llm, model_supports_structured_output
from .structured_outputs import (
    CRITIQUE_RESPONSE_FORMAT,
    EXPERIMENT_PLAN_RESPONSE_FORMAT,
    FEASIBILITY_RESPONSE_FORMAT,
    GAP_HYPOTHESES_RESPONSE_FORMAT,
)
from .prompts import (
    CRITIQUE_PERSONAS,
    CRITIQUE_USER_PROMPT,
    DIRECTION_INITIAL_PROMPT,
    DIRECTION_REFLECTION_PROMPT,
    EXPERIMENT_PLAN_PROMPT,
    FEASIBILITY_SELECTION_PROMPT,
    FINALIZE_DIRECTION_TOOL,
    FINALIZE_LITERATURE_REVIEW_TOOL,
    GAP_HYPOTHESES_PROMPT,
    LITERATURE_REVIEW_FINAL_ROUND_PROMPT,
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
from .tools.tavily import TavilySearchTool
from .validators import (
    validate_idea,
    validate_literature_review,
    validate_experiment_plan,
)

logger = logging.getLogger(__name__)

# When parse fails, log this many chars of LLM response for debug (use --verbose to see).
_DEBUG_RESPONSE_PREVIEW_LEN = 2500


def _build_fallback_literature_review(
    topic_content: str,
    msg_history: List[Dict[str, Any]],
    last_tool_results: str,
) -> Dict[str, Any]:
    """Build a minimal valid literature_review from conversation history when LLM did not finalize."""
    entries: List[Dict[str, Any]] = []
    seen_titles: set = set()

    # Collect all "Results from your last action" / numbered result blocks from user messages
    text_to_parse = last_tool_results
    for msg in msg_history:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            text_to_parse += "\n\n" + msg["content"]

    # Split by numbered items: "1: ...", "2: ..."
    block_pat = re.compile(r"\n(\d+):\s*", re.MULTILINE)
    parts = block_pat.split(text_to_parse)
    # parts[0] = preamble, then [num, content, num, content, ...]
    i = 1
    while i + 1 < len(parts):
        content = parts[i + 1]
        # First line is typically "Title. Authors. Source, year."
        line1_end = content.find("\n")
        first_line = content[: line1_end].strip() if line1_end >= 0 else content.strip()
        url_match = re.search(r"URL:\s*(\S+)", content, re.IGNORECASE)
        abstract_match = re.search(r"Abstract:\s*(.+?)(?=\n(?:CITE:|URL:|\d+:)|$)", content, re.DOTALL | re.IGNORECASE)
        url = (url_match.group(1).strip() if url_match else "") or ""
        abstract = (abstract_match.group(1).strip() if abstract_match else first_line) or first_line
        # Normalize title: take up to first period that looks like end of title (e.g. "Title. Authors")
        title = first_line
        if ". " in first_line:
            title = first_line.split(". ")[0].strip() or first_line
        if title and title not in seen_titles and len(title) > 2:
            seen_titles.add(title)
            entries.append({
                "source": "arxiv" if "arxiv" in url.lower() else "search",
                "citation": {
                    "author": "",
                    "year": "",
                    "title": title[:500],
                    "url": url[:500] if url else "",
                },
                "approach_summary": (abstract[:2000] if abstract else title),
                "strengths": [],
                "weaknesses": [],
                "research_gaps": [],
            })
        i += 2

    if not entries:
        entries = [{
            "source": "fallback",
            "citation": {"author": "", "year": "", "title": "Auto-finalized (no entries extracted)."},
            "approach_summary": "Literature review was auto-finalized after exhausting rounds; no structured entries could be extracted from search results.",
            "strengths": [],
            "weaknesses": [],
            "research_gaps": [],
        }]

    topic_summary = (topic_content.strip() or "Literature review")[:3000]
    if not topic_summary:
        topic_summary = "Literature review (auto-finalized)."
    return {
        "topic_summary": topic_summary,
        "entries": entries,
        "synthesis": "Auto-finalized when reflection rounds were exhausted. Synthesis based on gathered search results.",
    }


def _debug_log_parse_failure(
    log: logging.Logger,
    phase: str,
    round_num: int,
    total_rounds: int,
    response_text: str,
    exc: Exception,
) -> None:
    """Log parse failure with response preview for debugging. Use --verbose to see full preview."""
    log.warning(
        "%s round %d/%d: parse failed (%s), moving to next round.",
        phase, round_num, total_rounds, type(exc).__name__,
    )
    log.debug("Parse error: %s", traceback.format_exc())
    preview = (response_text or "").strip()
    if len(preview) > _DEBUG_RESPONSE_PREVIEW_LEN:
        preview = preview[:_DEBUG_RESPONSE_PREVIEW_LEN] + "\n... [truncated]"
    log.debug("LLM response preview (%d chars):\n%s", len(response_text or ""), preview)
    if not log.isEnabledFor(logging.DEBUG):
        log.info(
            "  Response length: %d chars. Run with --verbose to see response preview.",
            len(response_text or ""),
        )


def _tools_for_config(
    s2_enabled: bool,
    arxiv_enabled: bool,
    tavily_enabled: bool,
    pubmed_enabled: bool,
    openalex_enabled: bool,
) -> List[Any]:
    """Build list of search tools + given finalize tool (caller adds finalize)."""
    tools: List[Any] = []
    if s2_enabled:
        tools.append(SemanticScholarSearchTool())
    if arxiv_enabled:
        tools.append(ArxivSearchTool())
    if tavily_enabled:
        tools.append(TavilySearchTool())
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
        getattr(config, "s2_enabled", False),
        getattr(config, "arxiv_enabled", True),
        getattr(config, "tavily_enabled", True),
        getattr(config, "pubmed_enabled", False),
        getattr(config, "openalex_enabled", False),
    )
    tools.append(FINALIZE_LITERATURE_REVIEW_TOOL)
    tools_dict: Dict[str, BaseTool] = {t.name: t for t in tools if isinstance(t, BaseTool)}
    tool_descriptions = build_tool_descriptions(tools)
    tool_names_str = build_tool_names(tools)
    system_prompt = get_literature_review_system_prompt(tool_descriptions, tool_names_str)

    num_reflections = getattr(config, "pipeline_literature_reflections", 8)
    num_reflections = max(6, num_reflections)  # ensure enough rounds for multiple searches + finalize
    logger.info("Phase 1: %d reflection rounds", num_reflections)
    last_tool_results = ""
    msg_history: List[Dict[str, Any]] = []

    for reflection_round in range(num_reflections):
        if reflection_round == 0:
            prompt_text = LITERATURE_REVIEW_INITIAL_PROMPT.format(topic_content=topic_content)
        elif reflection_round == num_reflections - 1:
            # Last round: force finalize so we don't run out of rounds without calling FinalizeLiteratureReview
            prompt_text = LITERATURE_REVIEW_FINAL_ROUND_PROMPT.format(
                current_round=reflection_round + 1,
                num_reflections=num_reflections,
                last_tool_results=last_tool_results or "No new results.",
            )
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

        except Exception as e:
            _debug_log_parse_failure(
                logger, "Phase 1", reflection_round + 1, num_reflections, response_text, e
            )
            last_tool_results = (
                "Your previous response could not be parsed. Reply with ACTION: <tool name> and ARGUMENTS: <JSON>."
            )
            # Last round: auto-pass, do not require LLM to return valid ACTION
            if reflection_round == num_reflections - 1:
                literature_review = _build_fallback_literature_review(
                    topic_content, msg_history, last_tool_results
                )
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(literature_review, f, indent=2, ensure_ascii=False)
                logger.info(
                    "Phase 1 auto-finalized (last round, parse failed): saved to %s",
                    output_path,
                )
                return literature_review
            continue

    # Out of rounds: auto-pass with fallback, no check required
    literature_review = _build_fallback_literature_review(
        topic_content, msg_history, last_tool_results
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(literature_review, f, indent=2, ensure_ascii=False)
    logger.info(
        "Phase 1 auto-finalized (out of rounds): saved to %s",
        output_path,
    )
    return literature_review


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
    use_structured = getattr(config, "pipeline_structured_output", True) and model_supports_structured_output(client_model)

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
        response_format=GAP_HYPOTHESES_RESPONSE_FORMAT if use_structured else None,
    )

    if use_structured:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            data = _extract_json_object(response_text)
    else:
        data = _extract_json_object(response_text)
    if not data or "gaps" not in data or "hypotheses" not in data:
        raise RuntimeError("Phase 2 LLM did not return valid JSON with 'gaps' and 'hypotheses'.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Phase 2 complete: saved to %s", output_path)
    return data


def run_feasibility_selection(
    hypotheses_path: str,
    config: Any,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Select the most feasible hypothesis from hypotheses.json (single LLM call)."""
    hypotheses_path = str(Path(hypotheses_path).resolve())
    with open(hypotheses_path, "r", encoding="utf-8") as f:
        hypotheses_data = json.load(f)

    if output_path is None:
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / (Path(hypotheses_path).stem.replace(".hypotheses", "") + ".feasibility.json"))
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info("Feasibility selection from %s", hypotheses_path)
    client, client_model = create_client(config.model)
    use_structured = getattr(config, "pipeline_structured_output", True) and model_supports_structured_output(client_model)
    hypotheses_json_str = json.dumps(hypotheses_data, indent=2, ensure_ascii=False)
    prompt_text = FEASIBILITY_SELECTION_PROMPT.format(hypotheses_json=hypotheses_json_str)
    system_message = "You are a research advisor. Output only a valid JSON object with chosen_hypothesis_name, rationale, and feasibility_scores. No markdown, no explanation."

    response_text, _ = get_response_from_llm(
        prompt=prompt_text,
        client=client,
        model=client_model,
        system_message=system_message,
        msg_history=[],
        temperature=0.5,
        response_format=FEASIBILITY_RESPONSE_FORMAT if use_structured else None,
    )

    if use_structured:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            data = _extract_json_object(response_text)
    else:
        data = _extract_json_object(response_text)
    if not data or "chosen_hypothesis_name" not in data:
        raise RuntimeError("Feasibility selection did not return valid JSON with chosen_hypothesis_name.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Feasibility selection complete: chosen=%s", data.get("chosen_hypothesis_name"))
    return data


def _build_fallback_direction(
    lit_review: Dict[str, Any],
    hypotheses_data: Dict[str, Any],
    chosen_hypothesis_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a minimal valid direction (idea) when Phase 3 runs out of rounds without FinalizeDirection."""
    hypotheses = hypotheses_data.get("hypotheses", [])
    chosen = None
    if chosen_hypothesis_id:
        for h in hypotheses:
            if h.get("name") == chosen_hypothesis_id:
                chosen = h
                break
    if not chosen and hypotheses:
        chosen = hypotheses[0]
    name = (chosen.get("name") or "fallback_direction").strip() or "fallback_direction"
    short_hyp = (chosen.get("short_hypothesis") or "Hypothesis not finalized by agent.").strip()
    if len(short_hyp) < 10:
        short_hyp = short_hyp + " (auto-finalized; expand in revision.)"
    synthesis = (lit_review.get("synthesis") or "").strip() or "Literature synthesis not available."
    if len(synthesis) < 10:
        synthesis = "Related work to be filled from literature review. (Auto-finalized.)"
    return {
        "Name": name[:200],
        "Title": (short_hyp[:80] + ("..." if len(short_hyp) > 80 else "")).strip() or "Research direction (auto-finalized)",
        "Short Hypothesis": short_hyp[:2000],
        "Related Work": synthesis[:3000],
        "Abstract": "This direction was auto-finalized when reflection rounds were exhausted. Please expand the abstract and experiments from the chosen hypothesis and literature review.",
        "Experiments": "Proposed experiments to be specified: replicate baseline, ablations, and main comparison. (Auto-finalized.)",
        "Risk Factors and Limitations": "Risks and limitations to be documented. (Auto-finalized.)",
        "References": [],
    }


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
        getattr(config, "s2_enabled", False),
        getattr(config, "arxiv_enabled", True),
        getattr(config, "tavily_enabled", True),
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

        except Exception as e:
            _debug_log_parse_failure(
                logger, "Phase 3", reflection_round + 1, num_reflections, response_text, e
            )
            last_tool_results = "Your previous response could not be parsed. Reply with ACTION: and ARGUMENTS:."
            if reflection_round == num_reflections - 1:
                direction = _build_fallback_direction(lit_review, hypotheses_data, chosen_hypothesis_id)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(direction, f, indent=2, ensure_ascii=False)
                logger.info("Phase 3 auto-finalized (last round, parse failed): saved to %s", output_path)
                return direction
            continue

    direction = _build_fallback_direction(lit_review, hypotheses_data, chosen_hypothesis_id)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(direction, f, indent=2, ensure_ascii=False)
    logger.info("Phase 3 auto-finalized (out of rounds): saved to %s", output_path)
    return direction


def _build_fallback_experiment_plan(direction: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal valid experiment plan when Phase 4 LLM does not return valid JSON."""
    name = (direction.get("Name") or "proposal").strip() or "proposal"
    title = (direction.get("Title") or "Research proposal (auto-finalized)").strip() or "Research proposal (auto-finalized)"
    return {
        "proposal_ref": {"name": name[:200], "title": title[:500]},
        "metrics": [
            {"name": "primary_metric", "description": "Primary metric from proposal.", "primary": True},
            {"name": "secondary_metric", "description": "Secondary metrics.", "primary": False},
        ],
        "baselines": [{"name": "baseline", "description": "To be specified from literature.", "source": "", "citation": ""}],
        "datasets": [{"name": "dataset", "description": "To be specified.", "size_or_source": "", "license_or_access": ""}],
        "implementation_steps": [
            {"order": 1, "step": "Setup", "description": "Environment and data setup.", "deliverables": "Code and data ready."},
            {"order": 2, "step": "Baseline", "description": "Implement or run baselines.", "deliverables": "Baseline results."},
            {"order": 3, "step": "Main experiments", "description": "Run main experiments.", "deliverables": "Results and figures."},
        ],
        "min_config": {
            "hardware": "Single GPU, 24GB VRAM",
            "min_data": "Standard benchmark or 10k+ samples",
            "framework": "PyTorch 2.0",
            "estimated_time": "2-4 weeks for main experiments",
        },
    }


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
    use_structured = getattr(config, "pipeline_structured_output", True) and model_supports_structured_output(client_model)
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
        response_format=EXPERIMENT_PLAN_RESPONSE_FORMAT if use_structured else None,
    )

    if use_structured:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            data = _extract_json_object(response_text)
    else:
        data = _extract_json_object(response_text)
    if not data:
        logger.warning("Phase 4 LLM did not return valid JSON; using fallback experiment plan.")
        data = _build_fallback_experiment_plan(direction)

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


def run_critique(
    direction_path: str,
    config: Any,
    output_path: Optional[str] = None,
    experiment_plan_path: Optional[str] = None,
    persona_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run multi-persona critique on the direction (and optionally experiment plan)."""
    direction_path = str(Path(direction_path).resolve())
    with open(direction_path, "r", encoding="utf-8") as f:
        direction = json.load(f)
    direction_json_str = json.dumps(direction, indent=2, ensure_ascii=False)

    experiment_plan_json_str = "Not provided."
    if experiment_plan_path and Path(experiment_plan_path).exists():
        with open(experiment_plan_path, "r", encoding="utf-8") as f:
            experiment_plan = json.load(f)
        experiment_plan_json_str = json.dumps(experiment_plan, indent=2, ensure_ascii=False)

    if output_path is None:
        out_dir = getattr(config, "output_dir", "output")
        output_path = str(Path(out_dir) / (Path(direction_path).stem.replace(".direction", "") + ".critique.json"))
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    personas = [p for p in CRITIQUE_PERSONAS if persona_ids is None or p["id"] in persona_ids]
    if not personas:
        raise ValueError("No critique personas selected.")

    logger.info("Critique: %d personas for %s", len(personas), direction_path)
    client, client_model = create_client(config.model)
    user_prompt = CRITIQUE_USER_PROMPT.format(
        direction_json=direction_json_str,
        experiment_plan_json=experiment_plan_json_str,
    )

    use_structured = getattr(config, "pipeline_structured_output", True) and model_supports_structured_output(client_model)
    reviews: List[Dict[str, Any]] = []
    for persona in personas:
        logger.info("Critique persona: %s", persona["name"])
        response_text, _ = get_response_from_llm(
            prompt=user_prompt,
            client=client,
            model=client_model,
            system_message=persona["system_prompt"],
            msg_history=[],
            temperature=0.3,
            response_format=CRITIQUE_RESPONSE_FORMAT if use_structured else None,
        )
        if use_structured:
            try:
                review_data = json.loads(response_text)
            except json.JSONDecodeError:
                review_data = _extract_json_object(response_text)
        else:
            review_data = _extract_json_object(response_text)
        if review_data:
            reviews.append({
                "persona_id": persona["id"],
                "persona_name": persona["name"],
                **review_data,
            })
        else:
            reviews.append({
                "persona_id": persona["id"],
                "persona_name": persona["name"],
                "raw_response": response_text[:2000],
                "parse_error": True,
            })

    result = {"direction_ref": direction.get("Name") or direction.get("Title", ""), "reviews": reviews}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Critique complete: saved to %s", output_path)
    return result


def run_full_research_pipeline(
    topic_path: str,
    config: Any,
    output_dir: Optional[str] = None,
    skip_feasibility: bool = False,
    skip_critique: bool = False,
) -> Dict[str, List[str]]:
    """Run full pipeline: lit review -> hypotheses -> feasibility selection -> direction -> experiment plan -> critique."""
    topic_path = str(Path(topic_path).resolve())
    base = Path(topic_path).stem
    out_dir = output_dir or getattr(config, "output_dir", "output")
    out_dir = str(Path(out_dir).resolve())
    os.makedirs(out_dir, exist_ok=True)

    paths: Dict[str, List[str]] = {
        "literature_review": [],
        "hypotheses": [],
        "feasibility_selection": [],
        "direction": [],
        "experiment_plan": [],
        "critique": [],
    }

    lit_path = str(Path(out_dir) / f"{base}.lit_review.json")
    paths["literature_review"].append(lit_path)
    run_literature_review(topic_path, config, lit_path)

    hyp_path = str(Path(out_dir) / f"{base}.hypotheses.json")
    paths["hypotheses"].append(hyp_path)
    run_gap_hypotheses(lit_path, config, hyp_path)

    chosen_hypothesis_id: Optional[str] = None
    if not skip_feasibility:
        feas_path = str(Path(out_dir) / f"{base}.feasibility.json")
        paths["feasibility_selection"].append(feas_path)
        feas_data = run_feasibility_selection(hyp_path, config, feas_path)
        chosen_hypothesis_id = feas_data.get("chosen_hypothesis_name")

    dir_path = str(Path(out_dir) / f"{base}.direction.json")
    paths["direction"].append(dir_path)
    run_direction(lit_path, hyp_path, config, dir_path, chosen_hypothesis_id=chosen_hypothesis_id)

    exp_path = str(Path(out_dir) / f"{base}.experiment_plan.json")
    paths["experiment_plan"].append(exp_path)
    run_experiment_plan(dir_path, config, exp_path)

    if not skip_critique:
        critique_path = str(Path(out_dir) / f"{base}.critique.json")
        paths["critique"].append(critique_path)
        persona_ids = getattr(config, "critique_persona_ids", None)
        run_critique(dir_path, config, critique_path, experiment_plan_path=exp_path, persona_ids=persona_ids)

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
