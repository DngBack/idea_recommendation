# Kế hoạch cải tiến Idea Generator

Tài liệu này mô tả **luồng (flow)** hiện tại của repo và **kế hoạch cải tiến** để:
1. **Gen toàn bộ lý thuyết/giả thuyết mới** từ một ý tưởng (topic)
2. **Trích nguồn (citation) cụ thể** trong mỗi idea
3. **Bổ sung phương pháp search** ngoài Semantic Scholar và arXiv

---

## 1. Luồng (flow) hiện tại của repo

```
Topic (.md) → core.generate_ideas()
    │
    ├─ Đọc topic file (workshop_description)
    ├─ Tạo LLM client (OpenAI/Claude/Gemini/Ollama...)
    ├─ Đăng ký tools: [SemanticScholar, Arxiv?, FinalizeIdea]
    ├─ System prompt: hướng dẫn format ACTION/ARGUMENTS + IDEA JSON
    │
    └─ Vòng lặp: max_generations lần
         │
         └─ Mỗi idea: num_reflections vòng
              │
              ├─ Prompt: IDEA_GENERATION (lần 1) hoặc IDEA_REFLECTION (các lần sau)
              ├─ LLM trả lời → parse ACTION + ARGUMENTS
              ├─ Nếu SearchSemanticScholar / SearchArxiv → gọi tool → last_tool_results
              ├─ Nếu FinalizeIdea → validate schema → (optional) novelty_score → lưu idea
              └─ Checkpoint mỗi checkpoint_interval idea
    │
    └─ Ghi JSON ra output_path
```

**Điểm quan trọng:**
- Mỗi run sinh **một danh sách ideas** (số lượng = `max_generations`), mỗi idea **độc lập** (reflection + search rồi finalize).
- **Related Work** hiện là **text tự do**, không có trường citation chuẩn (author, year, DOI/URL).
- Search chỉ có **2 nguồn**: Semantic Scholar, arXiv.

---

## 2. Mục tiêu cải tiến

| Mục tiêu | Hiện trạng | Mong muốn |
|----------|------------|------------|
| **Gen “tất cả” lý thuyết/giả thuyết** | Gen N idea rời rạc, không có “branch” theo giả thuyết con | Có thể gen **nhiều giả thuyết con** từ một topic, hoặc **mở rộng** (expand) từ một idea thành nhiều biến thể lý thuyết |
| **Citation cụ thể** | Related Work là đoạn văn, không trích nguồn chuẩn | Mỗi idea có **References/Citations** dạng structured (author, year, title, URL/DOI), bắt buộc dựa trên kết quả search |
| **Search đa nguồn** | Chỉ Semantic Scholar + arXiv | Thêm PubMed, OpenAlex, CrossRef, DBLP, (hoặc Google Scholar proxy) và **gộp/rank** kết quả |

---

## 3. Kế hoạch chi tiết

### 3.1. Gen “tất cả” lý thuyết / giả thuyết mới từ một ý tưởng

**Hướng tiếp cận (chọn một hoặc kết hợp):**

1. **Chế độ “hypothesis expansion” (mới)**  
   - **Input:** 1 topic file (như hiện tại) **hoặc** 1 idea đã có (JSON).  
   - **Output:** N **giả thuyết con** (sub-hypotheses) hoặc **biến thể lý thuyết** (variants) từ idea gốc.  
   - **Cách làm:**  
     - Thêm prompt kiểu: “Từ idea/giả thuyết sau, liệt kê 5–10 giả thuyết con hoặc biến thể lý thuyết có thể nghiên cứu độc lập.”  
     - LLM trả về danh sách (Name, Short Hypothesis, one-liner) → sau đó với **từng** giả thuyết con có thể chạy **full pipeline** (search + reflection + finalize) để ra idea đầy đủ.  
   - **Code:** module mới `idea_generator/expansion.py` + CLI flag `--expand-hypotheses` (và optional `--from-idea-json`).

2. **Tăng chất lượng “phủ” từ một topic**  
   - Giữ pipeline hiện tại nhưng:  
     - **System prompt:** yêu cầu LLM “cover diverse angles: theory, algorithms, empirical, negative results, applications”.  
     - **Prev ideas:** đưa vào prompt danh sách idea đã gen để tránh trùng và ép “góc mới”.  
   - Có thể thêm **optional** bước sau khi đủ N idea: “Suggest 3 more *orthogonal* directions” → đưa lại vào queue (nếu muốn gen thêm).

