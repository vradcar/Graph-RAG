# T1-Sai Research: Multi-PDF Corpus & Cross-Doc GraphRAG Patterns

**Milestone:** v2.0 T1-Sai — harden ingestion across 3–5 additional Honeywell HVAC PDFs.
**Schema is frozen** (Product, Accessory, WiringConfig, HVACSystemType, Spec; COMPATIBLE_WITH, REPLACES, SUPPORTS_WIRING, HAS_SPEC). Every recommendation here adapts to that schema rather than expanding it.
**Researched:** 2026-05-02. Confidence overall: MEDIUM-HIGH.

---

## 1. Recommended PDF Corpus

Selection rule: each candidate must (a) fit the existing 5-kind / 4-relation schema and (b) share at least one entity with the T9 corpus so cross-document edges actually form. The shared anchors in the T9 manual are: `uwp-wallplate`, `wireless-room-sensor` (C7189R), `c-wire`, `heat-pump`, `conventional`, `24vac`, terminal letters R/W/Y/G/C, and `redlink` accessory family.

| # | Product | Doc # / URL Pattern | Why it composes with T9 | Expected entities |
|---|---------|--------------------|-------------------------|-------------------|
| 1 | **T6 Pro Smart Thermostat (TH6320WF2003)** | Resideo `33-00392EFS.pdf`, `33-00410EFS.pdf` under `customer.resideo.com/resources/Techlit/TechLitDocuments/33-00000s/` | T9 (`rcht9610wf`) **REPLACES TH6320WF** is already an extracted edge — onboarding the source manual closes the chain. Same UWP wallplate, same C-wire, same conventional/heat-pump split. | Product `th6320wf2003`; Accessory `uwp-wallplate` (shared); WiringConfig `c-wire`, `r-w-y-g-c-5-wire`; HVACSystemType `conventional`, `heat-pump`; Specs 24VAC. |
| 2 | **T6 Pro Z-Wave (TH6320ZW2003)** | Resideo `33-00587EFS.pdf`, `33-00588EFS.pdf` | Sibling of #1 — produces sibling Product nodes that share the wiring/HVAC subgraph but differ on accessory (Z-Wave hub vs RedLINK). Demonstrates accessory-driven differentiation. | Product `th6320zw2003`; Accessory `z-wave-hub`; reuses wiring + HVAC nodes. |
| 3 | **T10 / T10+ Pro Smart Thermostat (THX321WFS2001W)** | Resideo `33-00423EFS.pdf` (install), `33-00428.pdf` (user), `33-00462.pdf` (data) | Same RedLINK 3.0 family as T9 — **shares `wireless-room-sensor` (C7189R1004)** node, same UWP wallplate, same C-wire requirement. T10 supports up to 20 sensors — gives a richer COMPATIBLE_WITH fan-out off the shared sensor accessory. Ideal multi-hop test case ("which thermostats accept the C7189R sensor?"). | Product `thx321wfs2001w`; Accessory `wireless-room-sensor`, `uwp-wallplate`, `redlink-3` (shared); WiringConfig + HVAC nodes (shared). |
| 4 | **THP9045A1098 C-Wire Adapter** | Resideo `33-00342` / mirrored at `jacksonsystems.com/.../THP9045A1098-Installation-Manual.pdf`; older module THP9045A1023 at Resideo `69-2065EFS.pdf` | The T9 normalizer already treats `c-wire` as a WiringConfig. This PDF **defines** the adapter Accessory that resolves the missing-C-wire failure mode. Creates COMPATIBLE_WITH edges from T9, T6, T10, RTH9585 → `thp9045-c-wire-adapter`. Pure cross-doc value — one PDF, many edges. | Product/Accessory `thp9045a1098`; WiringConfig `c-wire`, `g-relabeled-c`, `4-wire-no-c`. |
| 5 | **HZ322 TrueZONE Zone Panel** | Resideo `69-2199.pdf` | Introduces zoning as an HVACSystemType + a controller Product. T6/T9/T10 manuals all reference zoning compatibility; this PDF is the canonical source. Validates that the schema scales beyond one-thermostat-per-system. | Product `hz322`; HVACSystemType `zoned-conventional`, `zoned-heat-pump`; WiringConfig (3-zone wiring); Accessory `c7189u-zone-sensor`. |
| 6 | **THM6000R7001 RedLINK Internet Gateway** | Resideo `33-00250EFS.pdf` (install), `33-00251EFS.pdf` (operating) | Accessory shared by T9, T10, VisionPRO 8000 family. One node, several inbound COMPATIBLE_WITH edges — the canonical demo of "this fact only emerges when 3 PDFs are in the graph at once." | Accessory `thm6000r7001`; Specs (Ethernet, 120VAC PSU). |
| 7 | **RTH9585WF1004 Wi-Fi Color Touchscreen** | Resideo `33-00269EF.pdf` (digitalassets.resideo.com mirror) | Consumer-line Wi-Fi sibling to T9 — same R/W/Y/G/C terminal vocabulary, same heat-pump/conventional split, but **no UWP wallplate** (different accessory family). Tests that the extractor doesn't hallucinate the UWP edge for non-UWP products. | Product `rth9585wf1004`; reuses HVAC + 24VAC specs; Accessory differs (no UWP). |
| 8 (stretch) | **FocusPRO TH6000 Series (TH6320WF02)** | Resideo `69-2736EFS.pdf` (FCC mirror at fcc.report), Resideo `69-2695EFS.pdf` | Predecessor line to T6 Pro — produces additional REPLACES chain links. Useful for the "long replacement chain" eval query. | Product `th6320wf02`; REPLACES → older TH6 series. |

