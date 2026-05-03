"""Coverage for cross-doc bridge canonicalization (INGEST-03 + SC-2).

Each parametrized case asserts that aliases observed across the corpus collapse to
the canonical node_id Phase 1 already established. If any of these regress, the
cross-doc edges in test_cross_doc_bridges.py will silently disappear."""
import pytest
from src.ingest.normalizer import normalize_node_id, is_sku


@pytest.mark.parametrize("raw,canonical", [
    # UWP family
    ("UWP Mounting System", "uwp-wallplate"),
    ("UWP", "uwp-wallplate"),
    ("Wallplate", "uwp-wallplate"),
    # THX9321R subbase family
    ("THX9321R5000", "thx9321r"),
    ("THX9321R1008", "thx9321r"),
    ("THX9321R-subbase", "thx9321r"),
    # HVAC terminals
    ("R", "terminal-r"),
    ("R-Wire", "terminal-r"),
    ("24V Power R", "terminal-r"),
    ("C", "terminal-c"),
    ("Y", "terminal-y"),
    ("G", "terminal-g"),
    ("W", "terminal-w"),
    ("O/B", "terminal-o-b"),
    ("AUX", "terminal-aux"),
    # HVAC system-type slugs
    ("1 Heat 1 Cool", "1h-1c"),
    ("2 Heat 2 Cool", "2h-2c"),
    ("3 Heat 2 Cool", "3h-2c"),
])
def test_normalize_node_id_canonicalizes_bridge(raw, canonical):
    assert normalize_node_id(raw) == canonical


@pytest.mark.parametrize("sku", [
    "TH6320U2008",        # T6 Pro
    "TH6220U2000",        # T6 Pro
    "TH6210U2001",        # T6 Pro
    "THX321WFS3001W",     # T10 Pro
    "THX321WF2001W",      # T10 Pro
    "C7189R3002-2",       # T10 sensor
    "C7089R3013",         # T10 sensor
    "THP9045",            # C-wire adapter
    "RCHT9610WF",         # T9 (existing baseline)
])
def test_is_sku_matches_corpus_skus(sku):
    assert is_sku(sku), f"{sku} should match SKU_REGEX"


@pytest.mark.parametrize("not_sku", [
    "uwp-wallplate",
    "heat-pump",
    "2-wire-heat-only",
    "T9",                 # too short to satisfy regex
    "",
])
def test_is_sku_rejects_non_skus(not_sku):
    assert not is_sku(not_sku)


def test_existing_t9_aliases_still_work():
    """Phase 1 baseline depends on these — regression guard."""
    assert normalize_node_id("T9 Wi-Fi Thermostat") == "rcht9610wf"
    assert normalize_node_id("T9") == "rcht9610wf"
    assert normalize_node_id("Wireless Sensor") == "wireless-room-sensor"
