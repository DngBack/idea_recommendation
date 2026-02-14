# Idea Generator

A **standalone** AI research idea generator, inspired by the ideation pipeline of [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2). This package generates high-quality, novel research ideas from a topic description, with optional **literature search** (Semantic Scholar, arXiv, PubMed, OpenAlex), **structured citations (References)**, and **hypothesis expansion** to derive multiple sub-hypotheses from one idea.

---

## Key Features

- **End-to-end idea generation**: From a Markdown topic file to a structured JSON list of research proposals.
- **Multi-model support**: OpenAI (GPT-4o, o1, o3-mini), Anthropic Claude, Gemini, Ollama (Qwen, DeepSeek, ...), and more.
- **Literature search (4 sources)**:
  - **Semantic Scholar** – general CS/ML (default on)
  - **arXiv** – preprints (default on)
  - **PubMed** – medicine, biology (optional: `--pubmed` or `pubmed_enabled: true`)
  - **OpenAlex** – broad coverage, DOI/citations (optional: `--openalex` or `openalex_enabled: true`)
- **Structured citations**: Each idea can include a **References** array (author, year, title, url/doi). Search results return **CITE** lines for the LLM to copy into References.
- **Hypothesis expansion**: From one topic or one idea JSON, generate a list of **sub-hypotheses** or theory variants (`--expand-hypotheses`, optional `--from-idea-json`).
- **JSON schema validation**: Every idea is validated; invalid ideas get an auto-fix prompt.
- **Novelty scoring** (optional): LLM-based novelty rating (0.0 – 1.0) per idea.
- **Checkpoint / Resume**: Long runs can be interrupted and resumed.
- **YAML config + CLI**: Configure via `config/default.yaml` with full CLI override.

---

## Quick Start

### 1. Install

```bash
cd idea_recommendation   # or your repo root
pip install -e .
```

Or install dependencies only:

```bash
pip install -r requirements.txt
```

### 2. Set API Keys and optional env

```bash
# Required for most models (OpenAI)
export OPENAI_API_KEY="sk-..."

# Optional – Semantic Scholar (higher rate limits)
export S2_API_KEY="..."

# Optional – Anthropic
export ANTHROPIC_API_KEY="..."

# Optional – Gemini
export GEMINI_API_KEY="..."

# Optional – OpenAlex (polite pool, faster responses)
export OPENALEX_MAILTO="your@email.com"
```

### 3. Run idea generation

```bash
# Basic run
idea-generator --topic-file topics/example_icbinb.md --model gpt-4o-2024-05-13 --max-generations 5

# With config file and custom output
idea-generator --topic-file topics/example_icbinb.md --config config/default.yaml --output output/my_ideas.json

# As Python module
python -m idea_generator --topic-file topics/example_icbinb.md --num-reflections 3
```

### 4. Resume a previous run

```bash
idea-generator --topic-file topics/example_icbinb.md --output output/my_ideas.json --resume
```

---

## Hướng dẫn chi tiết (Detailed guide)

### Cấu trúc file topic (Topic file format)

Topic là file Markdown (`.md`) mô tả hướng nghiên cứu. Ví dụ:

```markdown
# Title: My Research Topic
## Keywords
keyword1, keyword2
## TL;DR
One sentence summary.
## Abstract
Longer description: background, goals, expected contributions, evaluation plan.
```

- **Title / Keywords / TL;DR / Abstract** giúp LLM nắm context và sinh idea phù hợp.
- Đường dẫn: `--topic-file path/to/topic.md`.

### Sinh ý tưởng (Generate ideas)

1. **Chỉ định topic và số idea:**
   ```bash
   idea-generator --topic-file topics/gan_optimization_adoe.md --max-generations 5
   ```

2. **Dùng file config:**  
   Mặc định đọc `config/default.yaml` nếu có `--config`:
   ```bash
   idea-generator --topic-file topics/example_icbinb.md --config config/default.yaml
   ```

3. **Tắt/bật search:**
   - Tắt arXiv: `--no-arxiv`
   - Bật PubMed: `--pubmed`
   - Bật OpenAlex: `--openalex`

4. **Validation và novelty:**
   - Tắt kiểm tra schema: `--no-validate`
   - Bật chấm novelty: `--novelty-scoring` (có thể chỉ định `--novelty-model`).

5. **Output:**  
   Mặc định ghi ra `<topic-file-base>.json` (ví dụ `topics/example_icbinb.json`). Đổi đường dẫn: `--output output/ideas.json`.

### Trích nguồn (Citations / References)

- Mỗi idea có thể có trường **References** (mảng object): `author`, `year`, `title`, `url` hoặc `doi`.
- LLM được yêu cầu gọi ít nhất một lần search trước khi finalize và điền References từ các dòng **CITE** trong kết quả search.
- Trong **Related Work**, nguồn trích dẫn theo dạng `[Author (Year)]` và phải có entry tương ứng trong **References**.

### Công cụ tìm kiếm (Literature search tools)

| Tool                 | Mặc định | Bật/tắt                    | Ghi chú                          |
|----------------------|----------|-----------------------------|-----------------------------------|
| Semantic Scholar     | Bật      | Luôn bật                    | CS/ML, cần `S2_API_KEY` (tùy chọn) |
| arXiv                | Bật      | `--no-arxiv` để tắt         | Preprints                         |
| PubMed               | Tắt      | `--pubmed` hoặc YAML        | Y học, sinh học                   |
| OpenAlex             | Tắt      | `--openalex` hoặc YAML      | Bao phủ rộng, DOI; `OPENALEX_MAILTO` tùy chọn |

Ví dụ bật thêm PubMed và OpenAlex:

```bash
idea-generator --topic-file topics/example_icbinb.md --pubmed --openalex
```

