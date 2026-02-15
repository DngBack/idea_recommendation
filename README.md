# Idea Generator

A **standalone** tool for AI research workflows: from a topic file (Markdown) you can run a **research pipeline** (literature review → hypotheses → feasibility selection → direction → experiment plan → multi-persona critique) or **quickly generate many ideas** (idea generation). Inspired by [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2).

---

## Two modes of use

| Mode | Command | Purpose |
|------|---------|---------|
| **Research pipeline** | `--pipeline` or `--phase <name>` | Structured flow: lit review → hypotheses → feasibility selection → direction → experiment plan → multi-persona critique. Each step produces one JSON file. |
| **Idea generation** | `--topic-file ...` (without `--pipeline`) | Quickly generate multiple research proposals from a topic, with search + reflection; output is one JSON file (array of ideas). |
| **Hypothesis expansion** | `--expand-hypotheses` | From a topic or one idea JSON → list of sub-hypotheses (use standalone or with the pipeline). |

---

## Key features

- **Research pipeline (6 steps):** Literature review → Gaps + hypotheses → **Feasibility selection** (chọn ý tưởng khả thi nhất) → Direction → Experiment plan → **Multi-persona critique** (ICML reviewer, NeurIPS reviewer, professor, skeptic). Run the full pipeline or a single phase using existing files.
- **Idea generation:** From a topic file → multiple research ideas (Name, Title, Hypothesis, Related Work, References, Abstract, Experiments, Risk Factors) with reflection + search.
- **Literature search (4 sources):** Semantic Scholar, arXiv (default), PubMed, OpenAlex (optional). Used in both pipeline and idea generation.
- **Multi-model:** OpenAI (gpt-4o, o1, o3-mini, gpt-5.2), Anthropic Claude, Gemini, Ollama (Qwen, DeepSeek, ...).
- **Validation:** JSON schema for ideas, lit review, and experiment plan; errors are sent back to the LLM to fix.
- **Checkpoint / Resume** (idea generation), **YAML config + CLI**.

---

## Quick Start

### 1. Install

```bash
cd idea_recommendation
pip install -e .
```

Or install dependencies only: `pip install -r requirements.txt`

### 2. Environment variables (API keys)

```bash
export OPENAI_API_KEY="sk-..."          # Required for OpenAI
export S2_API_KEY="..."                 # Optional – Semantic Scholar (higher rate limit)
export ANTHROPIC_API_KEY="..."         # Optional – Claude
export GEMINI_API_KEY="..."             # Optional – Gemini
export OPENALEX_MAILTO="your@email.com" # Optional – OpenAlex
```

### 3. Run

**Research pipeline (recommended for a full research workflow):**

```bash
idea-generator --topic-file topics/gan_optimization_adoe.md --pipeline
```

→ Produces in order: `output/<base>.lit_review.json` → `.hypotheses.json` → `.direction.json` → `.experiment_plan.json`

**Idea generation (quick batch of ideas):**

```bash
idea-generator --topic-file topics/example_icbinb.md --max-generations 5 --output output/ideas.json
```

**Resume (idea generation only):**

```bash
idea-generator --topic-file topics/example_icbinb.md --output output/ideas.json --resume
```

---

## Detailed guide

### Topic file format

The topic is a Markdown (`.md`) file describing the research area. Example:

```markdown
# Title: My Research Topic
## Keywords
keyword1, keyword2
## TL;DR
One sentence summary.
## Abstract
Longer description: background, goals, expected contributions, evaluation plan.
```

Use with `--topic-file path/to/topic.md` (pipeline or idea generation).

---

### Research pipeline (6 steps)

Flow: **Literature review** → **Gaps & hypotheses** → **Feasibility selection** → **Direction** → **Experiment plan** → **Critique (multi-persona)**. Each step writes one JSON file.

**Run full pipeline:**

```bash
idea-generator --topic-file topics/gan_optimization_adoe.md --pipeline
```

Optional: `--skip-feasibility` or `--skip-critique` to omit those steps. Use `python -m idea_generator` if the `idea-generator` command is not installed.

**Run a single phase** (when you already have the previous phase’s output):

