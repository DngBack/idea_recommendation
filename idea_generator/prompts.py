"""
Prompt templates for the idea generation pipeline.
All prompts are functions so they can incorporate dynamic tool lists.
"""

from typing import List

from .tools.base import BaseTool


# ---------------------------------------------------------------------------
# Helper: build tool description block from the registered tools list
# ---------------------------------------------------------------------------

def build_tool_descriptions(tools: list) -> str:
    """Build a formatted tool-description string for the system prompt."""
    parts = []
    for tool in tools:
        if isinstance(tool, BaseTool):
            parts.append(f"- **{tool.name}**: {tool.description}")
        elif isinstance(tool, dict):
            parts.append(f"- **{tool['name']}**: {tool['description']}")
    return "\n\n".join(parts)


def build_tool_names(tools: list) -> str:
    """Build a comma-separated quoted list of tool names."""
    names = []
    for tool in tools:
        if isinstance(tool, BaseTool):
            names.append(f'"{tool.name}"')
        elif isinstance(tool, dict):
            names.append(f'"{tool["name"]}"')
    return ", ".join(names)


# ---------------------------------------------------------------------------
# FinalizeIdea pseudo-tool definition (not a BaseTool, just a dict)
# ---------------------------------------------------------------------------

FINALIZE_IDEA_TOOL = {
    "name": "FinalizeIdea",
    "description": """Finalize your idea by providing the idea details.

The IDEA JSON should include the following fields:
- "Name": A short descriptor of the idea. Lowercase, no spaces, underscores allowed.
- "Title": A catchy and informative title for the proposal.
- "Short Hypothesis": A concise statement of the main hypothesis or research question. Clarify the need for this specific direction, ensure this is the best setting to investigate this idea, and there are not obvious other simpler ways to answer the question.
- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly distinguishes from it, and is not a trivial extension. Cite sources using [Author (Year)] and ensure every cited work has a corresponding entry in "References".
- "References": An array of citation objects, one for each source cited in Related Work. Each object must have "author", "year", "title", and optionally "url" or "doi". Use the exact CITE lines from the search tool results (e.g. SearchArxiv, SearchTavily, SearchSemanticScholar, SearchPubMed, SearchOpenAlex) to fill these fields.
- "Abstract": An abstract that summarizes the proposal in conference format (approximately 250 words).
- "Experiments": A list of experiments that would be conducted to validate the proposal. Ensure these are simple and feasible. Be specific in exactly how you would test the hypothesis, and detail precise algorithmic changes. Include the evaluation metrics you would use.
- "Risk Factors and Limitations": A list of potential risks and limitations of the proposal.""",
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def get_system_prompt(tool_descriptions: str, tool_names_str: str) -> str:
    """Return the system prompt instructing the LLM how to generate ideas."""
    return f"""You are an experienced AI researcher who aims to propose high-impact research ideas resembling exciting grant proposals. Feel free to propose any novel ideas or experiments; make sure they are novel. Be very creative and think out of the box. Each proposal should stem from a simple and elegant question, observation, or hypothesis about the topic. For example, they could involve very interesting and simple interventions or investigations that explore new possibilities or challenge existing assumptions. Clearly clarify how the proposal distinguishes from the existing literature.

Ensure that the proposal does not require resources beyond what an academic lab could afford. These proposals should lead to papers that are publishable at top ML conferences.

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<The action to take, exactly one of {tool_names_str}>

ARGUMENTS:
<If ACTION is a search tool (e.g. SearchArxiv, SearchTavily, SearchSemanticScholar), provide the search query as {{"query": "your search query"}}. If ACTION is "FinalizeIdea", provide the idea details as {{"idea": {{ ... }}}} with the IDEA JSON specified below.>

If you choose to finalize your idea, provide the IDEA JSON in the arguments:

IDEA JSON:
```json
{{
  "idea": {{
    "Name": "...",
    "Title": "...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "References": [{{ "author": "...", "year": "...", "title": "...", "url": "..." }}],
    "Abstract": "...",
    "Experiments": "...",
    "Risk Factors and Limitations": "..."
  }}
}}
```

Ensure the JSON is properly formatted for automatic parsing.

Before finalizing, you must have called at least one literature search (using any of the search tools). When writing Related Work, cite each source as [Author (Year)] and ensure every cited source appears in References with author, year, title, and url or doi."""


# ---------------------------------------------------------------------------
# User prompts
# ---------------------------------------------------------------------------

IDEA_GENERATION_PROMPT = """{workshop_description}

Here are the proposals that you have already generated:

'''
{prev_ideas_string}
'''

Begin by generating an interestingly new high-level research proposal that differs from what you have previously proposed.
"""

IDEA_REFLECTION_PROMPT = """Round {current_round}/{num_reflections}.

In your thoughts, first carefully consider the quality, novelty, and feasibility of the proposal you just created.
Include any other factors that you think are important in evaluating the proposal.
Ensure the proposal is clear and concise, and the JSON is in the correct format.
Do not make things overly complicated.
In the next attempt, try to refine and improve your proposal.
Stick to the spirit of the original idea unless there are glaring issues.

If you have new information from tools, such as literature search results, incorporate them into your reflection and refine your proposal accordingly.

Results from your last action (if any):

{last_tool_results}
"""

VALIDATION_FIX_PROMPT = """The idea you just proposed has validation errors:

{errors}

Please fix the issues and finalize the idea again using the FinalizeIdea action. Make sure all required fields are present and correctly formatted.
"""

# ---------------------------------------------------------------------------
# Research pipeline – Phase 1: Literature Review
# ---------------------------------------------------------------------------

FINALIZE_LITERATURE_REVIEW_TOOL = {
    "name": "FinalizeLiteratureReview",
    "description": """Finalize the literature review by providing the structured review.

The payload must be a JSON object with:
- "topic_summary": Short summary of the research topic (string).
- "entries": Array of entry objects. Each entry has:
  - "source": Paper or method name (string).
  - "citation": Object with "author", "year", "title", and optionally "url" or "doi".
  - "approach_summary": What the method does (string).
  - "strengths": Array of strings.
  - "weaknesses": Array of strings.
  - "research_gaps": Array of strings (gaps this work does not address).
- "synthesis": Overall synthesis paragraph: trends and common gaps (string).

Use ARGUMENTS as {"literature_review": { ... }} with the above structure.""",
}


def get_literature_review_system_prompt(tool_descriptions: str, tool_names_str: str) -> str:
    """System prompt for Phase 1: literature reviewer."""
    return f"""You are an expert literature reviewer. Your task is to conduct a detailed, thorough literature review on the given research topic.

You MUST search multiple times before finalizing:
- Use at least 4–6 search calls (or more) with different queries: try variations of keywords, specific methods, and sub-topics. Use different tools (e.g. SearchArxiv and SearchTavily) to cover more sources.
- Aim for at least 8–12 distinct papers or approaches in your final review. Do NOT finalize with only 3–5 entries; a detailed review needs broad coverage.
- For each important paper or approach: (1) summarize the approach, (2) list strengths and weaknesses, (3) identify research gaps.

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<Exactly one of {tool_names_str}>

ARGUMENTS:
<For search tools: {{"query": "your search query"}}. For FinalizeLiteratureReview: {{"literature_review": {{ "topic_summary": "...", "entries": [...], "synthesis": "..." }}}}>

Only call FinalizeLiteratureReview when you have performed several searches and have at least 8 distinct entries. Ensure every entry has source, citation (author, year, title, url or doi), approach_summary, strengths, weaknesses, and research_gaps. Write a concise synthesis paragraph."""


LITERATURE_REVIEW_INITIAL_PROMPT = """Research topic:

{topic_content}

Conduct a detailed literature review. You have multiple rounds: use them to search repeatedly with different queries (keyword variants, method names, sub-topics) and use different search tools (e.g. arXiv and Tavily). Only after at least 4–6 searches and 8+ distinct papers or approaches, finalize with FinalizeLiteratureReview. For each work, record approach summary, strengths, weaknesses, and research gaps."""


LITERATURE_REVIEW_REFLECTION_PROMPT = """Round {current_round}/{num_reflections}.

Consider the literature you have gathered. If you have fewer than 8 entries or have not yet used several different search queries, use a search tool now (try a new query or a different tool). Add or refine entries: approach_summary, strengths, weaknesses, research_gaps. Ensure the synthesis captures overall trends and common gaps.

Results from your last action:

{last_tool_results}

When you have at least 8 entries and have searched multiple times, use FinalizeLiteratureReview with the complete literature_review JSON. If in doubt, search again before finalizing."""

# Used when this is the last round: force finalize (model often keeps searching otherwise).
LITERATURE_REVIEW_FINAL_ROUND_PROMPT = """This is the FINAL round ({current_round}/{num_reflections}). You MUST call FinalizeLiteratureReview now. Do NOT search again.

Summarize all the papers and approaches you have gathered so far into the literature_review JSON (topic_summary, entries with source, citation, approach_summary, strengths, weaknesses, research_gaps, and synthesis). Use the information from your previous search results below. If you have fewer than 8 entries, include all you have and write a short synthesis.

Results from your last action:

{last_tool_results}

Reply with ACTION: FinalizeLiteratureReview and ARGUMENTS: {{"literature_review": {{ ... }}}} now."""


# ---------------------------------------------------------------------------
# Research pipeline – Phase 2: Gap and Hypotheses
# ---------------------------------------------------------------------------

GAP_HYPOTHESES_PROMPT = """Based on the following structured literature review, identify research gaps and propose testable hypotheses.

Literature review:

{lit_review_json}

Tasks:
1. List 3–8 clear research gaps. For each gap provide: id (short identifier, e.g. "gap_1"), description, related_entries (array of source names or indices from the review), and optionally priority ("high" / "medium" / "low").
2. Propose 5–{max_hypotheses} hypotheses that could be investigated. Each hypothesis must have: name (lowercase with underscores), short_hypothesis (1–3 sentences), linked_gap_ids (array of gap ids this hypothesis addresses), rationale (why this is a good direction).

Respond with a single JSON object only (no markdown, no explanation):
{{"gaps": [{{"id": "...", "description": "...", "related_entries": [...], "priority": "..."}}, ...], "hypotheses": [{{"name": "...", "short_hypothesis": "...", "linked_gap_ids": [...], "rationale": "..."}}, ...]}}"""


# ---------------------------------------------------------------------------
# Research pipeline – Phase 3: Direction and Critique
# ---------------------------------------------------------------------------

FINALIZE_DIRECTION_TOOL = {
    "name": "FinalizeDirection",
    "description": """Finalize the research direction (detailed proposal) by providing the full proposal with critique and evidence.

The payload must include "direction" with an object that has:
- All fields of a research idea: Name, Title, Short Hypothesis, Related Work, References, Abstract, Experiments, Risk Factors and Limitations.
- "chosen_hypothesis": Object with "name", "short_hypothesis" (reference to the hypothesis from Phase 2).
- "critique": String or array of strings (criticism and counter-arguments considered).
- "evidence_summary": String (main evidence from literature supporting this direction).

Use ARGUMENTS as {"direction": { ... }}. Cite sources in Related Work as [Author (Year)] and include every cited work in References with author, year, title, url or doi.""",
}


def get_direction_system_prompt(tool_descriptions: str, tool_names_str: str) -> str:
    """System prompt for Phase 3: choose direction and write detailed proposal."""
    return f"""You are a senior AI researcher. Your task is to pick one research direction from the given hypotheses, deepen it with further literature if needed, write a critique (counter-arguments and limitations considered), summarize supporting evidence, and produce a detailed research proposal.

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<Exactly one of {tool_names_str}>

ARGUMENTS:
<For search tools: {{"query": "..."}}. For FinalizeDirection: {{"direction": {{ "Name": "...", "Title": "...", "Short Hypothesis": "...", "Related Work": "...", "References": [...], "Abstract": "...", "Experiments": "...", "Risk Factors and Limitations": "...", "chosen_hypothesis": {{ "name": "...", "short_hypothesis": "..." }}, "critique": "...", "evidence_summary": "..." }}}}>

Before finalizing, you must have used at least one search tool. Ensure the proposal is feasible for an academic lab and publishable at top venues."""


DIRECTION_INITIAL_PROMPT = """Literature review synthesis and context:

{lit_review_synthesis}

Candidate hypotheses to choose from:

{hypotheses_list}

Select ONE hypothesis (or a concrete combination) as your research direction. Search for additional papers if needed to strengthen related work and evidence. Then write:
1. A detailed proposal (Name, Title, Short Hypothesis, Related Work, References, Abstract, Experiments, Risk Factors).
2. chosen_hypothesis: which hypothesis you chose.
3. critique: key counter-arguments and limitations you considered.
4. evidence_summary: main evidence from the literature supporting this direction.

When ready, call FinalizeDirection with the full direction JSON."""


DIRECTION_REFLECTION_PROMPT = """Round {current_round}/{num_reflections}.

Refine your proposal based on the new information. Strengthen related work, critique, and evidence. Ensure the direction JSON is complete and well-formatted.

Results from your last action:

{last_tool_results}

When satisfied, use FinalizeDirection with the complete direction payload."""


# ---------------------------------------------------------------------------
# Research pipeline – Phase 4: Experiment Plan
# ---------------------------------------------------------------------------

EXPERIMENT_PLAN_PROMPT = """Given the following research direction (proposal), produce a detailed experiment plan.

Research direction:

{direction_json}

Produce a JSON object with this exact structure (no markdown, no explanation):

{{
  "proposal_ref": {{ "name": "<Name from direction>", "title": "<Title from direction>" }},
  "metrics": [
    {{ "name": "...", "description": "...", "primary": true_or_false }},
    ...
  ],
  "baselines": [
    {{ "name": "...", "description": "...", "source": "...", "citation": "..." }},
    ...
  ],
  "datasets": [
    {{ "name": "...", "description": "...", "size_or_source": "...", "license_or_access": "..." }},
    ...
  ],
  "implementation_steps": [
    {{ "order": 1, "step": "...", "description": "...", "deliverables": "..." }},
    ...
  ],
  "min_config": {{
    "hardware": "e.g. single GPU, 24GB VRAM",
    "min_data": "e.g. CIFAR-10 or 10k samples",
    "framework": "e.g. PyTorch 2.0",
    "estimated_time": "e.g. 2-3 weeks for main experiments"
  }}
}}

Be specific: metrics should include primary and secondary; baselines must be named methods from the literature; datasets with size and access; implementation steps in order with clear deliverables; min_config must be lab-feasible."""


# ---------------------------------------------------------------------------
# Research pipeline – Feasibility selection (after hypotheses)
# ---------------------------------------------------------------------------

FEASIBILITY_SELECTION_PROMPT = """You are an experienced research advisor. Given the following research gaps and hypotheses from a literature review, select the ONE hypothesis that is most feasible to pursue in an academic lab setting.

Consider:
- Clarity and testability of the hypothesis
- Resource feasibility (data, compute, time)
- Alignment with current literature and likelihood of publishable results at a top ML venue (ICML, NeurIPS, ICLR)
- Risk vs. impact balance

Hypotheses and gaps:

{hypotheses_json}

Respond with a single JSON object only (no markdown, no explanation):
{{
  "chosen_hypothesis_name": "<exact 'name' field of the chosen hypothesis>",
  "rationale": "2–4 sentences explaining why this hypothesis is the most feasible.",
  "feasibility_scores": [
    {{ "hypothesis_name": "...", "score_1_to_5": 4, "brief_reason": "..." }},
    ...
  ]
}}

Include feasibility_scores for each hypothesis (1–5, 5 = most feasible). The chosen_hypothesis_name must match one of the "name" values in the hypotheses list exactly."""


# ---------------------------------------------------------------------------
# Research pipeline – Critique with multiple personas (after direction)
# ---------------------------------------------------------------------------

# Personas for multi-perspective review. Each has id, name, and system_prompt.
CRITIQUE_PERSONAS = [
    {
        "id": "icml_reviewer",
        "name": "ICML Reviewer",
        "system_prompt": """You are a senior program committee member for the International Conference on Machine Learning (ICML). You have reviewed hundreds of submissions and value novelty, clarity, rigorous evaluation, and impact. You are strict but fair: you reject incremental work and unclear claims, but you support bold yet well-justified ideas. You write concise, constructive reviews. Use the typical ICML review format: Summary, Strengths, Weaknesses, Questions for authors, and a clear score (1–10) with recommendation (Accept / Weak Accept / Borderline / Weak Reject / Reject).""",
    },
    {
        "id": "neurips_reviewer",
        "name": "NeurIPS/ICLR Reviewer",
        "system_prompt": """You are a reviewer for NeurIPS or ICLR. You care about scientific rigor, reproducibility, clear motivation, and novelty. You expect strong baselines, ablations, and honest limitations. You write in a professional tone and provide actionable feedback. Give a score from 1 to 10 and a clear recommendation (Accept / Borderline Accept / Borderline Reject / Reject), plus a short summary, strengths, weaknesses, and suggestions.""",
    },
    {
        "id": "senior_professor",
        "name": "Senior Professor (PI)",
        "system_prompt": """You are a tenured professor leading a top ML lab. You evaluate proposals from the perspective of a principal investigator: Is this feasible with a small team and limited budget? Would you assign a PhD student or postdoc to this? Is the timeline realistic? What are the main risks and how would you mitigate them? Give a clear verdict (Go / Revise and reconsider / Do not pursue) and 2–4 paragraphs of advice.""",
    },
    {
        "id": "skeptic_reviewer",
        "name": "Skeptic Reviewer",
        "system_prompt": """You are a critical, skeptical reviewer. Your job is to stress-test the proposal: challenge assumptions, point out missing baselines or threats to validity, and identify overclaims. You are not hostile—you want to strengthen the work by surfacing weaknesses. Provide a concise critique with: main concerns, missing experiments or references, and whether the claims are justified. End with a recommendation (Support with major revisions / Borderline / Do not support).""",
    },
]

CRITIQUE_USER_PROMPT = """Review the following research proposal and experiment plan. Provide your assessment according to your role.

Research direction (proposal):
{direction_json}

Experiment plan (if available):
{experiment_plan_json}

Output a valid JSON object only (no markdown, no extra text):
{{
  "summary": "2–3 sentence summary of the proposal.",
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "score": <1–10>,
  "recommendation": "<e.g. Accept / Weak Accept / Borderline / Weak Reject / Reject or Go / Revise / Do not pursue>",
  "detailed_review": "Optional longer paragraph with detailed feedback."
}}"""


# ---------------------------------------------------------------------------
# Hypothesis expansion (Phase 3 – legacy)
# ---------------------------------------------------------------------------

HYPOTHESIS_EXPANSION_FROM_TOPIC = """Given the following research topic description, list distinct sub-hypotheses or theory variants that could be investigated independently. Each should be a concrete, researchable direction.

Topic:
{topic_text}

Respond with a JSON array only (no markdown, no explanation). Each element must have:
- "Name": short lowercase identifier with underscores (e.g. "adaptive_damping_ablation")
- "Short Hypothesis": one or two sentences stating the hypothesis or research question

Generate between 5 and {max_sub} items. Output format:
[{{"Name": "...", "Short Hypothesis": "..."}}, ...]
"""

HYPOTHESIS_EXPANSION_FROM_IDEA = """Given the following research idea, list distinct sub-hypotheses or theory variants that could be investigated independently. Each should be a concrete, researchable direction derived from or orthogonal to this idea.

Idea (Title): {title}
Short Hypothesis: {short_hypothesis}

Respond with a JSON array only (no markdown, no explanation). Each element must have:
- "Name": short lowercase identifier with underscores
- "Short Hypothesis": one or two sentences stating the hypothesis or research question

Generate between 5 and {max_sub} items. Output format:
[{{"Name": "...", "Short Hypothesis": "..."}}, ...]
"""
