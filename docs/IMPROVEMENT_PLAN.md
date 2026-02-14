# Idea Generator Improvement Plan

This document describes the **current flow** of the repo and the **improvement plan** to:
1. **Generate full theory/hypotheses** from a single idea (topic)
2. **Concrete citations** in each idea
3. **Additional search methods** beyond Semantic Scholar and arXiv

---

## 1. Current repo flow

```
Topic (.md) → core.generate_ideas()
    │
    ├─ Read topic file (workshop_description)
    ├─ Create LLM client (OpenAI/Claude/Gemini/Ollama...)
    ├─ Register tools: [SemanticScholar, Arxiv?, FinalizeIdea]
    ├─ System prompt: ACTION/ARGUMENTS format + IDEA JSON
    │
    └─ Loop: max_generations times
         │
         └─ Per idea: num_reflections rounds
              │
              ├─ Prompt: IDEA_GENERATION (first) or IDEA_REFLECTION (later)
              ├─ LLM response → parse ACTION + ARGUMENTS
              ├─ If SearchSemanticScholar / SearchArxiv → call tool → last_tool_results
              ├─ If FinalizeIdea → validate schema → (optional) novelty_score → save idea
              └─ Checkpoint every checkpoint_interval ideas
    │
    └─ Write JSON to output_path
```

**Key points:**
- Each run produces **one list of ideas** (count = `max_generations`); each idea is **independent** (reflection + search then finalize).
- **Related Work** is currently **free text**, with no standard citation fields (author, year, DOI/URL).
- Search has only **2 sources**: Semantic Scholar, arXiv.

---

## 2. Improvement goals

| Goal | Current | Desired |
|------|---------|---------|
| **Generate “all” theory/hypotheses** | Generate N separate ideas, no “branch” by sub-hypothesis | Can generate **multiple sub-hypotheses** from one topic, or **expand** from one idea into many theory variants |
| **Concrete citations** | Related Work is prose, no standard citations | Each idea has **References/Citations** (author, year, title, URL/DOI), required to be based on search results |
| **Multi-source search** | Only Semantic Scholar + arXiv | Add PubMed, OpenAlex, CrossRef, DBLP (or Google Scholar proxy) and **merge/rank** results |

---

## 3. Detailed plan

### 3.1. Generate “all” theory / new hypotheses from one idea

**Approach (choose one or combine):**

1. **“Hypothesis expansion” mode (new)**  
   - **Input:** 1 topic file (as now) **or** 1 existing idea (JSON).  
   - **Output:** N **sub-hypotheses** or **theory variants** from the original idea.  
   - **Implementation:**  
     - Add a prompt like: “From the following idea/hypothesis, list 5–10 sub-hypotheses or theory variants that can be researched independently.”  
     - LLM returns a list (Name, Short Hypothesis, one-liner) → then for **each** sub-hypothesis you can run the **full pipeline** (search + reflection + finalize) to get a full idea.  
   - **Code:** new module `idea_generator/expansion.py` + CLI flag `--expand-hypotheses` (and optional `--from-idea-json`).

2. **Improve “coverage” from one topic**  
   - Keep current pipeline but:  
     - **System prompt:** ask LLM to “cover diverse angles: theory, algorithms, empirical, negative results, applications”.  
     - **Prev ideas:** pass the list of already-generated ideas into the prompt to avoid duplicates and encourage “new angles”.  
   - Optionally add a step after N ideas: “Suggest 3 more *orthogonal* directions” → feed back into the queue (if you want to generate more).

3. **Batch “all” hypotheses**  
   - After expansion: for each (topic or root idea) → list H sub-hypotheses → **for each** run `generate_ideas()` with topic = short description of that hypothesis.  
   - Output: 1 JSON file with **many ideas** (optionally grouped by `source_hypothesis_id` or `parent_idea`).

**Concrete tasks:**
- [ ] Add `expansion.py`: function `expand_hypotheses(topic_text | idea_dict) -> List[dict]`.
- [ ] Add prompt `HYPOTHESIS_EXPANSION_PROMPT` (and optional `IDEA_VARIANTS_PROMPT`).
- [ ] CLI: `--expand-hypotheses`, `--from-idea-json`, `--max-sub-hypotheses`.
- [ ] (Optional) In `core.py`: “generate from multiple seeds” mode (each seed = one short hypothesis).

---

### 3.2. Concrete citations

**Schema and prompt changes:**

1. **Schema (validators.py)**  
   - Add **`References`** (or `Citations`) field:  
     - Type: `array of objects` with at least: `author` (string), `year` (string/number), `title` (string), `url` or `doi` (string, optional).  
   - Keep **Related Work** as prose, but **require** that every work mentioned in Related Work has a corresponding entry in `References`.

2. **Search tools return “citation-ready” output**  
   - **Semantic Scholar:** API already has `title`, `authors`, `year`, `abstract`; add `url` (e.g. `https://www.semanticscholar.org/paper/...`) and if API returns `externalIds` (DOI) include it.  
   - **arXiv:** already has `url`; add `doi` field if present in response.  
   - String format for LLM: add line “CITE: Author (Year). Title. URL.” so the LLM can copy into References.

3. **Prompts**  
   - **FinalizeIdea / IDEA JSON:**  
     - State clearly: “Related Work must cite papers you found via SearchSemanticScholar/SearchArxiv; each source must appear in References with author, year, title, url (or doi).”  
   - **System prompt:** “Before FinalizeIdea you must have called search at least once; when writing Related Work, cite as [Author (Year)] and ensure each source is in References.”

