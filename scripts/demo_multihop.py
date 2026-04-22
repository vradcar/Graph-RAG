"""
Week 2 demo: side-by-side comparison of single-hop vs multi-hop traversal.

Runs a curated set of queries against the loaded Neo4j graph at depth=1
and depth=2, prints both results next to each other so you can see exactly
what extra context multi-hop reasoning brings in. This is the core Week 2
deliverable evidence.

Output is structured so it is easy to screenshot / paste into the report:
  - Each query shows the question, then the depth=1 result, then depth=2
  - A summary at the end shows total nodes/hops reached at each depth

Usage:
    python -m scripts.demo_multihop

Prerequisites:
    - Neo4j running (docker container or Neo4j Desktop)
    - data/processed/graph_items.json loaded via:
        python -m src.graph.neo4j_loader --reset --verify
"""

from __future__ import annotations

from src.graph.neo4j_query import Neo4jQueryEngine, TraversalPath


# Queries chosen to showcase WHY multi-hop matters. Each one is a real
# question an HVAC installer might ask. The single-hop answer alone is
# incomplete; the multi-hop answer adds the context needed to actually
# act on it.
DEMO_QUERIES = [
    {
        "question": "What does the T9 thermostat connect to and depend on?",
        "entity": "t9_rcht9610wf",
        "why_multihop": (
            "1-hop reaches all direct neighbors. 2-hop additionally "
            "reaches the Zoning Panel through the C-Wire Adapter — a "
            "non-obvious dependency that affects installation."
        ),
    },
    {
        "question": "If a homeowner has a discontinued RTH6580WF, what is the modern path forward?",
        "entity": "rth6580wf_legacy",
        "relations": ["REPLACED_BY", "COMPATIBLE_WITH", "REQUIRES", "CONNECTS_TO"],
        "why_multihop": (
            "1-hop only finds the replacement (T9). 2-hop additionally "
            "surfaces what HVAC systems the T9 supports, what wiring it needs, "
            "and what accessories it works with — the full migration picture."
        ),
    },
    {
        "question": "What does the C-Wire Adapter affect?",
        "entity": "c_wire_adapter",
        "why_multihop": (
            "1-hop shows the Zoning Panel caveat. There are no further hops "
            "from this node, so 1-hop and 2-hop look identical — useful to "
            "demonstrate the depth parameter does not invent extra hops."
        ),
    },
    {
        "question": "What does the wireless room sensor do?",
        "entity": "wireless_room_sensor",
        "why_multihop": (
            "Leaf node — 1-hop and 2-hop both return nothing. Demonstrates "
            "graceful handling of nodes with no outgoing edges."
        ),
    },
]


def _render_compact(paths: list[TraversalPath]) -> list[str]:
    """Render paths as one line each, sorted by hop count then alphabetically."""
    rendered = sorted(p.render() for p in paths)
    return rendered


def run_one(engine: Neo4jQueryEngine, query: dict) -> None:
    print()
    print("=" * 78)
    print(f"Q: {query['question']}")
    print(f"   start entity: {query['entity']}")
    if query.get("relations"):
        print(f"   relation filter: {query['relations']}")
    print("=" * 78)

    relations = query.get("relations")

    single = engine.traverse_from(query["entity"], depth=1, relation_filter=relations)
    multi = engine.traverse_from(query["entity"], depth=2, relation_filter=relations)

    if single.get("error"):
        print(f"ERROR: {single['error']}")
        return

    start_name = single["start"].get("name", single["start"].get("id"))
    print(f"\nStart: {start_name}")

    print(f"\n--- depth=1 (single-hop) ---")
    print(f"  reached {single['node_count']} unique nodes via {single['hop_count']} hops")
    if single["paths"]:
        for line in _render_compact(single["paths"]):
            print(f"  {line}")
    else:
        print("  (no paths)")

    print(f"\n--- depth=2 (multi-hop) ---")
    print(f"  reached {multi['node_count']} unique nodes via {multi['hop_count']} hops")
    if multi["paths"]:
        for line in _render_compact(multi["paths"]):
            # Mark the new 2-hop paths so they're easy to spot
            marker = "  +" if line.count("-[") >= 2 else "   "
            print(f"  {marker} {line}")
    else:
        print("  (no paths)")

    delta_nodes = multi["node_count"] - single["node_count"]
    delta_hops = multi["hop_count"] - single["hop_count"]
    print(f"\n  Δ depth=1 → depth=2: +{delta_nodes} nodes, +{delta_hops} hops")
    print(f"\n  Why multi-hop matters here:")
    print(f"  {query['why_multihop']}")


def main() -> None:
    print()
    print("###############################################################")
    print("#  Week 2 Demo: Single-hop vs Multi-hop traversal comparison  #")
    print("###############################################################")

    with Neo4jQueryEngine() as engine:
        # Sanity check: confirm the graph is loaded
        entities = engine.list_entities()
        print(f"\nLoaded graph contains {len(entities)} entities total")

        for query in DEMO_QUERIES:
            run_one(engine, query)

    print()
    print("=" * 78)
    print("Demo complete. Screenshot this output for the Week 2 report.")
    print("=" * 78)


if __name__ == "__main__":
    main()
