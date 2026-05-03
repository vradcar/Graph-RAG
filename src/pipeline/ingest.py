"""
Ingestion entry point.

Auto-detects the input type based on file extension:
  - *.pdf  → Week 2 path: pdfplumber-based rich extraction + legacy conversion
  - *.json → Week 1 path: legacy product records (unchanged)

Both paths produce the same legacy output shape:
    {"nodes": [{"node_id", "label", "kind", ...}],
     "edges": [{"source_id", "target_id", "relation", ...}]}

This means the existing GraphStore in src/graph/store.py loads either file
without modification. Week 2 adds richer properties (source_page, reasons,
conditions, etc.) as extra fields on the legacy-shaped nodes and edges.

Usage:
  # Week 1 (legacy):
  python -m src.pipeline.ingest --input data/raw/products_sample.json

  # Week 2 (PDF):
  python -m src.pipeline.ingest \
      --input data/raw/t9-thermostat.pdf \
      --replacements data/raw/replacements.json
"""

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

from src.graph.extract import (
    extract_from_pdf,
    graph_items_to_legacy_format,
    load_product_records,
    product_records_to_graph_items,
)

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest source data into graph-ready JSON")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to source file (.pdf for Week 2 PDF extraction, .json for legacy records)",
    )
    parser.add_argument(
        "--replacements",
        default=None,
        help="Optional path to curated replacements JSON (PDF mode only)",
    )
    parser.add_argument(
        "--output",
        default="data/processed/graph_items.json",
        help="Path for processed graph items",
    )
    parser.add_argument(
        "--rich-output",
        default=None,
        help="Optional path to also write the Week 2 rich-format graph (PDF mode only)",
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Manifest doc-id key (PDF mode). Loads the entry's `pages` filter if set.",
    )
    parser.add_argument(
        "--inferencer",
        default=None,
        choices=["groq", "openrouter", "gemini"],
        help=(
            "LLM backend for PDF extraction (PDF + --doc-id mode only). "
            "groq: uses GROQ_API_KEY (default when key is present). "
            "openrouter: uses OPENROUTER_API_KEY with google/gemma-3-27b-it:free."
        ),
    )
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help=(
            "Bypass the output-JSON cache and re-run LLM extraction even if "
            "--output already exists. Use after prompt/schema/model changes."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable INFO-level logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    suffix = input_path.suffix.lower()

    if suffix == ".pdf":
        replacements_path = Path(args.replacements) if args.replacements else None
        if replacements_path and not replacements_path.exists():
            raise SystemExit(f"Replacements file not found: {replacements_path}")

        pages_filter = None
        if args.doc_id:
            from src.ingest.manifest import get_doc
            doc = get_doc(args.doc_id)
            pages_filter = tuple(doc["pages"]) if doc.get("pages") else None

        # Cache short-circuit: if --doc-id is set and --output already holds a
        # valid extraction, skip provider/key checks entirely. Lets cached runs
        # work with no API keys present at all.
        cache_path = Path(args.output)
        force_extract = args.force_extract or os.getenv("CORPUS_FORCE_EXTRACT") == "1"
        cached_graph = None
        if args.doc_id and not force_extract and cache_path.exists():
            try:
                with cache_path.open("r", encoding="utf-8") as fh:
                    candidate = json.load(fh)
                if (
                    isinstance(candidate, dict)
                    and candidate.get("nodes")
                    and "edges" in candidate
                ):
                    cached_graph = candidate
            except (json.JSONDecodeError, OSError):
                cached_graph = None

        # Use the hardened LLM pipeline when --doc-id is provided and an API key is set.
        # --inferencer explicitly picks the backend; without it we fall back by key presence.
        # Falls back to the legacy T9-specific pdfplumber extractors when no key is available.
        _DEFAULT_MODELS = {
            "groq": "llama-3.3-70b-versatile",
            # meta-llama/llama-3.3-70b-instruct:free supports system prompts +
            # JSON mode on OpenRouter free tier. Gemma 3 was rejected by Google
            # AI Studio with "Developer instruction is not enabled".
            "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
            "openai": "gpt-4o-mini",
            "gemini": "gemini-3-flash-preview",
        }
        _KEY_VARS = {
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }

        if args.inferencer:
            provider = args.inferencer
            use_llm = bool(args.doc_id and (cached_graph is not None or os.getenv(_KEY_VARS[provider])))
            if args.doc_id and cached_graph is None and not os.getenv(_KEY_VARS[provider]):
                raise SystemExit(
                    f"{_KEY_VARS[provider]} is not set — required for --inferencer {provider}"
                )
        else:
            # Auto-detect: groq → openrouter → openai → legacy
            if os.getenv("GROQ_API_KEY"):
                provider = "groq"
            elif os.getenv("OPENROUTER_API_KEY"):
                provider = "openrouter"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            else:
                provider = None
            use_llm = bool(args.doc_id and provider)

        if use_llm:
            if cached_graph is not None:
                # Re-normalize cached graphs: alias rules and id-canonicalization
                # may have evolved since the JSON was written. Forward-compat is
                # cheap (no LLM calls) and prevents cross-doc bridge drift when
                # an older cache used a different separator convention.
                from src.ingest.normalizer import normalize_and_deduplicate, normalize_node_id

                norm_nodes = normalize_and_deduplicate(cached_graph.get("nodes", []))
                seen: set = set()
                norm_edges: list = []
                for e in cached_graph.get("edges", []):
                    src = normalize_node_id(e["source_id"])
                    tgt = normalize_node_id(e["target_id"])
                    key = (src, tgt, e["relation"])
                    if key not in seen:
                        seen.add(key)
                        norm_edges.append({**e, "source_id": src, "target_id": tgt})
                existing_ids = {n["node_id"] for n in norm_nodes}
                for e in norm_edges:
                    for endpoint_key in ("source_id", "target_id"):
                        eid = e[endpoint_key]
                        if eid not in existing_ids:
                            norm_nodes.append({"node_id": eid, "label": eid, "kind": "Unknown"})
                            existing_ids.add(eid)
                graph_items = {"nodes": norm_nodes, "edges": norm_edges}
                print(
                    f"[cache] hit: {cache_path} "
                    f"({len(graph_items['nodes'])} nodes, {len(graph_items['edges'])} edges "
                    f"after re-normalization) — skipping LLM extraction "
                    "(use --force-extract to override)"
                )
            else:
                from src.ingest.pdf_parser import extract_page_content
                from src.ingest.entity_extractor import build_client, extract_from_page
                from src.ingest.normalizer import normalize_and_deduplicate, normalize_node_id

                model = os.getenv("LLM_MODEL", _DEFAULT_MODELS[provider])
                client = build_client(provider)
                raw_pages = extract_page_content(str(input_path), pages=pages_filter)
                all_nodes: list = []
                all_edges: list = []
                for page in raw_pages:
                    result = extract_from_page(client, model, page, doc_id=args.doc_id)
                    all_nodes.extend(n.model_dump() for n in result.nodes)
                    all_edges.extend(e.model_dump() for e in result.edges)
                norm_nodes = normalize_and_deduplicate(all_nodes)
                seen: set = set()
                norm_edges: list = []
                for e in all_edges:
                    src = normalize_node_id(e["source_id"])
                    tgt = normalize_node_id(e["target_id"])
                    key = (src, tgt, e["relation"])
                    if key not in seen:
                        seen.add(key)
                        norm_edges.append({**e, "source_id": src, "target_id": tgt})
                # Repair dangling edge endpoints: if the LLM emitted an edge whose
                # source or target wasn't extracted as a node, add a minimal stub so
                # the neo4j_loader MATCH doesn't fail.
                existing_ids = {n["node_id"] for n in norm_nodes}
                for e in norm_edges:
                    for endpoint_key in ("source_id", "target_id"):
                        eid = e[endpoint_key]
                        if eid not in existing_ids:
                            norm_nodes.append({"node_id": eid, "label": eid, "kind": "Unknown"})
                            existing_ids.add(eid)

                graph_items = {"nodes": norm_nodes, "edges": norm_edges}
                log.info(
                    "LLM path: %d nodes, %d edges extracted from %s (doc_id=%s)",
                    len(norm_nodes), len(norm_edges), input_path.name, args.doc_id,
                )
        else:
            rich_graph = extract_from_pdf(input_path, replacements_path, pages=pages_filter)
            graph_items = graph_items_to_legacy_format(rich_graph)

        # Optionally save the rich Week 2 format alongside the legacy output.
        # Only meaningful for the legacy pdfplumber path; LLM/cache paths don't
        # produce a rich_graph, so skip rather than NameError.
        if args.rich_output and "rich_graph" in locals():
            rich_path = Path(args.rich_output)
            rich_path.parent.mkdir(parents=True, exist_ok=True)
            with rich_path.open("w", encoding="utf-8") as f:
                json.dump(rich_graph, f, indent=2)
            print(f"Saved rich graph to {rich_path}")

        # Replacements manifest → Neo4j as REPLACES edges (INGEST-04).
        # Runs only when --replacements is provided and Neo4j is reachable.
        if args.replacements:
            replacements_path_r = Path(args.replacements)
            if replacements_path_r.exists():
                try:
                    from neo4j import GraphDatabase
                    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
                    user_n = os.getenv("NEO4J_USER", "neo4j")
                    pwd = os.getenv("NEO4J_PASSWORD", "neo4j")
                    from src.graph.extract import ingest_replacements
                    with GraphDatabase.driver(uri, auth=(user_n, pwd)) as driver:
                        counts = ingest_replacements(replacements_path_r, driver)
                    print(f"Ingested replacements: {counts}")
                except Exception as exc:
                    # Do not fail the pipeline if Neo4j is unreachable — replacements
                    # ingest is best-effort relative to the JSON output above.
                    print(f"WARN: replacements Neo4j ingest skipped: {exc}")

    elif suffix == ".json":
        records = load_product_records(str(input_path))
        graph_items = product_records_to_graph_items(records)

    else:
        raise SystemExit(
            f"Unsupported input type: {suffix}. Expected .pdf or .json."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(graph_items, file, indent=2)

    print(f"Saved graph items to {output_path} (doc_id={args.doc_id or '<none>'}, "
          f"{len(graph_items['nodes'])} nodes, {len(graph_items['edges'])} edges)")


if __name__ == "__main__":
    main()
