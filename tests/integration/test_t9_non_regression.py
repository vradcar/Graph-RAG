"""SC-4 / INGEST-05: re-ingesting T9 after Phase 2 hardening must produce
node/edge counts >= the v1.0 baseline, and no entity kind from the baseline
may be removed. Uses the conftest neo4j_driver + clean_db fixtures."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

BASELINE = json.loads(Path("tests/fixtures/t9_baseline.json").read_text())
GRAPH_ITEMS = Path("data/processed/graph_items.json")


@pytest.mark.integration
def test_t9_baseline_no_regression(neo4j_driver, clean_db):
    if not GRAPH_ITEMS.exists():
        pytest.skip(f"{GRAPH_ITEMS} missing — run ingest first")
    result = subprocess.run(
        [sys.executable, "-m", "src.graph.neo4j_loader",
         "--reset", "--doc-id", BASELINE["doc_id"],
         "--doc-title", "T9 Smart Thermostat Installation Guide",
         "--doc-sku", "T9",
         "--doc-source-url", "honeywellhome.com/t9-install-guide",
         "--input", str(GRAPH_ITEMS)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"loader failed: {result.stderr}"

    with neo4j_driver.session() as session:
        n = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        e = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        kinds = {row["k"] for row in session.run(
            "MATCH (n) UNWIND labels(n) AS k RETURN DISTINCT k")}

    assert n >= BASELINE["node_total"], f"nodes regressed: {n} < {BASELINE['node_total']}"
    assert e >= BASELINE["edge_total"], f"edges regressed: {e} < {BASELINE['edge_total']}"
    baseline_kinds = set(BASELINE["nodes_by_kind"].keys())
    missing = baseline_kinds - kinds
    assert not missing, f"baseline kinds removed: {missing}"
