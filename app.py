"""Streamlit UI for the Honeywell T9 GraphRAG demo."""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

import streamlit as st

from src.common.config import load_settings
from src.pipeline.query import run_query_structured


# ---------------------------------------------------------------------------
# Helper functions (defined before the rendering logic so they are available
# when Streamlit executes the module top-to-bottom on every rerun)
# ---------------------------------------------------------------------------

def _friendly_error_message(exc: Exception) -> str:
    """Classify an exception and return a user-friendly error string."""
    text = str(exc).lower()
    if "neo4j" in text or "bolt" in text or "connection refused" in text or "serviceunavailable" in text:
        return (
            "Could not connect to Neo4j. Make sure the database is running at "
            "bolt://localhost:7687 and NEO4J_PASSWORD is set in your .env file."
        )
    if "api key" in text or "unauthorized" in text or "authentication" in text or "401" in text:
        return (
            "The LLM call failed. Check that your API key is set correctly in .env "
            "and that the model name in settings.yaml is valid."
        )
    return "Something went wrong. Check the terminal for details."


def _render_answer(answer) -> None:
    """Render a QueryAnswer object into the Streamlit main area."""
    if answer.not_found:
        # D-11: show the model's suggestion via st.info; no evidence expander
        st.info(answer.suggestion or "No relevant information found in the knowledge graph.")
        return
    st.write(answer.prose)
    with st.expander("Graph Evidence", expanded=False):
        if not answer.evidence:
            st.caption("No supporting triples were returned.")
        else:
            lines = [
                f"- {triple.source} --[{triple.relation}]--> {triple.target}"
                for triple in answer.evidence
            ]
            st.markdown("\n".join(lines))


# ---------------------------------------------------------------------------
# Page configuration (UI-SPEC §"Page Configuration")
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Honeywell T9 GraphRAG",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Cached settings loader (UI-SPEC §"Caching Contract")
# Only settings loading is cached; run_query_structured must NOT be cached.
# ---------------------------------------------------------------------------

@st.cache_resource
def load_settings_cached() -> dict:
    return load_settings()


settings = load_settings_cached()
default_depth = int(settings.get("graph", {}).get("max_default_depth", 2))
provider_name = settings.get("llm", {}).get("provider", "unknown")
model_name = settings.get("llm", {}).get("model", "unknown")

# ---------------------------------------------------------------------------
# Session-state init (UI-SPEC §"Session State Contract")
# ---------------------------------------------------------------------------

if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""
if "auto_submit" not in st.session_state:
    st.session_state.auto_submit = False

# ---------------------------------------------------------------------------
# Sidebar (UI-SPEC §"Widget Contract" → "Sidebar Widgets")
# ---------------------------------------------------------------------------

with st.sidebar:
    st.link_button("Open Neo4j Browser", "http://localhost:7474")
    depth = st.slider("Traversal Depth", min_value=1, max_value=3, value=default_depth)
    st.divider()
    st.caption(f"Provider: {provider_name}")
    st.caption(f"Model: {model_name}")

# ---------------------------------------------------------------------------
# Main area — title and caption (UI-SPEC §"Copywriting Contract")
# ---------------------------------------------------------------------------

st.title("Honeywell T9 Knowledge Graph")
st.caption("Ask a question about the T9 thermostat's compatibility, wiring, or specifications.")

# ---------------------------------------------------------------------------
# Input row + Ask button (UI-SPEC §"Widget Contract" → "Main Area Widgets")
# ---------------------------------------------------------------------------

input_col, submit_col = st.columns([4, 1])
with input_col:
    question = st.text_input(
        "Your question",
        value=st.session_state.pending_question,
        placeholder="e.g. What accessories are compatible with the T9?",
        key="question_input",
    )
with submit_col:
    ask_clicked = st.button("Ask", type="primary")

# ---------------------------------------------------------------------------
# Demo query buttons (UI-SPEC §"Session State Contract" + "Copywriting Contract")
# 3 columns, secondary button style, exact copy strings.
# ---------------------------------------------------------------------------

DEMO_QUERIES = [
    "What accessories are compatible with the T9?",
    "What wiring configs does the T9 support?",
    "What are the T9 specifications?",
]

demo_cols = st.columns(3)
for col, demo_q in zip(demo_cols, DEMO_QUERIES):
    with col:
        if st.button(demo_q):
            # A demo button click happens on rerun N; we set pending_question + auto_submit
            # then call st.rerun() to trigger rerun N+1 where text_input reads the new value
            # and the submit branch fires via auto_submit. Streamlit 1.35 requires one rerun
            # for a button click to propagate to a sibling text_input widget.
            st.session_state.pending_question = demo_q
            st.session_state.auto_submit = True
            st.rerun()

# ---------------------------------------------------------------------------
# Submit resolution + pipeline call (UI-SPEC D-09, D-10, D-11)
# ---------------------------------------------------------------------------

submit = ask_clicked or st.session_state.auto_submit
if submit:
    st.session_state.auto_submit = False  # clear before pipeline call
    current_question = question or st.session_state.pending_question
    if not current_question.strip():
        st.warning("Please enter a question.")
    else:
        st.session_state.pending_question = current_question
        try:
            with st.spinner("Querying knowledge graph…"):
                answer = run_query_structured(
                    current_question,
                    depth=depth,
                    provider=provider_name,
                    model=model_name,
                )
        except Exception as exc:  # noqa: BLE001 — friendly error only, no raw traceback
            message = _friendly_error_message(exc)
            st.error(message)
        else:
            _render_answer(answer)
