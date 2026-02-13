# Idea Generator

A **standalone** AI research idea generator, inspired by the ideation pipeline of [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2). This package focuses exclusively on generating high-quality, novel research ideas from a topic description -- no experiment execution, writeup, or review pipeline included.

## Key Features

- **End-to-end idea generation**: From a Markdown topic file to a structured JSON list of research proposals.
- **Multi-model support**: OpenAI (GPT-4o, o1, o3-mini), Anthropic Claude (direct, Bedrock, Vertex AI), Gemini, Ollama (Qwen, DeepSeek, ...), and more.
- **Literature search tools**: Semantic Scholar + arXiv (new) for grounding ideas in existing work.
- **JSON schema validation**: Every generated idea is validated before acceptance; invalid ideas get a second chance via an auto-fix prompt.
- **Novelty scoring** (optional): LLM-based novelty rating (0.0 – 1.0) for each idea.
- **Checkpoint / Resume**: Long runs can be interrupted and resumed seamlessly.
- **YAML config + CLI**: Flexible configuration via a YAML file with full CLI override support.
- **Proper logging**: Uses Python `logging` instead of raw `print` statements.

## Quick Start

### 1. Install

```bash
cd Des
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
export OPENAI_API_KEY="sk-..."

# Optional – for Semantic Scholar (higher rate limits)
export S2_API_KEY="..."

# Optional – for Anthropic models
export ANTHROPIC_API_KEY="..."

# Optional – for Gemini
export GEMINI_API_KEY="..."
```

### 3. Run

```bash
# Using the CLI entry-point (after pip install -e .)
idea-generator \
    --topic-file topics/example_icbinb.md \
    --model gpt-4o-2024-05-13 \
    --max-generations 5 \
    --num-reflections 3

# Or as a Python module
python -m idea_generator \
    --topic-file topics/example_icbinb.md \
    --config config/default.yaml \
    --output output/my_ideas.json
```

### 4. Resume a Previous Run

```bash
idea-generator \
    --topic-file topics/example_icbinb.md \
    --output output/my_ideas.json \
    --resume
```

## Configuration

All settings can be provided via `config/default.yaml` and overridden by CLI flags.

| Setting              | Default                  | CLI Flag              | Description                                      |
|----------------------|--------------------------|-----------------------|--------------------------------------------------|
| `model`              | `gpt-4o-2024-05-13`     | `--model`             | LLM model for idea generation                    |
| `max_generations`    | `20`                     | `--max-generations`   | Number of ideas to generate                      |
| `num_reflections`    | `5`                      | `--num-reflections`   | Reflection rounds per idea                       |
| `validate`           | `true`                   | `--no-validate`       | JSON schema validation                           |
| `novelty_scoring`    | `false`                  | `--novelty-scoring`   | Enable LLM-based novelty scoring                 |
| `novelty_model`      | (same as `model`)        | `--novelty-model`     | Model for novelty scoring                        |
| `arxiv_enabled`      | `true`                   | `--no-arxiv`          | Enable arXiv search tool                         |
| `checkpoint_interval`| `1`                      | –                     | Save checkpoint every N ideas                    |
| `resume`             | `false`                  | `--resume`            | Resume from checkpoint                           |

## Output Format

The output is a JSON array of idea objects:

```json
[
  {
    "Name": "my_idea_name",
    "Title": "An Interesting Research Title",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": ["...", "..."],
    "Risk Factors and Limitations": ["...", "..."],
    "novelty_score": 0.75
  }
]
```

The `novelty_score` field is only present when `--novelty-scoring` is enabled.

## Project Structure

```
Des/
├── README.md
├── requirements.txt
├── pyproject.toml
├── config/
│   └── default.yaml
├── topics/                     # Example topic files
│   ├── example_icbinb.md
│   └── example_ml_general.md
├── idea_generator/             # Python package
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                  # CLI entry point
│   ├── core.py                 # Main generation logic
│   ├── llm.py                  # Multi-provider LLM client
│   ├── prompts.py              # All prompt templates
│   ├── validators.py           # JSON schema validation
│   ├── novelty.py              # Novelty scoring
│   ├── tools/
│   │   ├── base.py             # Abstract tool base class
│   │   ├── semantic_scholar.py # Semantic Scholar search
│   │   └── arxiv.py            # arXiv search (new)
│   └── utils/
│       ├── token_tracker.py    # Token usage tracking
│       └── checkpoint.py       # Checkpoint / resume
└── examples/
    └── run.sh
```

## Supported Models

All models from AI Scientist v2 are supported:

- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `o1`, `o3-mini`, ...
- **Anthropic**: `claude-3-5-sonnet-*` (direct, Bedrock, Vertex AI)
- **Google**: `gemini-2.0-flash`, `gemini-2.5-*`
- **Ollama**: `ollama/qwen3:*`, `ollama/deepseek-r1:*`, `ollama/gpt-oss:*`, ...
- **Other**: `deepseek-coder-v2-0724`, `deepcoder-14b`, `llama3.1-405b`

## Differences from AI Scientist v2 Ideation

| Aspect             | AI Scientist v2                | Idea Generator (this)            |
|--------------------|--------------------------------|----------------------------------|
| Structure          | Single file, imports ai_scientist | Standalone package              |
| Config             | CLI args only                  | YAML config + CLI override       |
| Validation         | None                           | JSON schema validation           |
| Novelty scoring    | None                           | Optional LLM-based scoring       |
| Checkpoint/Resume  | None                           | Built-in                         |
| Search tools       | Semantic Scholar only          | + arXiv                          |
| Logging            | `print()`                      | Python `logging` module          |

## License

Same license as the parent AI Scientist v2 project.
