"""Unit tests for app.py (Streamlit UI).

These tests use Streamlit's AppTest harness — no browser, no live Neo4j.
Live-stack verification is a manual checkpoint in Plan 03-02 Task 2.
"""
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = "app.py"

# The Neo4j messages embed the configured NEO4J_URI, so match on the stable
# leading phrase rather than the full string.
NEO4J_UNREACHABLE_COPY = "Could not connect to Neo4j at "
NEO4J_AUTH_COPY = "Neo4j rejected the credentials for "
LLM_COPY = (
    "The LLM call failed. Check that your API key is set correctly in .env "
    "and that the model name in settings.yaml is valid."
)
UNKNOWN_COPY = "Something went wrong. Check the terminal for details."


def test_initial_render_has_required_widgets():
    # timeout=30: the app now parses/renders the full multi-doc comparison
    # table on every run (all 4 tabs execute regardless of which is active),
    # which comfortably exceeded the original 10s budget once that table grew
    # with the richer embeddings-based retrieval evidence.
    at = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not at.exception, f"Initial render raised: {at.exception}"
    # Title + caption
    assert at.title[0].value == "Honeywell GraphRAG — Milestone 2.0 Demo"
    # Text input label (accessed by key in AppTest)
    ti_labels = [ti.label for ti in at.text_input]
    assert "Your question" in ti_labels
    # Ask button
    ask_labels = [b.label for b in at.button]
    assert "Ask" in ask_labels
    # Demo query buttons
    assert "What accessories are compatible with the T9?" in ask_labels
    assert "Does the THP9045 C-wire adapter work with heat pump systems?" in ask_labels
    assert "What does the UWP wallplate mount on?" in ask_labels
    # Sidebar Neo4j link — st.link_button renders as UnknownElement in AppTest 1.35;
    # verify by inspecting the proto of the first sidebar child.
    sidebar_link = at.sidebar[0]
    assert "http://localhost:7474" in str(sidebar_link.proto)
    # Sidebar slider
    slider_labels = [s.label for s in at.sidebar.slider]
    assert "Traversal Depth" in slider_labels
    depth_slider = next(s for s in at.sidebar.slider if s.label == "Traversal Depth")
    assert depth_slider.min == 1
    assert depth_slider.max == 3


def test_initial_render_has_no_answer_area():
    # Note: at.info is NOT asserted empty here — the Corpus tab unconditionally
    # renders one st.info() per document that has a `notes` field in
    # manifest.json (3, currently), independent of whether a question has
    # been asked. That's unrelated to the query-answer area this test covers.
    at = AppTest.from_file(APP_PATH).run(timeout=30)
    assert len(at.error) == 0
    assert len(at.expander) == 0  # no Graph Evidence / Debug Payload expander before submission


@pytest.mark.parametrize("exc, expected", [
    (Exception("Neo4j connection refused on bolt://localhost:7687"), NEO4J_UNREACHABLE_COPY),
    (Exception("ServiceUnavailable: bolt driver could not connect"), NEO4J_UNREACHABLE_COPY),
    # A Neo4j auth rejection must NOT be reported as an unreachable database.
    (Exception("{code: Neo.ClientError.Security.Unauthorized} bolt"), NEO4J_AUTH_COPY),
    (Exception("401 Unauthorized: invalid api key"), LLM_COPY),
    (Exception("openai.AuthenticationError: API key not found"), LLM_COPY),
    (Exception("KeyError: 'nodes'"), UNKNOWN_COPY),
])
def test_friendly_error_message_mapping(exc, expected):
    import app
    assert app._friendly_error_message(exc).startswith(expected)


def test_not_found_renders_info_and_hides_evidence(monkeypatch):
    from src.llm.generate import QueryAnswer

    def fake_run(*args, **kwargs):
        return QueryAnswer(
            prose="",
            evidence=[],
            not_found=True,
            suggestion="Try asking about T9 compatibility or wiring.",
        )

    # Patch in both namespaces — AppTest re-executes app.py on each .run(),
    # so the source module patch ensures the re-import picks up the fake.
    monkeypatch.setattr("src.pipeline.query.run_query_structured", fake_run)
    import app
    monkeypatch.setattr(app, "run_query_structured", fake_run)

    at = AppTest.from_file(APP_PATH).run(timeout=10)
    at.text_input[0].set_value("what is the color").run(timeout=10)
    at.button[0].click().run(timeout=10)

    assert any("Try asking about T9 compatibility" in i.value for i in at.info)
    # D-11: no *evidence* expander in not-found state. A "Debug Answer Payload"
    # expander is expected here too — the export panel renders for any
    # submitted answer, found or not — so check by label, not by count.
    assert "Graph Evidence" not in [e.label for e in at.expander]


def test_happy_path_renders_prose_and_evidence_expander(monkeypatch):
    from src.llm.generate import QueryAnswer, EvidenceTriple

    def fake_run(*args, **kwargs):
        return QueryAnswer(
            prose="The T9 is compatible with the C-wire adapter.",
            evidence=[
                EvidenceTriple(source="T9", relation="COMPATIBLE_WITH", target="C-Wire Adapter"),
            ],
            not_found=False,
            suggestion="",
        )

    monkeypatch.setattr("src.pipeline.query.run_query_structured", fake_run)
    import app
    monkeypatch.setattr(app, "run_query_structured", fake_run)

    at = AppTest.from_file(APP_PATH).run(timeout=10)
    at.text_input[0].set_value("T9 accessories?").run(timeout=10)
    at.button[0].click().run(timeout=10)

    # Prose rendered somewhere (st.write produces a markdown element)
    rendered_text = " ".join(md.value for md in at.markdown)
    assert "T9 is compatible with the C-wire adapter" in rendered_text
    # Evidence expander present with correct label
    expander_labels = [e.label for e in at.expander]
    assert "Graph Evidence" in expander_labels
    # Evidence triple formatted correctly inside the expander
    assert "T9 --[COMPATIBLE_WITH]--> C-Wire Adapter" in rendered_text


def test_neo4j_error_renders_friendly_message(monkeypatch):
    def raising_run(*args, **kwargs):
        raise Exception("Neo4j bolt connection refused")

    monkeypatch.setattr("src.pipeline.query.run_query_structured", raising_run)
    import app
    monkeypatch.setattr(app, "run_query_structured", raising_run)

    at = AppTest.from_file(APP_PATH).run(timeout=10)
    at.text_input[0].set_value("anything").run(timeout=10)
    at.button[0].click().run(timeout=10)

    assert len(at.error) >= 1
    assert "Could not connect to Neo4j" in at.error[0].value
