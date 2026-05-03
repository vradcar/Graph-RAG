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

import json
import logging
from typing import Any, Dict

from neo4j import ManagedTransaction

log = logging.getLogger("provenance")


def _clean_props(d: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten props to Neo4j-safe scalar / primitive-list values."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = v
        else:
            out[k] = json.dumps(v)
    return out


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
    label = node.get("kind") or node.get("type") or "Entity"
    extra_props = _clean_props(node.get("properties") or {})

    # Build props map: include human label if present, plus any extra props.
    props: Dict[str, Any] = {}
    if node.get("label"):
        props["label"] = node["label"]
    props.update(extra_props)
    # Ensure node_id is stored as a property too (keeps compat with existing schema).
    props["node_id"] = node_id

    # label has already been validated / sanitised by the caller (neo4j_loader) before
    # it reaches here.  We still sanitise as defence-in-depth.
    safe_label = "".join(ch for ch in label if ch.isalnum()) or "Entity"

    tx.run(
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
        """,
        node_id=node_id,
        props=props,
        doc_id=doc_id,
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

    # Sanitise relation type — caller validates, but we sanitise as defence-in-depth.
    safe_rel = "".join(ch if ch.isalnum() else "_" for ch in relation).upper()

    tx.run(
        f"""
        MATCH (a {{node_id: $source_id}})
        MATCH (b {{node_id: $target_id}})
        MERGE (a)-[r:{safe_rel} {{source_doc: $doc_id}}]->(b)
        ON CREATE SET r += $props, r.created = timestamp()
        ON MATCH  SET r += $props, r.updated = timestamp()
        """,
        source_id=source_id,
        target_id=target_id,
        props=props,
        doc_id=doc_id,
    )