4. **Validation**  
   - (Optional but recommended): Check that `References` is not empty when `Related Work` has length > 0; basic format check (has `author`, `year`, `title`).

**Concrete tasks:**
- [ ] `validators.py`: add `References` to schema (array of `{ author, year, title, url?, doi? }`).
- [ ] `prompts.py`: update FinalizeIdea description and system prompt (citation + References).
- [ ] `tools/semantic_scholar.py`: request extra fields (url, externalIds); format output with CITE line.
- [ ] `tools/arxiv.py`: format output with CITE line; add doi if present.
- [ ] (Optional) Check consistency Related Work ↔ References (minimum count).

---

### 3.3. Other search methods (multi-source)

**Suggested sources:**

| Source | API / Usage | Notes |
|--------|-------------|-------|
| **PubMed** | REST API `eutils` | Medicine, biology, medical NLP. |
| **OpenAlex** | REST API, free | Broad coverage, DOI, citations. |
| **CrossRef** | REST API (DOI search) | Search by DOI, title, author. |
| **DBLP** | API / XML | CS, conference papers. |
| **Google Scholar** | No official API | Only via proxy/scraper (legal/ToS risk). |

**Design:**

1. **Normalize each tool’s output**  
   - Each search tool returns (internally) a list of dicts with a unified format, e.g.:  
     `title`, `authors`, `year`, `abstract`, `url`, `doi`, `source` (="semantic_scholar" | "arxiv" | "pubmed" | ...).  
   - Shared `_format()` or per-tool but same CITE structure.

2. **Add new tools (same BaseTool interface)**  
   - `PubMedSearchTool`: query → PubMed eutils → parse XML/JSON → format.  
   - `OpenAlexSearchTool`: query → OpenAlex API → format.  
   - `CrossRefSearchTool`: (optional) search by title/author.  
   - (DBLP/Google Scholar: later if needed.)

3. **Config**  
   - `config/default.yaml`:  
     - `semantic_scholar_enabled: true`  
     - `arxiv_enabled: true`  
     - `pubmed_enabled: false`  
     - `openalex_enabled: false`  
   - CLI flags: `--no-arxiv`, `--pubmed`, `--openalex`, etc.

4. **Merge / rank (optional)**  
   - If multiple tools are enabled: LLM calls multiple actions (SearchSemanticScholar, SearchArxiv, SearchPubMed, …) across reflections.  
   - Or add a **meta-tool** “SearchLiterature” that takes `query` + `sources: ["semantic_scholar","arxiv","pubmed"]` → call each backend → merge, dedup by title/DOI → sort (e.g. by citation count or year) → return one block to the LLM.  
   - Merge/dedup can live in `core.py` or a new `SearchLiterature` tool.

**Concrete tasks:**
- [ ] Define standard `CitationRecord` (dataclass or dict): title, authors, year, abstract, url, doi, source.
- [ ] `tools/pubmed.py`: PubMedSearchTool, parse eutils response, map to CitationRecord + CITE format.
- [ ] `tools/openalex.py`: OpenAlexSearchTool (per OpenAlex docs).
- [ ] (Optional) `tools/crossref.py`: CrossRefSearchTool.
- [ ] `core.py`: register tools from config (pubmed_enabled, openalex_enabled).
- [ ] `config/default.yaml` + `cli.py`: add options per source.
- [ ] (Optional) SearchLiterature tool that merges multiple sources + dedup.

---

## 4. Suggested implementation order

1. **Phase 1 – Citation (short term)**  
   - References schema + prompts + CITE format in S2/arXiv.  
   - No heavy new dependencies, easy to verify.

2. **Phase 2 – Add 1–2 search (PubMed, OpenAlex)**  
   - Broaden sources; LLM has more literature to cite.

3. **Phase 3 – Hypothesis expansion**  
   - Expansion module + CLI + (optional) run full pipeline per sub-hypothesis to “generate all theory/hypotheses” from one idea.

4. **Phase 4 (optional)**  
   - SearchLiterature merge/dedup, CrossRef/DBLP, improve “diverse angles” prompt for better coverage from one topic.

---

## 5. Summary of files to add/change

| File | Change |
|------|--------|
| `idea_generator/validators.py` | Add `References` field (schema). |
| `idea_generator/prompts.py` | Citation + References in FinalizeIdea & system prompt. |
| `idea_generator/tools/semantic_scholar.py` | Url/DOI fields, CITE format. |
| `idea_generator/tools/arxiv.py` | CITE format, doi if present. |
| `idea_generator/tools/pubmed.py` | **New.** PubMedSearchTool. |
| `idea_generator/tools/openalex.py` | **New.** OpenAlexSearchTool. |
| `idea_generator/core.py` | Register tools from config (pubmed, openalex). |
| `idea_generator/expansion.py` | **New.** expand_hypotheses(), expansion prompt. |
| `idea_generator/__main__.py` / `cli.py` | Flags: --expand-hypotheses, --from-idea-json, --pubmed, --openalex. |
| `config/default.yaml` | pubmed_enabled, openalex_enabled. |

After implementation, when you have **one idea** (topic file or idea JSON):
- The system can **expand** it into multiple sub-hypotheses and for each hypothesis (or for the topic) run the **multi-source search** → **reflection** → **finalize** pipeline with **concrete citations** in References.

If you like, the next step can be implementing **Phase 1 (citation)** first (schema + prompt + CITE format in S2/arXiv).
