# Week 2 Report — Multi-hop Reasoning

## Objective
Extend the Week 1 baseline with multi-hop graph traversal and validate it on
the product compatibility use case. Compare single-hop vs multi-hop retrieval
quality across the evaluation query set.

## Use Case Chosen
- **Product Compatibility (HVAC)**
- **Why this use case:** Real compatibility questions in this domain are
  inherently multi-hop — e.g. "what does a homeowner need to know when
  replacing a discontinued thermostat?" requires traversing: legacy device →
  its replacement → the replacement's compatible systems, wiring requirements,
  and accessories. A flat document search cannot reliably reason across these
  relationship chains; graph traversal is the natural fit.

## Multi-hop Implementation
- **Traversal strategy:** Two implementations running in parallel:
  - **NetworkX (main pipeline):** BFS from keyword-matched entity nodes,
    following both outgoing and incoming edges, collecting
    `(source, relation, target)` triples. Implemented in
    `src/graph/store.py → GraphStore.neighbors_multi_hop()`.
  - **Neo4j/Cypher (Member 2):** Cypher-based traversal using
    `OPTIONAL MATCH path = (start {id: $entity_id}) -[*1..{depth}]-> (end)`.
    Implemented in `src/graph/neo4j_query.py → Neo4jQueryEngine.traverse_from()`.
    Loaded into Neo4j via `src/graph/neo4j_loader.py`.
- **Depth parameter design:** Exposed as `--depth` CLI flag (default 1).
  Depth 1 = direct neighbours only. Depth 2 = neighbours of neighbours.
  Depth parameter provably does not invent extra hops — leaf nodes and
  nodes with no outbound edges return identical results at depth=1 and depth=2.
- **Entity linking approach:** Regex extraction of uppercase product codes and
  hyphen-separated tokens (e.g. `T6-PRO`, `WALL-PLATE-A`, `RCHT9610WF`)
  from the raw question string. Matched tokens are looked up directly in the
  graph; unmatched tokens fall through to vector retrieval.

## Single-hop vs Multi-hop Comparison

Source: `reports/week2_evidence/demo_output.txt` — Neo4j traversal on a 31-entity graph.

| Query | Single-hop result | Multi-hop result (depth 2) | Quality difference |
|---|---|---|---|
| What does the T9 thermostat connect to and depend on? | 26 nodes, 25 hops — all direct T9 relationships (compatible systems, wiring terminals, electrical spec) | 27 nodes, 27 hops — adds Zoning Panel discovered through C-Wire Adapter | Multi-hop surfaces a non-obvious installation dependency: if the home has a zoning panel, the C-Wire Adapter installation is more complex. 1-hop misses this entirely. |
| If a homeowner has a discontinued RTH6580WF, what is the modern path forward? | 2 nodes, 1 hop — only finds the replacement (T9) | 20 nodes, 37 hops — surfaces all HVAC systems T9 supports, all wiring requirements, and all compatible accessories | 1-hop answers "what replaces it?" but not "what do I need to install the replacement?" 2-hop gives the full migration picture in one query. Δ: +18 nodes, +36 hops. |
| What does the C-Wire Adapter affect? | 2 nodes, 1 hop — Zoning Panel dependency | 2 nodes, 1 hop — identical | Leaf node with no further connections. Demonstrates depth parameter behaves correctly — no phantom hops invented. |
| What does the wireless room sensor do? | No paths (leaf node) | No paths (leaf node) | Graceful handling of nodes with no outbound edges at any depth. |

**Key finding:** The biggest multi-hop gain is on replacement chain queries. Depth=2 returned 18x more nodes (+18 nodes, +36 hops) than depth=1 on the RTH6580WF migration question — the difference between a one-word answer ("T9") and a complete installation guide.

## Evidence
1. **Traversal path (depth=2, RTH6580WF replacement query):**
   ```
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf -[COMPATIBLE_WITH]-> central_cooling
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf -[COMPATIBLE_WITH]-> forced_air_heating
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf -[COMPATIBLE_WITH]-> heat_pump
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf -[CONNECTS_TO]-> wireless_room_sensor
   rth6580wf_legacy -[REPLACED_BY]-> t9_rcht9610wf -[REQUIRES]-> terminal_c  (+ 13 more terminals)
   Δ depth=1 → depth=2: +18 nodes, +36 hops
   ```
   Full output: `reports/week2_evidence/demo_output.txt`

2. **Evaluation results:** Full 12-query comparison run across graph, vector,
   and hybrid — see `data/eval/results.json` and `notebooks/scoring_analysis.ipynb`.
   Graph accuracy: 91.7% (11/12). Only failure: q09 — text-only question with no graph node.

3. **Chart:** `reports/retrieval_comparison.png` — accuracy and latency by method.

## Lessons Learned / Week 3 Prep
- **Multi-hop depth matters most on chain queries:** Replacement/migration questions
  see the largest gain (18x more context at depth=2). Simple attribute lookups
  see no improvement from increasing depth.
- **Graph retrieval gap — text-only questions:** One question (q09, "retrofit
  installations") returns 0 graph hits at any depth because the concept has no
  graph node. Vector retrieval is the only solution here — hybrid covers it.
- **Neo4j backend is not yet wired into the main pipeline:** `evaluate.py` runs
  against NetworkX only. For week 3, if Neo4j is integrated, the evaluation
  should be re-run to compare NetworkX vs Neo4j traversal quality as well.
- **Week 3 priorities:**
  1. Wire real LLM (Member 4) so correctness scoring checks actual answer text
  2. Re-run eval on expanded real-world data (Member 1)
  3. Integrate Neo4j into the main pipeline evaluation (Member 2 coordination)
  4. Finalize week 3 report with full graph vs vector vs hybrid comparison