**Recommended ingest set (5 PDFs):** #1, #3, #4, #5, #6. This combination guarantees:
- ≥1 REPLACES cross-doc edge (T9 → T6 Pro doc).
- ≥1 shared Accessory node with 3+ inbound edges (RedLINK gateway, wireless room sensor).
- ≥1 shared WiringConfig with adapter resolution path (c-wire ↔ THP9045).
- A non-thermostat Product (HZ322) to prove the schema generalizes.

**Source pattern note:** the canonical host is `https://customer.resideo.com/resources/Techlit/TechLitDocuments/{prefix}-00000s/{docnum}.pdf`. `33-00xxx` are the modern Honeywell Home docs; `69-xxxx` are the older "PRO" series docs. Anything not on Resideo should be sourced from `manuals.plus`, `manualslib.com`, or distributor mirrors (`jacksonsystems.com`, `alpinehomeair.com`) only as a fallback.

Confidence on URLs: **HIGH** for items 1, 3, 5, 6 (verified against `customer.resideo.com` directly); **MEDIUM** for items 2, 4, 7, 8 (verified document numbers, but Resideo URL slugs occasionally renumber on revision).

---

## 2. Cross-Document Entity Resolution

**Problem we'll hit on PDF #2:** the LLM extracts `t6-pro` from the T9 manual ("REPLACES TH6320WF") and `th6320wf2003` from the T6 Pro install guide. Both are the same Product. Today the normalizer's `NODE_ID_ALIASES` is hand-maintained and T9-specific, so this fails silently — two Product nodes, no merge.

**Pattern: two-stage resolution — deterministic first, fuzzy second.** This is what `neo4j-graphrag-python` ships (`SinglePropertyExactMatchResolver` then `FuzzyMatchResolver` on RapidFuzz/Levenshtein) and is the consensus pattern in current GraphRAG literature. Don't go straight to embedding-based resolution — model numbers are the natural primary key, deterministic rules cover ~85% of cases at zero cost.

**Pipeline integration:**

1. **`src/ingest/normalizer.py` — promote ALIAS_MAP from constant to layered registry.**
   Today `NODE_ID_ALIASES` is one flat dict. Replace with:
   ```
   ALIASES = {
     "rcht9610wf": ["t9", "t9-thermostat", "t9-smart-thermostat", "t9-wi-fi-thermostat"],
     "th6320wf2003": ["t6-pro", "t6", "t6-pro-smart"],
     "thx321wfs2001w": ["t10", "t10-pro", "t10-plus", "t10-pro-smart"],
     ...
   }
   ```
   Build a reverse index at module load. This is still hand-maintained, but it's organized per canonical product and easy to extend per-PDF.

2. **`src/ingest/normalizer.py` — add a model-number regex extractor.** Before alias lookup, run a regex that pulls model numbers from any node label or id (`r"\b(RCHT|TH[XP]?|RTH|HZ|THM|THP)\d{3,4}[A-Z]{0,2}\d{0,4}[A-Z]?\b"`). Honeywell SKUs are highly structured; a regex match should win over alias lookup. Add a new function `canonicalize_model_number(label, node_id) -> str | None` and call it from `normalize_node()` before `NODE_ID_ALIASES`.

3. **`src/ingest/normalizer.py` — fuzzy resolver for non-Product nodes.** WiringConfig and Spec labels drift (`"24 VAC"` vs `"24VAC"` vs `"24V AC"`). Add `rapidfuzz` (already a transitive dep of `instructor` in some versions; verify). New function `fuzzy_merge_within_kind(nodes, threshold=92) -> nodes` that runs after `normalize_and_deduplicate`. Restrict to `WiringConfig` and `Spec` — never fuzzy-merge Products (false positives on similar SKUs are catastrophic).

