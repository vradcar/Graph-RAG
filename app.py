"""Streamlit UI for the Honeywell T9 GraphRAG demo."""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

import streamlit as st
import json

from src.common.config import load_settings
from src.pipeline.query import run_query_structured


# Helper functions

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


def _triples_to_dot(evidence) -> str:
    """Convert evidence triples into a Graphviz DOT string for visualization."""
    lines = ["digraph evidence {", "  rankdir=LR;", "  node [shape=box style=rounded fontsize=11];",
             "  edge [fontsize=9];"]
    seen_edges = set()
    for triple in evidence:
        # Sanitise: DOT node IDs must be quoted to handle spaces and special chars
        src = triple.source.replace('"', '\\"')
        tgt = triple.target.replace('"', '\\"')
        rel = triple.relation.replace('"', '\\"')
        key = (src, rel, tgt)
        if key not in seen_edges:
            seen_edges.add(key)
            lines.append(f'  "{src}" -> "{tgt}" [label="{rel}"];')
    lines.append("}")
    return "\n".join(lines)


def _render_answer(answer, mode: str = "graph") -> None:
    """Render a QueryAnswer object into the Streamlit main area."""
    if answer.not_found:
        st.info(answer.suggestion or "No relevant information found in the knowledge graph.")
        return

    st.write(answer.prose)

    with st.expander("Graph Evidence", expanded=False):
        st.caption(f"Retrieval mode: **{mode}** · {len(answer.evidence)} triple(s) returned")
        if not answer.evidence:
            st.caption("No supporting triples were returned.")
        else:
            lines = [
                f"- **{triple.source}** --[{triple.relation}]--> **{triple.target}**"
                for triple in answer.evidence
            ]
            st.markdown("\n".join(lines))

    if answer.evidence:
        with st.expander("Graph Visualization", expanded=False):
            st.caption("Directed graph of retrieved evidence triples.")
            dot_src = _triples_to_dot(answer.evidence)
            st.graphviz_chart(dot_src)


def _build_export_payload(question: str, depth: int, mode: str, answer) -> dict:
    """Build a serializable payload for report evidence export."""
    return {
        "question": question,
        "depth": depth,
        "mode": mode,
        "answer": answer.prose,
        "not_found": answer.not_found,
        "suggestion": answer.suggestion,
        "evidence": [
            {"source": t.source, "relation": t.relation, "target": t.target}
            for t in answer.evidence
        ],
    }


# Page configuration

st.set_page_config(
    page_title="Honeywell T9 GraphRAG",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Cached settings loader

@st.cache_resource
def load_settings_cached() -> dict:
    return load_settings()


settings = load_settings_cached()
default_depth = int(settings.get("graph", {}).get("max_default_depth", 2))
provider_name = settings.get("llm", {}).get("provider", "unknown")
model_name = settings.get("llm", {}).get("model", "unknown")

# Session-state init

if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""
if "auto_submit" not in st.session_state:
    st.session_state.auto_submit = False
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_question" not in st.session_state:
    st.session_state.last_question = ""
if "last_depth" not in st.session_state:
    st.session_state.last_depth = default_depth
if "last_mode" not in st.session_state:
    st.session_state.last_mode = "graph"

# Sidebar

with st.sidebar:
    st.link_button("Open Neo4j Browser", "http://localhost:7474")
    st.divider()

    retrieval_mode = st.radio(
        "Retrieval Mode",
        options=["graph", "vector", "hybrid"],
        index=0,
        help=(
            "**graph** — traverses the knowledge graph for relationship-aware answers\n\n"
            "**vector** — keyword similarity search over stored entities\n\n"
            "**hybrid** — merges graph traversal + vector search, graph hits ranked first"
        ),
    )
    depth = st.slider("Traversal Depth", min_value=1, max_value=3, value=default_depth)
    st.divider()
    st.caption(f"Provider: {provider_name}")
    st.caption(f"Model: {model_name}")

# Main area — title and mode badge

st.title("Honeywell T9 Knowledge Graph")
st.caption(
    "Ask a question about the T9 thermostat's compatibility, wiring, or specifications. "
    "Switch retrieval modes in the sidebar to compare graph vs vector results."
)

MODE_LABEL = {"graph": "🔵 Graph", "vector": "🟡 Vector", "hybrid": "🟢 Hybrid"}
MODE_DESC = {
    "graph": "Traverses Neo4j relationships — best for compatibility and multi-hop queries.",
    "vector": "Keyword similarity over entity text — best for spec and name lookups.",
    "hybrid": "Graph hits ranked first, then vector hits merged in.",
}
st.info(f"**{MODE_LABEL[retrieval_mode]}** — {MODE_DESC[retrieval_mode]}")

# Input row + Ask button

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

# 8 showcase queries — chosen to visibly differentiate graph vs vector

DEMO_QUERIES = [
    "What accessories are compatible with the T9?",
    "What wiring configs does the T9 support?",
    "What are the T9 specifications?",
    "What is the modern replacement for the RTH6580WF?",
    "Does the T9 need a C-wire for heat-only systems?",
    "What HVAC system types work with the T9?",
    "What are the T9 electrical specifications?",
    "List discontinued thermostats and their replacements.",
]

st.markdown("**Try a showcase query:**")
cols_a = st.columns(4)
cols_b = st.columns(4)
for i, (col, demo_q) in enumerate(zip(cols_a + cols_b, DEMO_QUERIES)):
    with col:
        if st.button(demo_q, key=f"demo_{i}", use_container_width=True):
            st.session_state.pending_question = demo_q
            st.session_state.auto_submit = True
            st.rerun()

# Submit resolution + pipeline call

submit = ask_clicked or st.session_state.auto_submit
if submit:
    st.session_state.auto_submit = False
    current_question = question or st.session_state.pending_question
    if not current_question.strip():
        st.warning("Please enter a question.")
    else:
        st.session_state.pending_question = current_question
        try:
            with st.spinner(f"Querying knowledge graph ({retrieval_mode} mode)…"):
                answer = run_query_structured(
                    current_question,
                    depth=depth,
                    provider=provider_name,
                    model=model_name,
                    mode=retrieval_mode,
                )
        except Exception as exc:  # noqa: BLE001
            message = _friendly_error_message(exc)
            st.error(message)
        else:
            st.session_state.last_answer = answer
            st.session_state.last_question = current_question
            st.session_state.last_depth = depth
            st.session_state.last_mode = retrieval_mode
            _render_answer(answer, mode=retrieval_mode)

# Export panel (shown after any successful query)

if st.session_state.last_answer is not None:
    st.divider()
    st.subheader("Export Evidence")
    payload = _build_export_payload(
        st.session_state.last_question,
        st.session_state.last_depth,
        st.session_state.last_mode,
        st.session_state.last_answer,
    )
    with st.expander("Debug Answer Payload", expanded=False):
        st.json(payload)
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download Evidence (JSON)",
            data=json.dumps(payload, indent=2),
            file_name="query_evidence.json",
            mime="application/json",
        )
    with col2:
        text_lines = [
            f"Question: {payload['question']}",
            f"Depth: {payload['depth']}",
            f"Mode: {payload['mode']}",
            "",
            "Answer:",
            payload["answer"] or "(no answer)",
            "",
            "Evidence:",
        ]
        for e in payload["evidence"]:
            text_lines.append(f"- {e['source']} --[{e['relation']}]--> {e['target']}")
        if not payload["evidence"]:
            text_lines.append("- (none)")
        st.download_button(
            label="Download Evidence (TXT)",
            data="\n".join(text_lines),
            file_name="query_evidence.txt",
            mime="text/plain",
        )