3. **Batch “toàn bộ” giả thuyết**  
   - Sau bước expansion: với mỗi (topic hoặc idea gốc) → list H giả thuyết con → **for each** chạy `generate_ideas()` với topic = mô tả ngắn của giả thuyết đó.  
   - Output: 1 file JSON gồm **nhiều idea** (có thể nhóm theo `source_hypothesis_id` hoặc `parent_idea`).

**Công việc cụ thể:**
- [ ] Thêm `expansion.py`: hàm `expand_hypotheses(topic_text | idea_dict) -> List[dict]`.
- [ ] Thêm prompt `HYPOTHESIS_EXPANSION_PROMPT` (và optional `IDEA_VARIANTS_PROMPT`).
- [ ] CLI: `--expand-hypotheses`, `--from-idea-json`, `--max-sub-hypotheses`.
- [ ] (Tùy chọn) Trong `core.py`: chế độ “generate from multiple seeds” (mỗi seed = một giả thuyết ngắn).

---

### 3.2. Trích nguồn (citation) cụ thể

**Thay đổi schema và prompt:**

1. **Schema (validators.py)**  
   - Thêm trường **`References`** (hoặc `Citations`):  
     - Kiểu: `array of objects` với ít nhất: `author` (string), `year` (string/number), `title` (string), `url` hoặc `doi` (string, optional).  
   - Có thể giữ **Related Work** như đoạn văn, nhưng **yêu cầu** mỗi work được nhắc trong Related Work phải có entry tương ứng trong `References`.

2. **Tool search trả về “citation-ready”**  
   - **Semantic Scholar:** API đã có `title`, `authors`, `year`, `abstract`; bổ sung `url` (e.g. `https://www.semanticscholar.org/paper/...`) và nếu API trả về `externalIds` (DOI) thì đưa vào.  
   - **arXiv:** đã có `url`; thêm field `doi` nếu có trong response.  
   - Format chuỗi trả về cho LLM: thêm dòng “CITE: Author (Year). Title. URL.” để LLM dễ copy vào References.

3. **Prompt**  
   - **FinalizeIdea / IDEA JSON:**  
     - Mô tả rõ: “Related Work phải trích từ các paper bạn đã tìm qua SearchSemanticScholar/SearchArxiv; mỗi nguồn cần có trong References với author, year, title, url (hoặc doi).”  
   - **System prompt:** “Trước khi FinalizeIdea, bạn phải đã gọi ít nhất một lần search; khi viết Related Work, trích nguồn theo format [Author (Year)] và đảm bảo mỗi nguồn có trong References.”

4. **Validation**  
   - (Optional nhưng nên có): Kiểm tra `References` không rỗng khi `Related Work` có độ dài > 0; có thể kiểm tra sơ bộ format (có `author`, `year`, `title`).

**Công việc cụ thể:**
- [ ] `validators.py`: thêm `References` vào schema (array of `{ author, year, title, url?, doi? }`).
- [ ] `prompts.py`: cập nhật FinalizeIdea description và system prompt (citation + References).
- [ ] `tools/semantic_scholar.py`: request thêm fields (url, externalIds); format output có dòng CITE.
- [ ] `tools/arxiv.py`: format output có dòng CITE; thêm doi nếu có.
- [ ] (Tùy chọn) Kiểm tra consistency Related Work ↔ References (số lượng tối thiểu).

---

### 3.3. Phương pháp search khác (đa nguồn)

**Các nguồn đề xuất:**

| Nguồn | API / Cách dùng | Ghi chú |
|-------|------------------|--------|
| **PubMed** | REST API `eutils` | Y học, sinh học, NLP y tế. |
| **OpenAlex** | REST API, free | Bao phủ rộng, có DOI, citations. |
| **CrossRef** | REST API (DOI search) | Tìm theo DOI, title, author. |
| **DBLP** | API / XML | CS, conference papers. |
| **Google Scholar** | Không có API chính thức | Chỉ dùng qua proxy/scraper (legal/ToS risk). |

**Thiết kế:**

1. **Chuẩn hóa output mỗi tool**  
   - Mỗi tool search trả về (nội bộ) list dict với format thống nhất, ví dụ:  
     `title`, `authors`, `year`, `abstract`, `url`, `doi`, `source` (="semantic_scholar" | "arxiv" | "pubmed" | ...).  
   - Hàm `_format()` chung hoặc per-tool nhưng cùng cấu trúc CITE.