```bash
# Phase 1: literature review
idea-generator --topic-file topics/gan_optimization_adoe.md --phase literature_review --output output/my.lit_review.json

# Phase 2: from lit review
idea-generator --phase hypotheses --from-literature output/gan_optimization_adoe.lit_review.json

# Feasibility: choose most feasible hypothesis (from hypotheses)
idea-generator --phase feasibility_selection --from-hypotheses output/gan_optimization_adoe.hypotheses.json

# Phase 3: direction (optionally use chosen hypothesis from feasibility)
idea-generator --phase direction --from-literature output/gan_optimization_adoe.lit_review.json --from-hypotheses output/gan_optimization_adoe.hypotheses.json [--from-feasibility output/gan_optimization_adoe.feasibility.json]

# Phase 4: experiment plan
idea-generator --phase experiment_plan --from-direction output/gan_optimization_adoe.direction.json

# Critique: multi-persona review (ICML reviewer, NeurIPS reviewer, professor, skeptic)
idea-generator --phase critique --from-direction output/gan_optimization_adoe.direction.json [--from-experiment-plan output/gan_optimization_adoe.experiment_plan.json]
```

**Pipeline config** in `config/default.yaml`:

```yaml
research_pipeline:
  literature_reflections: 8
  direction_reflections: 5
  max_hypotheses: 10
  skip_feasibility: false
  skip_critique: false
  critique_persona_ids: null   # null = all; or e.g. [icml_reviewer, senior_professor]
```

**Output format per phase:**

| File | Main contents |
|------|----------------|
| `*.lit_review.json` | `topic_summary`, `entries` (source, citation, approach_summary, strengths, weaknesses, research_gaps), `synthesis` |
| `*.hypotheses.json` | `gaps`, `hypotheses` (name, short_hypothesis, linked_gap_ids, rationale) |
| `*.feasibility.json` | `chosen_hypothesis_name`, `rationale`, `feasibility_scores` (per-hypothesis score and reason) |
| `*.direction.json` | Full proposal + `chosen_hypothesis`, `critique`, `evidence_summary` |
| `*.experiment_plan.json` | `proposal_ref`, `metrics`, `baselines`, `datasets`, `implementation_steps`, `min_config` |
| `*.critique.json` | `direction_ref`, `reviews` (per persona: summary, strengths, weaknesses, score, recommendation) |

**Critique personas** (defined in `prompts.py`): ICML Reviewer, NeurIPS/ICLR Reviewer, Senior Professor (PI), Skeptic Reviewer. Each produces a structured review (summary, strengths, weaknesses, score 1–10, recommendation).

You can export the lit review to CSV (e.g. from Excel), edit it, and reuse it as input for Phase 2.

---

### Idea generation (quick batch of ideas)

- Set topic and number of ideas: `--topic-file ... --max-generations 5`
- Use config file: `--config config/default.yaml`
- Enable/disable search: `--no-arxiv`, `--pubmed`, `--openalex`
- Validation: `--no-validate` to disable; `--novelty-scoring` to enable novelty scoring (optionally `--novelty-model`)
- Default output: same directory as topic, filename `<topic-base>.json`; override with `--output output/ideas.json`

**Citations:** Ideas and directions include **References** (author, year, title, url/doi). Related Work should cite as `[Author (Year)]`; each cited source must have an entry in References. Search results provide **CITE** lines for the LLM to copy.

### When is search used?

Search tools are used in **three** places:

| Context | When | Purpose |
|--------|------|--------|
| **Literature review (Phase 1)** | Mỗi round trong phase 1, LLM có thể gọi một search tool (arXiv, Tavily, …) hoặc FinalizeLiteratureReview. Số round = `literature_reflections` (mặc định **12**). | Thu thập nhiều paper/approach để viết lit review chi tiết (khuyến nghị ≥ 8 entries, search 4–6+ lần với query đa dạng). |
| **Direction (Phase 3)** | Mỗi round trong phase 3, LLM có thể search hoặc FinalizeDirection. Số round = `direction_reflections` (5). | Bổ sung tài liệu khi viết proposal (related work, evidence). |
| **Idea generation** | Mỗi idea có `num_reflections` round (5); mỗi round có thể search hoặc FinalizeIdea. | Tìm tài liệu cho từng ý tưởng (related work, references). |

