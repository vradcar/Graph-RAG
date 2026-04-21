# Week 2 Report — Multi-hop Reasoning

## Objective
Extend the Week 1 baseline with multi-hop graph traversal and validate it on
the product compatibility use case. Compare single-hop vs multi-hop retrieval
quality across the evaluation query set.

## Use Case Chosen
- **Product Compatibility (HVAC)**
- **Why this use case:** Real compatibility questions in this domain are
  inherently multi-hop — e.g. "what accessories work with the replacement of a
  discontinued product" requires traversing: discontinued product → its
  replacement → the replacement's accessories. A flat document search cannot
  reliably reason across these relationship chains; graph traversal is the
  natural fit.

## Multi-hop Implementation
- **Traversal strategy:** Breadth-first search (BFS) starting from any graph
  node that matches an entity extracted from the question. At each step,
  outgoing *and* incoming edges are followed, collecting
  `(source, relation, target)` triples. Implemented in
  `src/graph/store.py → GraphStore.neighbors_multi_hop()`.
- **Depth parameter design:** Exposed as `--depth` CLI flag (default 1).
  Depth 1 = direct neighbours only. Depth 2 = neighbours of neighbours,
  which is required for questions that chain two relationship hops (e.g.
  TH1110D → T6-PRO → REDLINK-GATEWAY).
- **Entity linking approach:** Regex extraction of uppercase product codes
  (`[A-Z]{2,}\d+[A-Z0-9]*|[A-Z]{2,}-\d+`) from the raw question string.
  Matched tokens are looked up directly in the graph; unmatched tokens are
  silently skipped.

## Single-hop vs Multi-hop Comparison

| Query | Single-hop hits | Multi-hop hits (depth 2) | Quality difference |
|---|---|---|---|
| What accessories can I use with the replacement for TH1110D? | 0 (TH1110D has no accessory named in question) | 9 — full neighbourhood of TH1110D and T6-PRO | Multi-hop surfaces the replacement and its accessories; single-hop cannot cross the REPLACES edge |
| What system type does the replacement for TH1110D belong to? | 0 | 9 — includes T6-PRO node with system_type=HVAC | Single-hop misses T6-PRO entirely; multi-hop walks through the replacement chain |
| Which accessories are shared between TH1110D and its replacement? | 3 (TH1110D direct neighbours) | 9 — both product neighbourhoods | Depth 2 captures both sides of the comparison; depth 1 only sees one product |
| Which accessories are compatible with TH1110D? | 3 ✓ | 3 (no improvement needed) | Simple 1-hop lookup — depth has no effect here |

## Evidence
1. **Traversal path (depth 2, q06):**
   ```
   TH1110D --[COMPATIBLE_WITH]--> WALL-PLATE-A
   TH1110D --[COMPATIBLE_WITH]--> WIRE-C-ADAPTER
   T6-PRO  --[REPLACES]---------> TH1110D
   T6-PRO  --[COMPATIBLE_WITH]--> WALL-PLATE-A
   T6-PRO  --[COMPATIBLE_WITH]--> REDLINK-GATEWAY
   (+ reverse edges back to source)
   ```
2. **Evaluation results:** Full 12-query comparison run — see
   `data/eval/results.json` and `notebooks/scoring_analysis.ipynb`
3. **Chart:** `reports/retrieval_comparison.png` — accuracy and latency by method

## Lessons Learned / Week 3 Prep
- **Graph retriever gap — reverse traversal:** When the query entity is an
  accessory (e.g. WALL-PLATE-A or REDLINK-GATEWAY), the retriever returns 0
  hits on 3 of 12 queries because the regex does not extract accessory-style
  tokens and the BFS never starts. Fix: broaden entity extraction or add
  reverse-index lookup.
- **Vector covers graph's blind spots:** Vector retrieval scored 100% accuracy
  vs graph's 67% — but graph returned 3x more hits on multi-hop questions
  where it did work (9 vs 3). Neither alone is sufficient.
- **Hybrid is the safest baseline:** 100% accuracy, never 0 hits, only ~0.013ms
  overhead vs vector alone.
- **Week 3 priorities:**
  1. Wire real LLM (Member 4) to replace the generate.py stub so correctness
     scoring can check actual answer text, not just hit counts
  2. Ingest real domain data (Member 1) and re-run full evaluation
  3. Fix reverse-traversal gap in graph retriever
  4. Add per-query correctness column to scoring notebook once LLM is live
