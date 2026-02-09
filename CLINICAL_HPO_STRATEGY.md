# Strategy: Clinical Case → HPO Term Matching

## The core problem

Searching with **raw clinical narrative** against indexed HPO terms fails because:

- **Clinical language ≠ HPO terminology** (e.g. "super-morbidly obese" vs "Severe obesity" HP:0001513).
- **Narrative context drowns signal** (demographics, procedures, family history dilute phenotype terms).
- **No semantic bridge**: embeddings trained on general text may not map clinical phrasing to ontology labels.

So we must **not** rely on vector search alone for clinical→HPO. Use it as a **supplement**; make **keyword/ID search the backbone**.

---

## Two-stage strategy

### Stage 1: Clinical NER + HPO mapping

1. **Extract phenotypes** from the narrative:
   - Pull out distinct phenotypic observations (symptoms, physical findings, test results, morphology).
   - Strip demographics, procedures, family-history context.
   - Output: structured list of clinical feature phrases.

2. **Map clinical terms → HPO concepts** using:
   - **HPO synonym/label matching** (name, exact_synonyms in index).
   - **Semantic similarity** (embeddings) for expansion when exact match fails.
   - **Parent-term traversal** (if we have hierarchy: fall back to parent HPO terms).

Example mappings:

| Clinical phrase           | HPO concept / ID        |
|---------------------------|-------------------------|
| super-morbid obesity      | Severe obesity (HP:0001513) |
| fundic gland polyps       | Gastric polyp (HP:0100751)  |
| tubular adenoma (colon)   | Colonic polyps (HP:0100821)  |
| Barrett's oesophagus      | Barrett esophagus (HP:0004395) |
| mesenteric mass, desmoid  | Desmoid tumor (HP:0100244)   |

### Stage 2: Weighted Meilisearch query

- **Query with HPO IDs or standardized HPO labels**, not raw narrative.
- **Weight rare/specific phenotypes higher** (e.g. desmoid tumor >> obesity).
- **Filter-then-rank**: must-have (core syndrome features) vs nice-to-have (common/variable).

---

## Why raw text + vector is insufficient

Syndromes (e.g. APC-associated polyposis) are identified by **constellations** of findings. The syndrome name often does **not** appear in the case. Meilisearch keyword/vector on raw text:

- Misses mappings like "fundic gland polyps" → Gastric polyp (HP:0100751).
- Cannot weight "desmoid" over "obesity" for syndrome relevance.
- Context and narrative structure break simple matching.

So the pipeline must: **extract → map → query with HPO concepts**, and use **keyword + optional semantic expansion** (vector as supplement, not primary).

---

## Immediate action plan

| Step | Action |
|------|--------|
| 1 | **Phenotype extraction** – Pipeline: clinical text → structured phenotype list (placeholder in `app/clinical_hpo.py`; LLM/NLP to be plugged in). |
| 2 | **HPO mapping layer** – Phenotype list → HPO term IDs/labels (synonym match, then semantic, then parent traversal if available). |
| 3 | **Restructure search** – Query Meilisearch with HPO IDs/labels (and optionally joined phenotype phrases), not raw case text. |
| 4 | **Weighting** – Rare/specific features >> common features (scoring or filter-then-rank). |
| 5 | **Hybrid** – Keyword/ID search as backbone; vector for synonym-like expansion only; do not rely on vector alone for clinical→HPO. |

---

## Implementation notes (codebase)

- **`app/clinical_hpo.py`** – `extract_phenotypes()` (placeholder) and `clinical_to_hpo_search_query()`; later: LLM extraction, mapping table or HPO synonym API.
- **Search path** – Optional mode: extract phenotypes → build query from HPO IDs/labels → call `search_hpo()` with that query; vector remains optional in `hpo.search_hpo()`.
- **Index** – Continue to index HPO terms with name, definition, synonyms_str, and vectors for hybrid search; mapping layer uses the same index for synonym + semantic lookup.