4. **Post-load resolution job.** After all PDFs are ingested, run a Cypher pass that merges nodes only differing by alias. This is the same idea as neo4j-graphrag's resolver but implemented as an explicit script (`scripts/resolve_cross_doc_entities.py`) so re-runs are auditable.

**Quality gate:** after batch ingest, every Product node must have exactly one `id` and the count of Product nodes must be ≤ (sum of unique model numbers across the corpus). A simple test in `tests/test_resolution.py` enforces this.

Confidence: **HIGH** on the layered-alias + regex approach (deterministic, matches Honeywell SKU structure). **MEDIUM** on fuzzy resolver thresholds (will need tuning on first batch run).

---

## 3. Provenance & Citation

**Problem:** today `neo4j_loader.py` MERGEs edges with `SET r += $props` but the upstream pipeline doesn't attach a source-document property. With one PDF this is fine. With five, "What replaces the T9?" returns an answer with no way to cite which manual the REPLACES edge came from, and you can't debug a wrong edge back to a page.

**Pattern: per-edge `source_doc` + `source_page` properties, plus a `:Document` node.** This is the convention in `neo4j-graphrag-python` (every chunk-derived relationship carries source metadata) and Microsoft GraphRAG (every claim has provenance back to source unit).

**Pipeline integration:**

1. **`src/ingest/entity_extractor.py` — thread doc_id through extraction.** `extract_from_page()` already takes a page dict with `page_num`. Add a new arg `doc_id: str` (e.g. `"t6-pro-33-00392EFS"`). After extraction, decorate every node and edge with `source_doc=doc_id` and `source_page=page["page_num"]` before returning. This is a 5-line change.

2. **`src/graph/neo4j_loader.py` — propagate provenance to MERGE.**
   - Nodes: at `load_nodes()` L128, the current Cypher is `MERGE (n:{label} {id: $id}) SET n += $props`. Add to props: `source_docs` as a list (append-on-merge so a node touched by 3 PDFs ends up with `source_docs: ["t9", "t6-pro", "t10-pro"]`). Cypher pattern:
     ```
     MERGE (n:Product {id: $id})
     ON CREATE SET n.source_docs = [$doc_id], n += $props
     ON MATCH  SET n.source_docs = CASE WHEN $doc_id IN n.source_docs
                                        THEN n.source_docs
                                        ELSE n.source_docs + $doc_id END
     ```
   - Edges: at `load_edges()` L161, edges are MERGEd on (source, type, target). Provenance needs to live on the edge itself. Change MERGE key to include `source_doc`:
     ```
     MERGE (a)-[r:REPLACES {source_doc: $doc_id}]->(b)
     SET r.source_page = $page, r += $props
     ```
     This means the SAME edge fact extracted from two different PDFs becomes two parallel relationships (one per source). That is **correct** — it's the citation evidence. A query helper `RETURN r, collect(r.source_doc)` collapses them at read time.

3. **Add a `:Document` node per PDF.** One MERGE per ingestion run:
   `MERGE (d:Document {doc_id: $doc_id}) SET d.title = $title, d.path = $path, d.ingested_at = datetime()`. Then every Product/Accessory node gets a `(:Product)-[:MENTIONED_IN]->(:Document)` edge. This is one new relation type — but it's metadata-only (not part of the core 4-relation business schema), so consider keeping it on a separate label namespace or noting it explicitly in `schema.py` as "infrastructure relations excluded from VALID_RELATIONS validation."

4. **Streamlit UI citation panel.** When the answer expands the "Graph context," show `source_doc:source_page` next to each triple. One-line Cypher change in the query layer to return `r.source_doc, r.source_page`.

Confidence: **HIGH**. This is a textbook pattern; only design tension is the "edge per source" multiplication, which is the right tradeoff for a citation-first system.

---

## 4. Re-run / Drift Safety for Multi-Doc Ingest

**Problem unique to N>1 PDFs:** re-running ingestion against an updated PDF (or a new Groq model) should not (a) duplicate, (b) leave orphan facts from the prior run that the new run no longer extracts, or (c) silently overwrite a valid edge from PDF-A with conflicting info from PDF-B.

**Patterns:**

