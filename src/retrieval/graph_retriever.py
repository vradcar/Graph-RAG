import re
from typing import List, Tuple
from src.graph.store import GraphStore


def extract_candidate_entities(question: str) -> List[str]:
    # Matches hyphen-separated uppercase tokens (WALL-PLATE-A, REDLINK-GATEWAY, T6-PRO)
    # and plain uppercase+digit codes (TH1110D, SMK100).
    return re.findall(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|[A-Z]{2,}\d+[A-Z0-9]*", question)


def graph_retrieve(graph_store: GraphStore, question: str, depth: int = 1) -> List[Tuple[str, str, str]]:
    entities = extract_candidate_entities(question)
    context = []

    for entity in entities:
        if graph_store.has_node(entity):
            context.extend(graph_store.neighbors_multi_hop(entity, depth=depth))

    # Fallback for generic, non-entity questions (e.g.,
    # "What is the modern replacement for this discontinued part?").
    if context:
        return context

    q = question.lower()
    asks_replacement = any(token in q for token in ["replacement", "replace", "replaced", "modern replacement"])
    asks_discontinued = any(token in q for token in ["discontinued", "legacy", "old part", "older part"])

    if asks_replacement and hasattr(graph_store, "run_cypher"):
        try:
            # 1) Collect direct replacement mapping from discontinued/legacy items.
            rows = graph_store.run_cypher(
                "MATCH (old)-[r:REPLACED_BY]->(new) "
                "WHERE toLower(coalesce(old.status, '')) IN ['discontinued', 'legacy'] "
                "RETURN old.id AS src, "
                "type(r) AS rel, "
                "new.id AS tgt "
                "LIMIT 40"
            )
            fallback = [(r["src"], r["rel"], r["tgt"]) for r in rows if r.get("src") and r.get("tgt")]

            # If status labels are sparse, broaden to all known replacement links.
            if not fallback:
                rows = graph_store.run_cypher(
                    "MATCH (old)-[r:REPLACED_BY]->(new) "
                    "RETURN old.id AS src, type(r) AS rel, new.id AS tgt "
                    "LIMIT 40"
                )
                fallback = [(r["src"], r["rel"], r["tgt"]) for r in rows if r.get("src") and r.get("tgt")]

            # 2) If user asks for deeper reasoning, expand from replacement targets.
            if fallback and depth > 1:
                replacement_ids = sorted({tgt for _, _, tgt in fallback})
                extra_hops = max(1, depth - 1)
                expansion_rows = graph_store.run_cypher(
                    f"UNWIND $replacement_ids AS rid "
                    f"MATCH (new {{id: rid}})-[rel]->(ctx) "
                    f"WHERE type(rel) IN ["
                    f"'COMPATIBLE_WITH', 'REQUIRES', 'CONNECTS_TO', 'HAS_ELECTRICAL_SPEC', "
                    f"'NEEDS_ADAPTER_IF_MISSING', 'HAS_OPERATING_RANGE', 'MOUNTS_ON'"
                    f"] "
                    f"RETURN new.id AS src, type(rel) AS rel, ctx.id AS tgt "
                    f"LIMIT {200 if extra_hops == 1 else 400}",
                    replacement_ids=replacement_ids,
                )
                expanded = [
                    (r["src"], r["rel"], r["tgt"])
                    for r in expansion_rows
                    if r.get("src") and r.get("tgt")
                ]
                merged = []
                seen = set()
                for t in fallback + expanded:
                    if t not in seen:
                        seen.add(t)
                        merged.append(t)
                return merged

            if fallback:
                return fallback
        except Exception:
            # Keep retrieval resilient and let caller handle empty context.
            pass

    if asks_replacement and asks_discontinued and hasattr(graph_store, "run_cypher"):
        try:
            rows = graph_store.run_cypher(
                "MATCH (old)-[r:REPLACED_BY]->(new) "
                "RETURN old.id AS src, "
                "type(r) AS rel, "
                "new.id AS tgt "
                "LIMIT 20"
            )
            return [(r["src"], r["rel"], r["tgt"]) for r in rows if r.get("src") and r.get("tgt")]
        except Exception:
            pass

    return context
