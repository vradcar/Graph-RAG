"""
Cypher helpers for document-level provenance in Neo4j.

All three helpers are designed to be called inside ``session.execute_write``:

    session.execute_write(lambda tx: merge_document(tx, doc_dict))
    session.execute_write(lambda tx: merge_node_with_provenance(tx, node_dict, doc_id))
    session.execute_write(lambda tx: merge_edge_with_provenance(tx, edge_dict, doc_id))

Invariant (audit query — should always return 0 after a clean ingest):

    MATCH ()-[r]->()
    WHERE type(r) <> 'MENTIONED_IN' AND r.source_doc IS NULL
    RETURN count(r) AS missing

Design notes:
- merge_document must be called in its own committed transaction BEFORE the entity
  loop so that the MENTIONED_IN MATCH inside merge_node_with_provenance always finds
  the :Document node (Pitfall 5 in RESEARCH.md).
- source_doc is keyed inside the MERGE pattern for edges so the same fact extracted
  from two different PDFs creates two parallel evidence edges (SCHEMA-04).
- Pure-Cypher dedup guard on source_docs prevents unbounded growth on re-ingest (Pitfall 3).
  coll.distinct() (APOC) is NOT used — replaced with CASE WHEN expression for Community Edition
  compatibility.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from neo4j import ManagedTransaction

from src.graph.utils import clean_props as _clean_props

log = logging.getLogger("provenance")

VALID_LABELS = frozenset({"Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec", "Entity"})
VALID_RELATIONS = frozenset({"COMPATIBLE_WITH", "REPLACES", "HAS_SPEC", "REQUIRES", "RELATED_TO"})


def merge_document(tx: ManagedTransaction, doc: Dict[str, Any]) -> None:
    """Upsert a :Document node.

    ``doc`` must contain keys: doc_id, title, sku, source_url, ingested_at.

    ON CREATE: sets first_ingested = datetime() (preserved on re-ingest).
    ON MATCH:  sets last_reingested = datetime() (does NOT overwrite first_ingested).
    """
    tx.run(
        """
        MERGE (d:Document {doc_id: $doc_id})
        ON CREATE SET
            d.title         = $title,
            d.sku           = $sku,
            d.source_url    = $source_url,
            d.ingested_at   = datetime($ingested_at),
            d.first_ingested = datetime()
        ON MATCH SET
            d.title         = $title,
            d.sku           = $sku,
            d.source_url    = $source_url,
            d.last_reingested = datetime()
        """,
        doc_id=doc.get("doc_id"),
        title=doc.get("title", ""),
        sku=doc.get("sku"),
        source_url=doc.get("source_url"),
        ingested_at=doc.get("ingested_at") or None,
    )


def merge_node_with_provenance(
    tx: ManagedTransaction,
    node: Dict[str, Any],
    doc_id: str,
) -> None:
    """MERGE node by id; accumulate source_docs (dedup via CASE WHEN); MERGE MENTIONED_IN to :Document.

    ``node`` dict shape:
        {
            "node_id": str,          # canonical id (also accepted: "id")
            "label":   str,          # human-readable label (stored as property)
            "kind":    str,          # Neo4j label — validated against VALID_KINDS by caller
            "properties": dict,      # extra props (optional)
        }

    ``doc_id`` is REQUIRED — never optional.
    """
    node_id = node.get("node_id") or node.get("id")
    if not node_id:
        raise ValueError(f"merge_node_with_provenance requires a non-empty node_id; got: {node!r}")
    label = node.get("kind") or node.get("type") or "Entity"
    extra_props = _clean_props(node.get("properties") or {})

    # Build props map: include human label if present, plus any extra props.
    props: Dict[str, Any] = {}
    if node.get("label"):
        props["label"] = node["label"]
    props.update(extra_props)
    # Ensure node_id is stored as a property too (keeps compat with existing schema).
    props["node_id"] = node_id

    # Whitelist-validate the label — structural tokens must not be interpolated
    # without strict validation (Cypher injection defence).
    if label not in VALID_LABELS:
        raise ValueError(f"Unknown node label {label!r}; allowed: {VALID_LABELS}")
    safe_label = label  # already validated — no character-stripping needed

    # First-match: if a node with the same node_id already exists under any label,
    # reuse it (add source_docs + MENTIONED_IN) instead of creating a new-label clone.
    # This prevents cross-doc multi-label duplicates that break scoped-delete idempotency.
    existing = tx.run(
        "MATCH (n {node_id: $node_id}) RETURN n LIMIT 1",
        node_id=node_id,
    ).single()

    if existing is not None:
        # Node exists (possibly under a different label) — update in-place
        result = tx.run(
            """
            MATCH (n {node_id: $node_id})
            WITH n LIMIT 1
            SET n += $props,
                n.source_docs = CASE WHEN $doc_id IN coalesce(n.source_docs, []) THEN n.source_docs ELSE coalesce(n.source_docs, []) + [$doc_id] END,
                n.last_seen   = timestamp()
            WITH n
            MATCH (d:Document {doc_id: $doc_id})
            MERGE (n)-[m:MENTIONED_IN]->(d)
            ON CREATE SET m.first_mentioned = timestamp()
            RETURN count(m) AS mi_count
            """,
            node_id=node_id,
            props=props,
            doc_id=doc_id,
        )
    else:
        # Node does not exist — create with canonical label
        result = tx.run(
            f"""
            MERGE (n:{safe_label} {{node_id: $node_id}})
            ON CREATE SET
                n += $props,
                n.source_docs = [$doc_id],
                n.first_seen  = timestamp()
            ON MATCH SET
                n += $props,
                n.source_docs = CASE WHEN $doc_id IN coalesce(n.source_docs, []) THEN n.source_docs ELSE coalesce(n.source_docs, []) + [$doc_id] END,
                n.last_seen   = timestamp()
            WITH n
            MATCH (d:Document {{doc_id: $doc_id}})
            MERGE (n)-[m:MENTIONED_IN]->(d)
            ON CREATE SET m.first_mentioned = timestamp()
            RETURN count(m) AS mi_count
            """,
            node_id=node_id,
            props=props,
            doc_id=doc_id,
        )
    row = result.single()
    if row is None or row["mi_count"] == 0:
        raise ValueError(
            f"merge_node_with_provenance: :Document {{doc_id: {doc_id!r}}} not found. "
            "Call merge_document in a committed transaction before ingesting nodes."
        )


def merge_edge_with_provenance(
    tx: ManagedTransaction,
    edge: Dict[str, Any],
    doc_id: str,
) -> None:
    """MERGE (a)-[r:REL {source_doc: $doc_id}]->(b).

    ``edge`` dict shape:
        {
            "source_id": str,   # id of source node (also accepted: "source")
            "target_id": str,   # id of target node (also accepted: "target")
            "relation":  str,   # relationship type — validated against VALID_RELATIONS by caller
            "properties": dict, # extra props (optional)
        }

    ``doc_id`` is keyed INSIDE the MERGE map so the same fact from two PDFs
    creates two parallel evidence edges (SCHEMA-04).

    ``doc_id`` is REQUIRED — never optional.
    """
    source_id = edge.get("source_id") or edge.get("source")
    target_id = edge.get("target_id") or edge.get("target")
    relation = edge.get("relation") or edge.get("type", "RELATED_TO")
    props = _clean_props(edge.get("properties") or {})

    # Whitelist-validate the relation type — structural tokens must not be interpolated
    # without strict validation (Cypher injection defence).
    if relation not in VALID_RELATIONS:
        raise ValueError(f"Unknown relation {relation!r}; allowed: {VALID_RELATIONS}")
    safe_rel = relation  # already validated — no character-stripping needed

    result = tx.run(
        f"""
        MATCH (a {{node_id: $source_id}})
        MATCH (b {{node_id: $target_id}})
        MERGE (a)-[r:{safe_rel} {{source_doc: $doc_id}}]->(b)
        ON CREATE SET r += $props, r.created = timestamp()
        ON MATCH  SET r += $props, r.updated = timestamp()
        RETURN count(r) AS written
        """,
        source_id=source_id,
        target_id=target_id,
        props=props,
        doc_id=doc_id,
    )
    row = result.single()
    if row is None or row["written"] == 0:
        raise ValueError(
            f"merge_edge_with_provenance: endpoint node not found "
            f"(source_id={source_id!r}, target_id={target_id!r})"
        )


def scoped_delete_doc(tx: ManagedTransaction, doc_id: str) -> Dict[str, int]:
    """Remove every contribution of ``doc_id`` while leaving other docs intact.

    Implements BATCH-04 (idempotent re-runs) by deleting only the rows this doc
    contributed and orphan-cleaning nodes whose ``source_docs[]`` becomes empty.
    The 5 steps run in a single tx and roll back together on failure.

    Steps:
        1. Drop business edges with ``r.source_doc = $doc_id``.
        2. Drop ``MENTIONED_IN`` edges from each entity to the :Document
           — direction matches ``merge_node_with_provenance`` L118
           ``(entity)-[:MENTIONED_IN]->(:Document)``.
        3. Prune ``$doc_id`` from every node's ``source_docs[]`` array.
        4. Detach-delete nodes whose ``source_docs`` is now empty
           (excluding :Document — owned by step 5).
        5. Detach-delete the :Document node itself.

    Returns a counts dict for the per-doc batch report::

        {"edges": int, "mentioned_in": int, "nodes_pruned": int,
         "orphans": int, "document": int}

    Notes:
        * Must be invoked inside ``session.execute_write`` so all 5 steps
          share one transaction — partial failure rolls back per Neo4j 5.x
          semantics.
        * Assumes Phase 1 invariant A2: every non-MENTIONED_IN edge carries
          ``r.source_doc``. Edges with ``source_doc IS NULL`` would survive
          scoped delete and break BATCH-04 idempotency — see the pre-flight
          assertion in Plan 03-03 Task 2 verify block.
    """
    edge_q = (
        "MATCH ()-[r {source_doc: $doc_id}]->() "
        "WITH r, count(r) AS c "
        "DELETE r "
        "RETURN c"
    )
    ment_q = (
        "MATCH (e)-[m:MENTIONED_IN]->(:Document {doc_id: $doc_id}) "
        "WITH m, count(m) AS c "
        "DELETE m "
        "RETURN c"
    )
    prune_q = (
        "MATCH (n) WHERE $doc_id IN coalesce(n.source_docs, []) "
        "SET n.source_docs = [x IN n.source_docs WHERE x <> $doc_id] "
        "RETURN count(n) AS c"
    )
    orph_q = (
        "MATCH (n) WHERE n.source_docs IS NOT NULL "
        "AND size(n.source_docs) = 0 "
        "AND NOT n:Document "
        "WITH n, count(n) AS c "
        "DETACH DELETE n "
        "RETURN c"
    )
    doc_q = (
        "MATCH (d:Document {doc_id: $doc_id}) "
        "WITH d, count(d) AS c "
        "DETACH DELETE d "
        "RETURN c"
    )

    out: Dict[str, int] = {}
    for name, q in (
        ("edges", edge_q),
        ("mentioned_in", ment_q),
        ("nodes_pruned", prune_q),
        ("orphans", orph_q),
        ("document", doc_q),
    ):
        rec = tx.run(q, doc_id=doc_id).single()
        out[name] = (rec["c"] if rec else 0)
    return out