**Đảm bảo literature review chi tiết:** Prompt đã được cấu hình để yêu cầu search nhiều lần (nhiều query, nhiều nguồn) và ít nhất 8 entries trước khi finalize. Tăng `literature_reflections` trong `config/default.yaml` (ví dụ 15–20) nếu bạn muốn còn nhiều round hơn để search thêm.

### Search tools (used by pipeline and idea generation)

| Tool             | Default | Enable/disable              | Notes |
|------------------|---------|-----------------------------|-------|
| Semantic Scholar | Off     | `--s2` or `s2_enabled: true`| CS/ML; cần `S2_API_KEY` |
| arXiv            | On      | `--no-arxiv` to disable     | Preprints |
| Tavily           | On      | `--no-tavily` to disable    | Web + literature; cần `TAVILY_API_KEY` |
| PubMed           | Off     | `--pubmed` or YAML          | Medicine, biology |
| OpenAlex         | Off     | `--openalex` or YAML        | Broad coverage, DOI; `OPENALEX_MAILTO` optional |

Example: enable PubMed and OpenAlex:

```bash
idea-generator --topic-file topics/example_icbinb.md --pubmed --openalex
```

Or in `config/default.yaml`:

```yaml
pubmed_enabled: true
openalex_enabled: true
```

### Hypothesis expansion

From **a topic** or **one idea (JSON)** you can generate multiple **sub-hypotheses** as JSON, then use each as input for the pipeline or idea generation.

**1. Expansion from a topic file:**

```bash
idea-generator --topic-file topics/gan_optimization_adoe.md --expand-hypotheses
```

- Reads the topic file and calls the LLM once to produce 5–10 sub-hypotheses.
- Default output: `output/<topic-base>.hypotheses.json` (or the directory from config `output_dir`).
- Custom output: `--output path/to/hypotheses.json`.

**2. Expansion from one idea (JSON file):**

```bash
idea-generator --expand-hypotheses --from-idea-json path/to/idea.json
```

- `idea.json` can be a **single object** (one idea) or an **array** (first element is used).
- The idea object must have at least `Title` and `Short Hypothesis`.
- Output: `output/<idea-file-base>.hypotheses.json` unless `--output` is set.

**3. Limit number of sub-hypotheses:**

```bash
idea-generator --topic-file topics/example.md --expand-hypotheses --max-sub-hypotheses 8
```

**4. With model and config:**

```bash
idea-generator --topic-file topics/example.md --expand-hypotheses --config config/default.yaml --model gpt-4o
```

**Hypotheses file format:** JSON array; each item has at least:

- `Name`: short identifier (lowercase, underscores).
- `Short Hypothesis`: one or two sentences describing the hypothesis.

Example:

```json
[
  { "Name": "adaptive_damping_ablation", "Short Hypothesis": "We hypothesize that..." },
  { "Name": "rotation_proxy_comparison", "Short Hypothesis": "..." }
]
```

You can turn each item into a topic (e.g. write a .md file) and run idea generation or the pipeline for that direction.

---

## Configuration

Configure via `config/default.yaml`; all values can be overridden by CLI flags.

| Setting               | Default   | CLI Flag               | Description |
|-----------------------|-----------|------------------------|-------------|
| `model`               | `gpt-5.2` | `--model`              | LLM model for generation |
| `max_generations`     | `3`       | `--max-generations`    | Number of ideas per run (idea generation) |
| `num_reflections`     | `5`       | `--num-reflections`    | Reflection rounds per idea |
| `output_dir`          | `output`  | –                      | Output directory (when using config) |
| `validate`            | `true`    | `--no-validate`        | Enable/disable JSON schema validation |
| `novelty_scoring`     | `false`   | `--novelty-scoring`    | Enable novelty scoring |
| `novelty_model`       | (same as `model`) | `--novelty-model` | Model for novelty scoring |
| `checkpoint_interval` | `1`       | –                      | Save checkpoint every N ideas |
| `arxiv_enabled`       | `true`    | `--no-arxiv`           | Enable/disable arXiv search |
| `pubmed_enabled`      | `false`   | `--pubmed`             | Enable/disable PubMed search |
| `openalex_enabled`    | `false`   | `--openalex`           | Enable/disable OpenAlex search |
| `resume`              | `false`   | `--resume`             | Resume from checkpoint |
| `system_prompt_override` | `""`   | –                      | Override full system prompt (empty = default) |
| `pipeline_mode`       | `false`   | `--pipeline` / `--phase` | Run research pipeline instead of idea generation |
| `research_pipeline.literature_reflections` | `8` | – | Reflection rounds for Phase 1 |
| `research_pipeline.direction_reflections`  | `5` | – | Reflection rounds for Phase 3 |
| `research_pipeline.max_hypotheses`         | `10`| – | Max hypotheses for Phase 2 |

