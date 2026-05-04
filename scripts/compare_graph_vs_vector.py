"""
scripts/compare_graph_vs_vector.py

Comparison runner: executes each question in the curated multi-doc query set through
both graph mode and vector mode, surfaces per-edge source_doc citations, and writes:
  - data/eval/multi_doc_results.json  (machine-readable per-query breakdown)
  - data/eval/multi_doc_comparison.md (human-readable summary + graph-only wins)

Design rules (enforced):
  - Single file in scripts/. NO new modules under src/.
  - NO subclassing of SimpleVectorStore, NO new retriever, NO new generate_* function.
  - NO modifications to graph_retriever, vector_store, hybrid_retriever, generate, evaluate, query.
  - Runs deterministically without --with-llm (default). LLM path is opt-in.
  - Cypher in enrich_triples_with_source_doc is read-only (MATCH ... RETURN only).

Usage:
    .venv/bin/python scripts/compare_graph_vs_vector.py \\
        --queries data/eval/multi_doc_queries.json \\
        --output-json data/eval/multi_doc_results.json \\
        --output-md data/eval/multi_doc_comparison.md \\
        --chunks data/raw/doc_chunks_corpus.json
"""
from dotenv import load_dotenv
load_dotenv()  # Must be first — loads .env before any os.getenv() calls

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Ensure the project root is on sys.path so src/ imports work when called
# directly as a script (vs python -m).
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.vector_store import SimpleVectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core functions (all pure / mockable — no I/O beyond graph_store.run_cypher)
# ---------------------------------------------------------------------------

