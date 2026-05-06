"""
Evaluate query pipeline against demo queries.

Usage:
    python -m src.pipeline.evaluate
    python -m src.pipeline.evaluate --queries data/eval/queries.json --output data/eval/results.json
"""
from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import sys
import time
import math
import re
from pathlib import Path

from src.common.config import load_settings
from src.graph.store import Neo4jGraphStore
from src.llm.provider import build_instructor_client
from src.retrieval.graph_retriever import graph_retrieve
from src.retrieval.vector_store import SimpleVectorStore
from src.retrieval.hybrid_retriever import hybrid_retrieve
from src.llm.generate import generate_answer


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _split_expected(expected: str) -> list[str]:
    if not expected:
        return []
    parts = re.split(r"\s+and\s+|,", expected, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _triple_text(triple) -> str:
    if isinstance(triple, tuple) and len(triple) >= 3:
        return f"{triple[0]} {triple[1]} {triple[2]}"
    if hasattr(triple, "source") and hasattr(triple, "relation") and hasattr(triple, "target"):
        return f"{triple.source} {triple.relation} {triple.target}"
    if isinstance(triple, dict):
        return f"{triple.get('source')} {triple.get('relation')} {triple.get('target')}"
    return str(triple)


def _count_expected_hits(texts: list[str], expected_tokens: list[str]) -> int:
    if not expected_tokens:
        return 0
    count = 0
    for text in texts:
        normalized = _normalize(text)
        if any(token.casefold() in normalized for token in expected_tokens):
            count += 1
    return count


def _precision_at_k(hit_count: int, k: int, has_expected: bool) -> float | None:
    if not has_expected:
        return None
    if k <= 0:
        return 0.0
    return round(hit_count / k, 3)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def run_eval(
    queries_path: str,
    output_path: str,
    provider: str | None = None,
    model: str | None = None,
    output_csv: str | None = None,
    summary_path: str | None = None,
) -> None:
    """Run evaluation pipeline against a set of demo queries."""
    settings = load_settings()
    neo4j_uri = settings["graph"]["neo4j_uri"]
    neo4j_user = settings["graph"]["neo4j_user"]
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not neo4j_password:
        print("ERROR: NEO4J_PASSWORD environment variable is required", file=sys.stderr)
        sys.exit(1)
    model = model or settings["llm"]["model"]
    provider = provider or settings["llm"].get("provider", "groq")

    client = None
    try:
        client = build_instructor_client(provider)
    except ValueError as e:
        print(f"WARNING: {e}", file=sys.stderr)
        print("WARNING: Falling back to deterministic non-LLM answer mode", file=sys.stderr)

    # Load document chunks for vector/hybrid retrieval
    docs_path = Path("data/raw/doc_chunks.json")
    with docs_path.open("r", encoding="utf-8") as f:
        doc_chunks = json.load(f)

    vector_store = SimpleVectorStore()
    vector_store.add_documents(doc_chunks)

    with Neo4jGraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password) as store:
        with Path(queries_path).open("r", encoding="utf-8") as f:
            queries = json.load(f)

        results = []
        csv_rows = []
        for item in queries:
            question = item["question"]
            depth = item.get("depth", 2)
            expected = item.get("expected", "")
            expected_tokens = _split_expected(expected)
            has_expected = bool(expected_tokens)

            # Graph-only
            g_start = time.perf_counter()
            graph_hits = graph_retrieve(store, question, depth=depth)
            graph_latency = time.perf_counter() - g_start

            # Vector-only
            v_start = time.perf_counter()
            vector_hits = vector_store.search(question, top_k=settings["retrieval"]["top_k_chunks"])
            vector_latency = time.perf_counter() - v_start

            # Hybrid (graph + vector) — measure combined time
            h_start = time.perf_counter()
            hybrid_hits = hybrid_retrieve(
                store,
                vector_store,
                question,
                depth=depth,
                top_k=settings["retrieval"]["top_k_chunks"],
            )
            hybrid_latency = time.perf_counter() - h_start

            # Optional answer generation using graph evidence (kept for report context)
            answer = generate_answer(client, model, question, graph_hits)

            graph_texts = [_triple_text(t) for t in graph_hits]
            vector_texts = [d.get("text", "") for d in vector_hits]
            hybrid_texts = graph_texts + [d.get("text", "") for d in hybrid_hits.get("doc_hits", [])]

            graph_expected_hits = _count_expected_hits(graph_texts, expected_tokens)
            vector_expected_hits = _count_expected_hits(vector_texts, expected_tokens)
            hybrid_expected_hits = _count_expected_hits(hybrid_texts, expected_tokens)

            results.append({
                "id": item.get("id"),
                "question": question,
                "depth": depth,
                "expected": expected,
                "graph": {
                    "hit_count": len(graph_hits),
                    "latency_sec": round(graph_latency, 3),
                    "latency_ms": int(graph_latency * 1000),
                    "contains_expected": graph_expected_hits > 0 if has_expected else None,
                    "precision_at_k": _precision_at_k(graph_expected_hits, len(graph_hits), has_expected),
                    "evidence": [e.model_dump() for e in answer.evidence],
                },
                "vector": {
                    "hit_count": len(vector_hits),
                    "latency_sec": round(vector_latency, 3),
                    "latency_ms": int(vector_latency * 1000),
                    "contains_expected": vector_expected_hits > 0 if has_expected else None,
                    "precision_at_k": _precision_at_k(vector_expected_hits, len(vector_hits), has_expected),
                    "doc_ids": [d.get("id") for d in vector_hits],
                },
                "hybrid": {
                    "graph_hit_count": len(hybrid_hits.get("graph_hits", [])),
                    "doc_hit_count": len(hybrid_hits.get("doc_hits", [])),
                    "latency_sec": round(hybrid_latency, 3),
                    "latency_ms": int(hybrid_latency * 1000),
                    "contains_expected": hybrid_expected_hits > 0 if has_expected else None,
                    "precision_at_k": _precision_at_k(
                        hybrid_expected_hits,
                        len(hybrid_hits.get("graph_hits", [])) + len(hybrid_hits.get("doc_hits", [])),
                        has_expected,
                    ),
                    "doc_ids": [d.get("id") for d in hybrid_hits.get("doc_hits", [])],
                },
            })

            if output_csv:
                csv_rows.extend([
                    {
                        "id": item.get("id"),
                        "question": question,
                        "expected": expected,
                        "depth": depth,
                        "method": "graph",
                        "hit_count": len(graph_hits),
                        "latency_ms": int(graph_latency * 1000),
                        "contains_expected": graph_expected_hits > 0 if has_expected else None,
                        "precision_at_k": _precision_at_k(graph_expected_hits, len(graph_hits), has_expected),
                    },
                    {
                        "id": item.get("id"),
                        "question": question,
                        "expected": expected,
                        "depth": depth,
                        "method": "vector",
                        "hit_count": len(vector_hits),
                        "latency_ms": int(vector_latency * 1000),
                        "contains_expected": vector_expected_hits > 0 if has_expected else None,
                        "precision_at_k": _precision_at_k(vector_expected_hits, len(vector_hits), has_expected),
                    },
                    {
                        "id": item.get("id"),
                        "question": question,
                        "expected": expected,
                        "depth": depth,
                        "method": "hybrid",
                        "hit_count": len(hybrid_hits.get("graph_hits", [])) + len(hybrid_hits.get("doc_hits", [])),
                        "latency_ms": int(hybrid_latency * 1000),
                        "contains_expected": hybrid_expected_hits > 0 if has_expected else None,
                        "precision_at_k": _precision_at_k(
                            hybrid_expected_hits,
                            len(hybrid_hits.get("graph_hits", [])) + len(hybrid_hits.get("doc_hits", [])),
                            has_expected,
                        ),
                    },
                ])

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    if output_csv:
        csv_path = Path(output_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8") as f:
            header = [
                "id",
                "question",
                "expected",
                "depth",
                "method",
                "hit_count",
                "latency_ms",
                "contains_expected",
                "precision_at_k",
            ]
            f.write(",".join(header) + "\n")
            for row in csv_rows:
                f.write(",".join(str(row.get(col, "")) for col in header) + "\n")

    if summary_path:
        def _method_summary(method: str) -> dict:
            method_rows = [r for r in results if r.get(method)]
            latencies = [r[method]["latency_ms"] for r in method_rows]
            contains = [r[method]["contains_expected"] for r in method_rows]
            contains_filtered = [c for c in contains if c is not None]
            accuracy = None
            if contains_filtered:
                accuracy = round(sum(1 for c in contains_filtered if c) / len(contains_filtered), 3)
            return {
                "accuracy": accuracy,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "p50_latency_ms": _percentile(latencies, 0.5),
                "p95_latency_ms": _percentile(latencies, 0.95),
            }

        summary = {
            "total_queries": len(results),
            "graph": _method_summary("graph"),
            "vector": _method_summary("vector"),
            "hybrid": _method_summary("hybrid"),
        }

        summary_file = Path(summary_path)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        with summary_file.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    print(f"Evaluated {len(results)} queries. Saved to {output_path}")


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Evaluate query pipeline against demo queries")
    parser.add_argument(
        "--queries",
        default=settings["evaluation"]["queries_file"],
        help="Path to queries JSON file",
    )
    parser.add_argument(
        "--output",
        default=settings["evaluation"]["output_file"],
        help="Path to write results JSON",
    )
    parser.add_argument("--provider", choices=["groq", "openai"], default=None,
                        help="LLM provider override (default: from settings.yaml)")
    parser.add_argument("--model", default=None,
                        help="Model name override (default: from settings.yaml)")
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Optional CSV output path for per-query metrics",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional JSON summary output path",
    )
    args = parser.parse_args()
    run_eval(
        args.queries,
        args.output,
        provider=args.provider,
        model=args.model,
        output_csv=args.output_csv,
        summary_path=args.summary,
    )


if __name__ == "__main__":
    main()
