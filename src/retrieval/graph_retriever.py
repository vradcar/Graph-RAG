import re
from typing import List, Tuple
from src.graph.store import GraphStore
from src.ingest.normalizer import normalize_node_id


def extract_candidate_entities(question: str) -> List[str]:
    """Extract product codes and common shorthands from the question."""
    # Hyphenated codes (WALL-PLATE-A) and multi-letter+digit codes (RCHT9510WF, TH1110D)
    standard = re.findall(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|[A-Z]{2,}\d+[A-Z0-9]*", question)
    # Short product codes: T9, T6, T10 etc. (case-insensitive)
    short = re.findall(r"\bT\d+\b", question, re.IGNORECASE)
    return standard + [s.upper() for s in short]


def _lookup(graph_store: GraphStore, entity: str, depth: int) -> List[Tuple[str, str, str]]:
    """Try entity as-is, then lowercased, then normalized alias — return first hit."""
    for candidate in [entity, entity.lower(), normalize_node_id(entity)]:
        if graph_store.has_node(candidate):
            return graph_store.neighbors_multi_hop(candidate, depth=depth)
    return []


def graph_retrieve(graph_store: GraphStore, question: str, depth: int = 1) -> List[Tuple[str, str, str]]:
    entities = extract_candidate_entities(question)
    context = []

    for entity in entities:
        context.extend(_lookup(graph_store, entity, depth))

    # Fallback for generic, non-entity questions (e.g.,
    # "What is the modern replacement for this discontinued part?").
    if context:
        return context

    q = question.lower()
    asks_replacement = any(token in q for token in ["replacement", "replace", "replaced", "modern replacement"])
    asks_discontinued = any(token in q for token in ["discontinued", "legacy", "old part", "older part"])
    asks_compatibility = any(token in q for token in [
        "compatible", "compatibility", "accessories", "accessory", "work with", "works with",
        "wiring", "hvac", "system type", "electrical", "specification", "spec",
    ])

    # Broad fallback: return all edges from the primary product node so any question
    # about T9 features, accessories, or wiring returns useful context.
    if not context and asks_compatibility and hasattr(graph_store, "run_cypher"):
        try:
            rows = graph_store.run_cypher(
                "MATCH (n)-[r]->(m) "
                "WHERE toLower(coalesce(n.id, '')) CONTAINS 'rcht9' "
                "   OR toLower(coalesce(n.id, '')) IN ['t9', 't9-thermostat'] "
                "RETURN coalesce(n.id) AS src, type(r) AS rel, "
                "       coalesce(m.id) AS tgt LIMIT 60"
            )
            context = [(r["src"], r["rel"], r["tgt"]) for r in rows if r.get("src") and r.get("tgt")]
        except Exception:
            pass

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