1. **Per-document staged ingest.** `scripts/batch_ingest.py` should ingest one PDF at a time, in a deterministic order (config'd in `settings.yaml` as a list), and write a per-doc summary `data/processed/{doc_id}.json` BEFORE touching Neo4j. The Neo4j load step is a separate phase. This means a bad extraction is caught at JSON-diff time, not at graph-write time.

2. **Pre-load diff against previous run.** For each `{doc_id}.json`, diff against `data/processed/{doc_id}.prev.json` if it exists. Log added/removed/changed nodes and edges to `data/processed/{doc_id}.diff.log`. This is the closest thing to a regression test the project will have for extraction drift across model versions.

3. **Idempotent + scoped re-ingest.** Re-running a single PDF must not affect other PDFs' data. Implementation:
   - Before re-ingesting `doc_id`, run `MATCH ()-[r {source_doc: $doc_id}]-() DELETE r` (delete only edges sourced from this doc).
   - Then `MATCH (n {source_docs: [$doc_id]}) DETACH DELETE n` (delete only nodes that were *exclusively* sourced from this doc — the array equality is intentional).
   - Then re-load.
   This is the "edge-per-source" pattern from §3 paying dividends — without it, scoped delete is impossible.

4. **Conflicting-spec policy.** If T9 says "Power: 24VAC 0.2A" and T6 says "Power: 24VAC 0.5A", both HAS_SPEC edges should exist with different source_doc values pointing to potentially different Spec nodes. Don't try to merge specs across products. Add a normalizer rule that Spec node_ids include the parent product id (`spec-rcht9610wf-power-24vac-0-2a`) — this prevents accidental cross-product spec collapse.

**New file:** `scripts/batch_ingest.py` orchestrating: extract → JSON → diff → scoped wipe → load → verify. Failure log goes to `data/processed/batch_{timestamp}.log`.

Confidence: **MEDIUM-HIGH**. Pattern is sound; the scoped-delete logic needs careful testing because `source_docs: [$doc_id]` array-equality is brittle if the property gets re-ordered.

---

## 5. Failure Modes Watch List (1 → N PDFs)

These didn't exist with the T9 alone. Each needs a test or a guard.

| # | Failure | Symptom | Guard |
|---|---------|---------|-------|
| F1 | **Silent product duplication** | T6 Pro present as both `t6-pro` and `th6320wf2003`. Multi-hop "What replaces T9?" misses the chain. | Test in `tests/`: assert Product node count == |unique model numbers|. Run after every batch. |
| F2 | **Accessory fan-in collapse** | RedLINK gateway extracted under different ids in each PDF (`thm6000`, `redlink-gateway`, `internet-gateway`). Cross-doc edges never form. | Add accessories to `ALIASES` registry per §2. Add an assertion that key shared-accessory nodes have ≥2 inbound COMPATIBLE_WITH from different `source_doc`s. |
| F3 | **Spec leakage across products** | T9's 0.2A current spec gets MERGEd onto T6 because the LLM emitted the same Spec node_id. | §4 rule: namespace Spec ids by parent product. |
| F4 | **Conflicting REPLACES chains** | T9 says it replaces TH6320WF; T6 Pro install guide says T6 Pro replaces TH5320U. Chain becomes ambiguous if loader picks one. | These are not conflicts — both edges should exist (different source_docs). Cypher path query naturally surfaces the chain. Add an eval query that requires this. |
| F5 | **Hallucinated cross-doc edges** | LLM sees "T6 Pro" mentioned in the T9 manual and invents a COMPATIBLE_WITH it shouldn't infer. | Tighten extractor prompt rule 4 ("Only extract relationships explicitly stated"). Add a per-doc rate-limit check: if a single page contributes >N edges to products NOT named in that page's prose, flag for manual review. |
| F6 | **WiringConfig fragmentation** | `r-w-y-g-c`, `5-wire-conventional`, `5-wire-heat-cool` all created across docs for the same physical wiring. | Fuzzy resolver per §2 step 3. Restrict aggressive merging to WiringConfig only. |
| F7 | **Drift across Groq model versions** | Switching `llama-3.1-8b-instant` → `llama-3.1-70b-versatile` changes node_ids subtly (different slugs). | Diff log per §4 step 2. Pin model in `settings.yaml`. Add the model name to the per-doc JSON output as `extracted_with_model`. |
| F8 | **PDF parser quality cliff** | T9's pdfplumber config works; T10's wiring tables span pages and pdfplumber returns garbage. | `tests/test_pdf_parser.py` per fixture: assert minimum non-empty page count and minimum table cell count. Fail fast at extraction, not at graph-write. |
| F9 | **EXCLUDED_NODES being honest is now harder** | `electric-baseboard` is excluded because the T9 doesn't support it. But the T6 might. Hard-coded exclusions become wrong. | Move `EXCLUDED_NODES` from a global to a per-doc override in a new `config/exclusions.yaml`. Default is empty; T9 keeps its existing list. |
| F10 | **No-citation answers** | Answer cites a fact whose REPLACES edge has no source_doc. | After every batch, assert `MATCH ()-[r]->() WHERE r.source_doc IS NULL RETURN count(r)` returns 0. |

---

## 6. Open Questions for Requirements

1. **Corpus size:** REQUIREMENTS should pin to 5 PDFs (the recommended set in §1). 8 is overkill for a prototype; 3 doesn't generate enough cross-doc structure. Confirm 5.
2. **Provenance edge multiplication:** §3 step 2 changes the MERGE key for edges. This is a schema-shape decision — it doesn't add new relation types but it changes the cardinality of edges in the graph. Confirm acceptable.
3. **`MENTIONED_IN` relation:** §3 step 3 introduces a 5th relation type for documents. Either (a) add it to `VALID_RELATIONS` in schema.py, (b) treat it as infrastructure and skip the validator, or (c) drop it and rely solely on `source_docs` array on nodes. Pick one.
4. **Fuzzy threshold:** §2 step 3 needs an empirical RapidFuzz threshold. Defer to first batch run; set initial 92, document the tuning step.
5. **Where to host the PDFs:** check in to `data/raw/`, or fetch on demand via `scripts/fetch_corpus.py`? Resideo URLs are stable but bandwidth + license unclear. Recommend: check in, with a `data/raw/SOURCES.md` listing canonical URLs.
6. **Eval queries that prove cross-doc value:** REQUIREMENTS should list 4–6 questions whose answers are only possible when ≥2 PDFs are loaded (e.g. "Which products accept the C7189R wireless room sensor?", "What replaces the T6 Pro?", "Which thermostats can be driven from a RedLINK gateway?"). Out of scope for T1-Sai per the milestone (T2 owns eval), but the corpus must be picked to support these — and §1's recommended set does.
7. **Source PDFs for THP9045 and HZ322** are not on Resideo's modern `/Techlit/` path under the same convention — confirm fallback hosting (`jacksonsystems.com`, official older `/69-0000s/` path) is acceptable.

---

## Sources

- Existing code read: `src/graph/schema.py`, `src/ingest/pdf_parser.py`, `src/ingest/entity_extractor.py`, `src/ingest/normalizer.py`, `src/graph/neo4j_loader.py`, `.planning/PROJECT.md`.
- Honeywell/Resideo techlit (HIGH confidence — verified URLs):
  - T6 Pro install: https://customer.resideo.com/resources/techlit/TechLitDocuments/33-00000s/33-00392EFS.pdf
  - T6 Pro install (alt): https://customer.resideo.com/resources/techlit/TechLitDocuments/33-00000s/33-00410EFS.pdf
  - T6 Pro Z-Wave: https://customer.resideo.com/resources/Techlit/TechLitDocuments/33-00000s/33-00587EFS.pdf
  - T10 Pro install: https://customer.resideo.com/resources/Techlit/TechLitDocuments/33-00000s/33-00423EFS.pdf
  - T10 Pro user guide: https://customer.resideo.com/resources/techlit/TechLitDocuments/33-00000s/33-00428.pdf
  - HZ322 TrueZONE: https://customer.resideo.com/resources/Techlit/TechLitDocuments/69-0000s/69-2199.pdf
  - THM6000R7001 install: https://customer.resideo.com/resources/Techlit/TechLitDocuments/33-00000s/33-00250EFS.pdf
  - THP9045A1023 wiring module: https://customer.resideo.com/resources/Techlit/TechLitDocuments/69-0000s/69-2065EFS.pdf
  - THP9045A1098 C-Wire adapter (mirror): https://jacksonsystems.com/wp-content/uploads/2024/07/THP9045A1098-Installation-Manual.pdf
  - RTH9585WF user guide: https://digitalassets.resideo.com/damroot/Original/10015/33-00269EF.pdf
- Pattern references (MEDIUM confidence — current literature, not version-pinned):
  - Neo4j GraphRAG Python — Knowledge Graph Builder & resolvers (SinglePropertyExactMatch, FuzzyMatch, SpaCySemanticMatch): https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html
  - Microsoft GraphRAG (provenance-first design): https://github.com/microsoft/graphrag
  - "GraphRAG Looks Great Until Entity Resolution Breaks" — multi-hop error compounding: https://www.sowmith.dev/blog/graphrag-entity-disambiguation
  - Cross-doc subgraph extraction patterns: https://igor-polyakov.com/2025/11/26/graphrag-part-2-cross-doc-sub-graph-extraction-multi-vector-entity-representation/