2. **Thêm tools mới (cùng interface BaseTool)**  
   - `PubMedSearchTool`: query → PubMed eutils → parse XML/JSON → format.  
   - `OpenAlexSearchTool`: query → OpenAlex API → format.  
   - `CrossRefSearchTool`: (optional) tìm theo title/author.  
   - (DBLP/Google Scholar: sau nếu cần.)

3. **Config**  
   - `config/default.yaml`:  
     - `semantic_scholar_enabled: true`  
     - `arxiv_enabled: true`  
     - `pubmed_enabled: false`  
     - `openalex_enabled: false`  
   - CLI flags: `--no-arxiv`, `--pubmed`, `--openalex`, v.v.

4. **Gộp / xếp hạng (optional)**  
   - Nếu nhiều tools bật: LLM gọi nhiều action (SearchSemanticScholar, SearchArxiv, SearchPubMed, …) trong các reflection.  
   - Hoặc thêm **meta-tool** “SearchLiterature” nhận `query` + `sources: ["semantic_scholar","arxiv","pubmed"]` → gọi từng backend → merge, dedup by title/DOI → sort (e.g. by citation count hoặc year) → trả một block cho LLM.  
   - Merge/dedup có thể làm trong `core.py` hoặc tool `SearchLiterature` mới.

**Công việc cụ thể:**
- [ ] Định nghĩa `CitationRecord` (dataclass hoặc dict) chuẩn: title, authors, year, abstract, url, doi, source.
- [ ] `tools/pubmed.py`: PubMedSearchTool, parse eutils response, map sang CitationRecord + format CITE.
- [ ] `tools/openalex.py`: OpenAlexSearchTool (theo docs OpenAlex).
- [ ] (Tùy chọn) `tools/crossref.py`: CrossRefSearchTool.
- [ ] `core.py`: đăng ký tools theo config (pubmed_enabled, openalex_enabled).
- [ ] `config/default.yaml` + `cli.py`: thêm options cho từng nguồn.
- [ ] (Tùy chọn) Tool `SearchLiterature` gộp nhiều nguồn + dedup.

---

## 4. Thứ tự triển khai đề xuất

1. **Phase 1 – Citation (ngắn hạn)**  
   - Schema References + prompt + format CITE trong S2/arXiv.  
   - Không thêm dependency nặng, dễ kiểm tra.

2. **Phase 2 – Thêm 1–2 search (PubMed, OpenAlex)**  
   - Mở rộng nguồn, LLM có thêm tài liệu để trích dẫn.

3. **Phase 3 – Hypothesis expansion**  
   - Module expansion + CLI + (tùy chọn) chạy full pipeline cho từng giả thuyết con để “gen tất cả lý thuyết/giả thuyết mới” từ một ý tưởng.

4. **Phase 4 (tùy chọn)**  
   - SearchLiterature merge/dedup, CrossRef/DBLP, cải thiện prompt “diverse angles” để phủ tốt hơn từ một topic.

---

## 5. Tóm tắt file cần sửa/tạo

| File | Thay đổi |
|------|----------|
| `idea_generator/validators.py` | Thêm trường `References` (schema). |
| `idea_generator/prompts.py` | Citation + References trong FinalizeIdea & system prompt. |
| `idea_generator/tools/semantic_scholar.py` | Fields url/DOI, format CITE. |
| `idea_generator/tools/arxiv.py` | Format CITE, doi nếu có. |
| `idea_generator/tools/pubmed.py` | **Mới.** PubMedSearchTool. |
| `idea_generator/tools/openalex.py` | **Mới.** OpenAlexSearchTool. |
| `idea_generator/core.py` | Đăng ký tools theo config (pubmed, openalex). |
| `idea_generator/expansion.py` | **Mới.** expand_hypotheses(), prompt expansion. |
| `idea_generator/__main__.py` / `cli.py` | Flags: --expand-hypotheses, --from-idea-json, --pubmed, --openalex. |
| `config/default.yaml` | pubmed_enabled, openalex_enabled. |

Sau khi triển khai, khi bạn có **một ý tưởng** (topic file hoặc idea JSON):
- Hệ thống có thể **expand** thành nhiều giả thuyết con và với mỗi giả thuyết (hoặc với topic) chạy pipeline **search đa nguồn** → **reflection** → **finalize** với **trích nguồn cụ thể** trong References.

Nếu bạn muốn, bước tiếp theo có thể là: triển khai **Phase 1 (citation)** trước (schema + prompt + format CITE trong S2/arXiv).