Hoặc trong `config/default.yaml`:

```yaml
pubmed_enabled: true
openalex_enabled: true
```

### Mở rộng giả thuyết (Hypothesis expansion)

Từ **một topic** hoặc **một idea (JSON)** có thể sinh ra nhiều **giả thuyết con** (sub-hypotheses) dạng JSON, sau đó có thể dùng từng giả thuyết làm input cho pipeline sinh idea đầy đủ.

**1. Expansion từ topic file:**

```bash
idea-generator --topic-file topics/gan_optimization_adoe.md --expand-hypotheses
```

- Đọc nội dung file topic, gọi LLM một lần để sinh 5–10 giả thuyết con.
- Output mặc định: `output/<topic-base>.hypotheses.json` (hoặc thư mục trong `output_dir` của config).
- Chỉ định file output: `--output path/to/hypotheses.json`.

**2. Expansion từ một idea (file JSON):**

```bash
idea-generator --expand-hypotheses --from-idea-json path/to/idea.json
```

- `idea.json` có thể là **một object** (một idea) hoặc **mảng** (sẽ lấy phần tử đầu).
- Object idea cần ít nhất `Title` và `Short Hypothesis`.
- Output: `output/<idea-file-base>.hypotheses.json` trừ khi dùng `--output`.

**3. Giới hạn số giả thuyết con:**

```bash
idea-generator --topic-file topics/example.md --expand-hypotheses --max-sub-hypotheses 8
```

**4. Kết hợp model và config:**

```bash
idea-generator --topic-file topics/example.md --expand-hypotheses --config config/default.yaml --model gpt-4o
```

**Định dạng file hypotheses:** Mảng JSON, mỗi phần tử có ít nhất:

- `Name`: định danh ngắn (lowercase, underscore).
- `Short Hypothesis`: một hoặc hai câu mô tả giả thuyết.

Ví dụ:

```json
[
  { "Name": "adaptive_damping_ablation", "Short Hypothesis": "We hypothesize that..." },
  { "Name": "rotation_proxy_comparison", "Short Hypothesis": "..." }
]
```

Bạn có thể dùng từng item làm mô tả topic (ví dụ ghi ra file .md) rồi chạy `idea-generator --topic-file ...` để sinh idea đầy đủ cho từng giả thuyết.

---

## Configuration

Cấu hình qua `config/default.yaml`; mọi giá trị có thể ghi đè bằng CLI.

| Setting               | Default       | CLI Flag               | Mô tả |
|-----------------------|---------------|------------------------|--------|
| `model`               | `gpt-5.2`     | `--model`               | Model LLM dùng để sinh idea |
| `max_generations`     | `3`           | `--max-generations`     | Số idea sinh ra mỗi lần chạy |
| `num_reflections`     | `5`           | `--num-reflections`     | Số vòng reflection cho mỗi idea |
| `output_dir`          | `output`      | –                       | Thư mục output (khi dùng config) |
| `validate`            | `true`        | `--no-validate`         | Bật/tắt kiểm tra schema JSON |
| `novelty_scoring`     | `false`       | `--novelty-scoring`     | Bật chấm điểm novelty |
| `novelty_model`       | (cùng `model`)| `--novelty-model`       | Model dùng cho novelty |
| `checkpoint_interval` | `1`           | –                       | Ghi checkpoint mỗi N idea |
| `arxiv_enabled`       | `true`        | `--no-arxiv`            | Bật/tắt search arXiv |
| `pubmed_enabled`      | `false`       | `--pubmed`              | Bật/tắt search PubMed |
| `openalex_enabled`    | `false`       | `--openalex`            | Bật/tắt search OpenAlex |
| `resume`              | `false`       | `--resume`              | Resume từ checkpoint |
| `system_prompt_override` | `""`        | –                       | Ghi đè toàn bộ system prompt (để trống = dùng mặc định) |

---

## Output format (Định dạng output)

File JSON là **mảng** các idea. Mỗi idea có dạng:

```json
[
  {
    "Name": "my_idea_name",
    "Title": "An Interesting Research Title",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "References": [
      { "author": "Author et al.", "year": "2023", "title": "Paper Title", "url": "https://..." }
    ],
    "Abstract": "...",
    "Experiments": ["...", "..."],
    "Risk Factors and Limitations": ["...", "..."],
    "novelty_score": 0.75
  }
]
```

- **References**: có thể có hoặc không (optional). Nếu có, mỗi nguồn trích trong Related Work nên có entry tương ứng.
- **novelty_score**: chỉ xuất hiện khi bật `--novelty-scoring`.

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
│   ├── cli.py              # CLI (generate + expand)
│   ├── core.py             # Generation loop, tools, validation
│   ├── expansion.py        # Hypothesis expansion
│   ├── llm.py              # Multi-provider LLM client
│   ├── prompts.py          # Prompts + expansion prompts
│   ├── validators.py       # JSON schema (incl. References)
│   ├── novelty.py          # Novelty scoring
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

## Tóm tắt lệnh thường dùng

```bash
# Sinh N idea từ topic
idea-generator --topic-file topics/example.md --max-generations 5

# Bật thêm PubMed + OpenAlex
idea-generator --topic-file topics/example.md --pubmed --openalex

# Chỉ sinh danh sách giả thuyết con từ topic
idea-generator --topic-file topics/example.md --expand-hypotheses --output output/hypotheses.json

# Sinh giả thuyết con từ một idea đã có (file JSON)
idea-generator --expand-hypotheses --from-idea-json output/my_idea.json

# Resume sau khi bị gián đoạn
idea-generator --topic-file topics/example.md --output output/ideas.json --resume
```

---

## License

Same license as the parent AI Scientist v2 project.
