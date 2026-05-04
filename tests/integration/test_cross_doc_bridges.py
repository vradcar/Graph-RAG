"""SC-2 / DISCOVER-03: After ingesting each new PDF (T6, THP9045, T10) into the
same Neo4j as T9, there must be at least one node OR edge that bridges the new
doc to t9_install_guide. We check via the source_docs[] array on nodes and the
source_doc property on edges (Phase 1 SCHEMA-03/05).

Depends on the `corpus_ingested` session fixture from test_corpus_ingest_full.py
so Phase 2 self-gates SC-2 -- no manual ingest step required."""
import pytest

# corpus_ingested session fixture lives in tests/integration/conftest.py

NEW_DOC_IDS = ["t6_pro_install", "thp9045_wiring_module", "t10_pro_user_guide"]
T9_DOC_ID = "t9_install_guide"


@pytest.mark.integration
@pytest.mark.parametrize("new_doc_id", NEW_DOC_IDS)
def test_each_new_doc_bridges_to_t9(neo4j_driver, corpus_ingested, new_doc_id):
    # NOTE: clean_db deliberately not used here. corpus_ingested is session-scoped
    # and owns the Neo4j state. A function-scoped clean_db wipes the data the
    # fixture loaded, leaving the test to read an empty graph.
    with neo4j_driver.session() as session:
        shared_nodes = session.run(
            "MATCH (n) WHERE $d1 IN n.source_docs AND $d2 IN n.source_docs RETURN count(n) AS c",
            d1=T9_DOC_ID, d2=new_doc_id,
        ).single()["c"]
        bridge_edges = session.run(
            """MATCH (a)-[]-(b)
               WHERE $d1 IN a.source_docs AND $d2 IN b.source_docs
               RETURN count(*) AS c""",
            d1=T9_DOC_ID, d2=new_doc_id,
        ).single()["c"]
        assert (shared_nodes + bridge_edges) > 0, (
            f"No cross-doc bridge found between {T9_DOC_ID} and {new_doc_id}. "
            f"shared_nodes={shared_nodes}, bridge_edges={bridge_edges}. "
            f"Likely an alias gap -- extend NODE_ID_ALIASES in normalizer.py."
        )
