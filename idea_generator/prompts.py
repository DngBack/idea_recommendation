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
- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly distinguishes from it, and is not a trivial extension.
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
<If ACTION is "SearchSemanticScholar", provide the search query as {{"query": "your search query"}}. If ACTION is "SearchArxiv", provide the search query as {{"query": "your search query"}}. If ACTION is "FinalizeIdea", provide the idea details as {{"idea": {{ ... }}}} with the IDEA JSON specified below.>

If you choose to finalize your idea, provide the IDEA JSON in the arguments:

IDEA JSON:
```json
{{
  "idea": {{
    "Name": "...",
    "Title": "...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": "...",
    "Risk Factors and Limitations": "..."
  }}
}}
```

Ensure the JSON is properly formatted for automatic parsing.

Note: You should perform at least one literature search (using SearchSemanticScholar or SearchArxiv) before finalizing your idea to ensure it is well-informed by existing research."""


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