---

## Output format

**Idea generation** (`--topic-file` without `--pipeline`): one JSON file that is an **array** of ideas. Each idea has `Name`, `Title`, `Short Hypothesis`, `Related Work`, `References`, `Abstract`, `Experiments`, `Risk Factors and Limitations`; optional `novelty_score` when `--novelty-scoring` is enabled.

**Research pipeline:** each phase writes one file (see the format table in [Research pipeline (4 phases)](#research-pipeline-4-phases)).

---

## Project structure

```
idea_recommendation/
├── README.md
├── requirements.txt
├── pyproject.toml
├── config/
│   └── default.yaml
├── topics/
│   ├── example_icbinb.md
│   ├── example_ml_general.md
│   └── gan_optimization_adoe.md
├── idea_generator/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # CLI (generate + expand + pipeline)
│   ├── core.py              # Generation loop, tools, validation
│   ├── research_pipeline.py # Pipeline: lit review -> hypotheses -> feasibility -> direction -> experiment plan -> critique
│   ├── expansion.py         # Hypothesis expansion
│   ├── llm.py               # Multi-provider LLM client
│   ├── prompts.py           # Prompts + expansion prompts
│   ├── validators.py        # JSON schema (incl. References)
│   ├── novelty.py           # Novelty scoring
│   ├── tools/
│   │   ├── base.py
│   │   ├── semantic_scholar.py
│   │   ├── arxiv.py
│   │   ├── pubmed.py
│   │   └── openalex.py
│   └── utils/
│       ├── token_tracker.py
│       └── checkpoint.py
├── docs/
│   └── IMPROVEMENT_PLAN.md
└── examples/
    └── run.sh
```

---

## Supported models

- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `o1`, `o3-mini`, `gpt-5.2`, ...
- **Anthropic**: `claude-3-5-sonnet-*` (direct, Bedrock, Vertex AI)
- **Google**: `gemini-2.0-flash`, `gemini-2.5-*`
- **Ollama**: `ollama/qwen3:*`, `ollama/deepseek-r1:*`, ...
- **Other**: `deepseek-coder-v2-0724`, `llama3.1-405b`, ...

---

## Command summary

```bash
# Research pipeline: full or single phase
idea-generator --topic-file topics/example.md --pipeline
idea-generator --phase literature_review --topic-file topics/example.md
idea-generator --phase hypotheses --from-literature output/example.lit_review.json
idea-generator --phase feasibility_selection --from-hypotheses output/example.hypotheses.json
idea-generator --phase direction --from-literature output/example.lit_review.json --from-hypotheses output/example.hypotheses.json [--from-feasibility output/example.feasibility.json]
idea-generator --phase experiment_plan --from-direction output/example.direction.json
idea-generator --phase critique --from-direction output/example.direction.json [--from-experiment-plan output/example.experiment_plan.json]

# Idea generation (batch of ideas from topic)
idea-generator --topic-file topics/example.md --max-generations 5 --output output/ideas.json
idea-generator --topic-file topics/example.md --output output/ideas.json --resume   # resume

# Hypothesis expansion (from topic or one idea JSON)
idea-generator --topic-file topics/example.md --expand-hypotheses
idea-generator --expand-hypotheses --from-idea-json output/my_idea.json

# Optional: enable PubMed/OpenAlex, config, model
idea-generator --topic-file topics/example.md --pubmed --openalex --config config/default.yaml --model gpt-4o
```

---

## License

Same license as the parent AI Scientist v2 project.