def load_queries(path: str) -> List[Dict]:
    """Load and parse the curated multi-doc query set from JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _cypher_fallback_retrieve(graph_store, question: str, depth: int) -> List[Tuple]:
    """
    Case-insensitive fallback graph retrieval via run_cypher when graph_retrieve
    returns nothing (upstream has_node is case-sensitive; node_ids are lowercase slugs
    but extract_candidate_entities emits uppercase tokens).

    Uses the pre-approved run_cypher escape hatch. Not a new retriever class or module.
    Only called when graph_retrieve returns an empty list.
    """
    from src.retrieval.graph_retriever import extract_candidate_entities

    candidates = extract_candidate_entities(question)
    if not candidates:
        return []

    triples: List[Tuple] = []
    seen: Set[Tuple] = set()

    for candidate in candidates:
        # Case-insensitive exact match first, then prefix/substring match
        rows = graph_store.run_cypher(
            "MATCH (n) WHERE toLower(n.node_id) = toLower($c) "
            "RETURN n.node_id AS nid LIMIT 1",
            c=candidate,
        )
        if not rows:
            slug = candidate.lower().replace("_", "-")
            rows = graph_store.run_cypher(
                "MATCH (n) WHERE n.node_id = $slug OR n.node_id STARTS WITH $slug "
                "RETURN n.node_id AS nid LIMIT 1",
                slug=slug,
            )
        for row in rows:
            nid = row.get("nid")
            if not nid:
                continue
            for triple in graph_store.neighbors_multi_hop(nid, depth=depth):
                # Filter out triples where src or tgt resolved to None
                # (Document nodes use doc_id, not node_id, so MENTIONED_IN
                # targets return None from _return_id_expr — skip them here).
                if triple[0] is not None and triple[2] is not None and triple not in seen:
                    seen.add(triple)
                    triples.append(triple)

    return triples


def enrich_triples_with_source_doc(graph_store, triples: List[Tuple]) -> List[Dict]:
    """
    For each unique (src, rel, tgt) triple, run one parametrized Cypher read to
    fetch the source_doc property from the matching edge in Neo4j.

    Returns a list of quad dicts:
        {"source": str, "relation": str, "target": str, "source_doc": str | None}

    If the Cypher returns no rows for an edge, one quad with source_doc=None is
    emitted — the edge is still surfaced but provenance is marked as missing
    (Phase 1 invariant violation signal).

    Deduplication: unique (src, rel, tgt) combos only, to avoid redundant round-trips.
    An edge present in 2 PDFs (Cypher returns 2 rows) produces 2 quads.
    """
    # Deduplicate triples preserving order
    seen: Set[Tuple] = set()
    unique_triples: List[Tuple] = []
    for triple in triples:
        if triple not in seen:
            seen.add(triple)
            unique_triples.append(triple)

    quads: List[Dict] = []
    for src, rel, tgt in unique_triples:
        # Nodes are keyed by node_id (lowercase slugs). The plan originally
        # documented s.id / t.id but the actual schema uses node_id exclusively.
        rows = graph_store.run_cypher(
            "MATCH (s)-[r]->(t) "
            "WHERE s.node_id = $src AND t.node_id = $tgt AND type(r) = $rel "
            "RETURN DISTINCT r.source_doc AS source_doc",
            src=src,
            tgt=tgt,
            rel=rel,
        )
        if not rows:
            logger.warning("no source_doc for edge %s -[%s]-> %s", src, rel, tgt)
            quads.append({"source": src, "relation": rel, "target": tgt, "source_doc": None})
        else:
            for row in rows:
                quads.append({
                    "source": src,
                    "relation": rel,
                    "target": tgt,
                    "source_doc": row.get("source_doc"),
                })

    return quads


def distinct_source_docs(quads: List[Dict]) -> Set[str]:
    """
    Return the set of distinct source_doc values from a list of quad dicts.
    None values are excluded so missing-provenance edges do not inflate the count.
    """
    return {q["source_doc"] for q in quads if q.get("source_doc") is not None}


def vector_doc_coverage(vector_hits: List[Dict], expected_source_docs: Set[str]) -> Set[str]:
    """
    Return the subset of expected_source_docs that the vector hits actually cover.

    A vector hit 'counts' if hit.get("source_doc") is in expected_source_docs.
    (doc_chunks_corpus.json carries source_doc on every chunk.)
    """
    covered: Set[str] = set()
    for hit in vector_hits:
        hit_doc = hit.get("source_doc")
        if hit_doc and hit_doc in expected_source_docs:
            covered.add(hit_doc)
    return covered


def verdict(query: Dict, graph_quads: List[Dict], vector_hits: List[Dict]) -> Dict:
    """
    Compute the verdict for a single query.

    Returns:
        {
            "verdict": "graph" | "tie" | "graph_fail",
            "graph_distinct_source_docs": int,
            "vector_distinct_expected_docs_covered": int,
            "gap": str | None,
        }

    Logic:
        1. If graph < expected_min -> "graph_fail" + gap description
        2. elif graph_only -> "graph" (vector cannot satisfy graph_only questions)
        3. elif vector covers >= expected_min -> "tie"
        4. else -> "graph"
    """
    graph_distinct = len(distinct_source_docs(graph_quads))
    expected_min = query["expected_min_distinct_source_docs"]
    expected_docs: Set[str] = set(query.get("expected_source_docs", []))
    vector_covered = len(vector_doc_coverage(vector_hits, expected_docs))

    if graph_distinct < expected_min:
        gap = (
            f"graph returned {graph_distinct} distinct docs, "
            f"expected >= {expected_min}"
        )
        return {
            "verdict": "graph_fail",
            "graph_distinct_source_docs": graph_distinct,
            "vector_distinct_expected_docs_covered": vector_covered,
            "gap": gap,
        }

    if query.get("graph_only") is True:
        return {
            "verdict": "graph",
            "graph_distinct_source_docs": graph_distinct,
            "vector_distinct_expected_docs_covered": vector_covered,
            "gap": None,
        }

    if vector_covered >= expected_min:
        return {
            "verdict": "tie",
            "graph_distinct_source_docs": graph_distinct,
            "vector_distinct_expected_docs_covered": vector_covered,
            "gap": None,
        }

    return {
        "verdict": "graph",
        "graph_distinct_source_docs": graph_distinct,
        "vector_distinct_expected_docs_covered": vector_covered,
        "gap": None,
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def write_markdown(results: List[Dict], path: str) -> None:
    """
    Write data/eval/multi_doc_comparison.md with three sections:
      1. # Multi-Document Graph-vs-Vector Comparison
      2. ## Summary  (table)
      3. ## Graph-only Wins  (bulleted list, QUALITY-04 gate)
      4. ## Per-Question Detail
    """
    lines = [
        "# Multi-Document Graph-vs-Vector Comparison",
        "",
        "## Summary",
        "",
        "| id | question (truncated) | verdict | graph_distinct_docs | vector_covered | graph_only |",
        "|----|---------------------|---------|--------------------:|---------------:|------------|",
    ]

    for r in results:
        q_short = r["question"][:60].rstrip()
        lines.append(
            f"| {r['id']} "
            f"| {q_short} "
            f"| {r['verdict']} "
            f"| {len(r['graph']['distinct_source_docs'])} "
            f"| {r['vector']['expected_docs_covered'] and len(r['vector']['expected_docs_covered']) or 0} "
            f"| {'yes' if r['graph_only'] else 'no'} |"
        )

    lines.append("")

    # Graph-only wins (QUALITY-04)
    graph_only_wins = [r for r in results if r["verdict"] == "graph" and r.get("graph_only")]
    lines.append("## Graph-only Wins")
    lines.append("")
    if len(graph_only_wins) >= 2:
        for r in graph_only_wins:
            lines.append(f"- **{r['id']}**: {r['question']}")
    else:
        lines.append(
            f"> WARNING: QUALITY-04 not satisfied — only {len(graph_only_wins)} graph-only wins "
            f"(need >= 2). See Per-Question Detail for graph_fail entries."
        )
        for r in graph_only_wins:
            lines.append(f"- **{r['id']}**: {r['question']}")
    lines.append("")

    # Per-question detail
    lines.append("## Per-Question Detail")
    lines.append("")
    for r in results:
        lines.append(f"### {r['id']}: {r['question']}")
        lines.append("")
        lines.append(f"**Expected source docs:** {', '.join(r['expected_source_docs'])}")
        lines.append(f"**Graph-only:** {'yes' if r['graph_only'] else 'no'}")
        lines.append(f"**Verdict:** {r['verdict']}" + (f"  _(gap: {r['gap']})_" if r['gap'] else ""))
        lines.append("")
        lines.append("**Graph quads:**")
        lines.append("```")
        for q in r["graph"]["quads"]:
            lines.append(
                f"{q['source']} --[{q['relation']}]--> {q['target']}  [{q['source_doc']}]"
            )
        lines.append("```")
        lines.append("")
        lines.append("**Vector doc_ids covered:**")
        covered = r["vector"]["expected_docs_covered"]
        if covered:
            for doc in covered:
                lines.append(f"- {doc}")
        else:
            lines.append("- (none)")
        lines.append("")

    Path(path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    queries_path: str,
    output_json: str,
    output_md: str,
    chunks_path: str,
    with_llm: bool = False,
) -> List[Dict]:
    """
    Main loop: iterate queries, run graph + vector retrieval, compute verdicts,
    write output artifacts.

    with_llm=False (default): deterministic, no LLM calls.
    with_llm=True: calls generate_answer() — requires GROQ_API_KEY or OPENAI_API_KEY.
    """
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not neo4j_password:
        print("ERROR: NEO4J_PASSWORD environment variable is required", file=sys.stderr)
        sys.exit(1)

    top_k = settings["retrieval"].get("top_k_chunks", 5)

    # Load chunks into vector store
    with open(chunks_path, "r", encoding="utf-8") as fh:
        chunks = json.load(fh)
    vector_store = SimpleVectorStore()
    vector_store.add_documents(chunks)

    queries = load_queries(queries_path)
    results: List[Dict] = []

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        for q in queries:
            qid = q["id"]
            logger.info("Processing query %s: %s", qid, q["question"][:60])

            # Graph retrieval — primary path, then case-insensitive fallback.
            # graph_retrieve uses has_node which is case-sensitive; node_ids in
            # this corpus are lowercase slugs but questions contain uppercase SKUs.
            # The fallback resolves this without modifying graph_retriever.py.
            graph_triples = graph_retrieve(store, q["question"], depth=q.get("depth", 2))
            if not graph_triples:
                graph_triples = _cypher_fallback_retrieve(
                    store, q["question"], depth=q.get("depth", 2)
                )
            graph_quads = enrich_triples_with_source_doc(store, graph_triples)

            # Vector retrieval
            vector_hits = vector_store.search(q["question"], top_k=top_k)

            # Verdict
            v = verdict(q, graph_quads, vector_hits)

            # Optional LLM answer
            llm_prose = None
            if with_llm:
                try:
                    from src.llm.provider import build_instructor_client
                    from src.llm.generate import generate_answer
                    model = settings["llm"]["model"]
                    provider = settings["llm"].get("provider", "groq")
                    client = build_instructor_client(provider)
                    answer = generate_answer(client, model, q["question"], graph_triples)
                    llm_prose = answer.prose
                except Exception as exc:
                    logger.warning("LLM answer failed for %s: %s", qid, exc)

            # Build result entry
            graph_distinct_list = sorted(distinct_source_docs(graph_quads))
            vector_doc_ids = [h.get("id", "") for h in vector_hits]
            expected_docs_set = set(q.get("expected_source_docs", []))
            vector_covered_list = sorted(vector_doc_coverage(vector_hits, expected_docs_set))

            entry = {
                "id": qid,
                "question": q["question"],
                "depth": q.get("depth", 2),
                "expected_source_docs": q.get("expected_source_docs", []),
                "expected_min_distinct_source_docs": q["expected_min_distinct_source_docs"],
                "graph_only": q.get("graph_only", False),
                "graph": {
                    "triple_count": len(graph_triples),
                    "quads": graph_quads,
                    "distinct_source_docs": graph_distinct_list,
                },
                "vector": {
                    "hit_count": len(vector_hits),
                    "doc_ids": vector_doc_ids,
                    "expected_docs_covered": vector_covered_list,
                },
                "verdict": v["verdict"],
                "gap": v.get("gap"),
                "llm_prose": llm_prose,
            }
            results.append(entry)

    # Write JSON
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"Wrote {len(results)} results to {output_json}")

    # Write Markdown
    Path(output_md).parent.mkdir(parents=True, exist_ok=True)
    write_markdown(results, output_md)
    print(f"Wrote comparison markdown to {output_md}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare graph vs vector retrieval across the curated multi-doc query set"
    )
    parser.add_argument(
        "--queries",
        default="data/eval/multi_doc_queries.json",
        help="Path to multi_doc_queries.json (Plan 04-01 output)",
    )
    parser.add_argument(
        "--output-json",
        default="data/eval/multi_doc_results.json",
        help="Path for the per-query machine-readable results JSON",
    )
    parser.add_argument(
        "--output-md",
        default="data/eval/multi_doc_comparison.md",
        help="Path for the human-readable comparison markdown",
    )
    parser.add_argument(
        "--chunks",
        default="data/raw/doc_chunks_corpus.json",
        help="Path to doc_chunks_corpus.json (vector baseline — Plan 04-01 fixture)",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        default=False,
        help="Generate prose answers via LLM (requires API keys; default: off)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run(
        queries_path=args.queries,
        output_json=args.output_json,
        output_md=args.output_md,
        chunks_path=args.chunks,
        with_llm=args.with_llm,
    )


if __name__ == "__main__":
    main()
