"""Streamlit UI for the Honeywell T9 GraphRAG demo."""
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any os.getenv() calls

import os
import json
import subprocess
import re

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


_STAGE_BADGES = {
    "fast_path": ("🟢 Stage 1: Fast path (regex + keyword graph retrieval)", "success"),
    "llm_understanding": ("🟡 Stage 2: LLM query understanding → graph traversal", "info"),
    "vector_fallback": ("🟠 Stage 3: Vector fallback (bag-of-words over Neo4j nodes)", "warning"),
    "none": ("⚪ No stage produced triples — pipeline returned not_found", "error"),
}


def _render_pipeline_stage(answer) -> None:
    """Render which retrieval stage produced the answer."""
    stage = getattr(answer, "pipeline_stage", "") or "none"
    label, level = _STAGE_BADGES.get(stage, (f"Stage: {stage}", "info"))
    getattr(st, level)(label)


def _render_answer(answer) -> None:
    """Render a QueryAnswer object into the Streamlit main area."""
    _render_pipeline_stage(answer)
    if answer.not_found:
        # D-11: show the model's suggestion via st.info; no evidence expander
        st.info(answer.suggestion or "No relevant information found in the knowledge graph.")
        return
    st.write(answer.prose)
    with st.expander("Graph Evidence", expanded=False):
        if not answer.evidence:
            st.caption("No supporting triples were returned.")
        else:
            lines = []
            for triple in answer.evidence:
                line = f"- {triple.source} --[{triple.relation}]--> {triple.target}"
                if hasattr(triple, "source_doc") and triple.source_doc:
                    line += f"  <span style='color: #888; font-size: 0.85em;'>[{triple.source_doc}]</span>"
                lines.append(line)
            st.markdown("\n".join(lines), unsafe_allow_html=True)


def _build_export_payload(question: str, depth: int, answer) -> dict:
    """Build a serializable payload for report evidence export."""
    return {
        "question": question,
        "depth": depth,
        "answer": answer.prose,
        "not_found": answer.not_found,
        "suggestion": answer.suggestion,
        "evidence": [
            {"source": t.source, "relation": t.relation, "target": t.target}
            for t in answer.evidence
        ],
    }


def _parse_comparison_md(path: str) -> list:
    """Parse the multi_doc_comparison.md summary table into a list of dicts."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("| mq"):
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if len(parts) >= 6:
                        rows.append({
                            "id": parts[0],
                            "question": parts[1],
                            "verdict": parts[2],
                            "graph_distinct_docs": parts[3],
                            "vector_covered": parts[4],
                            "graph_only": parts[5],
                        })
    except FileNotFoundError:
        pass
    return rows


def _parse_graph_only_wins(path: str) -> list:
    """Extract Graph-only Wins bullet lines from the comparison markdown."""
    wins = []
    try:
        with open(path) as f:
            in_section = False
            for line in f:
                if line.strip() == "## Graph-only Wins":
                    in_section = True
                    continue
                if in_section:
                    if line.startswith("## "):
                        break
                    m = re.match(r"^- \*\*(mq\d+)\*\*: (.+)", line.strip())
                    if m:
                        wins.append({"id": m.group(1), "question": m.group(2)})
    except FileNotFoundError:
        pass
    return wins


# ---------------------------------------------------------------------------
# Page configuration (UI-SPEC §"Page Configuration")
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Honeywell GraphRAG Demo",
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
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_question" not in st.session_state:
    st.session_state.last_question = ""
if "last_depth" not in st.session_state:
    st.session_state.last_depth = default_depth
# Per-query results for Tab 2
if "mq_results" not in st.session_state:
    st.session_state.mq_results = {}

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
# Main area — title, caption, and 4-tab layout
# ---------------------------------------------------------------------------

st.title("Honeywell GraphRAG — Milestone 2.0 Demo")
st.caption("4-PDF corpus · 7 multi-doc queries · Graph vs Vector comparison · Batch ingest runner")

tab_ask, tab_mq, tab_compare, tab_corpus = st.tabs(
    ["🔍 Ask", "📚 Multi-Doc Queries", "📊 Graph vs Vector", "🗄️ Corpus"]
)

# ===========================================================================
# TAB 1 — Ask (existing content verbatim, with source_doc badge added above)
# ===========================================================================

with tab_ask:
    st.subheader("Ask the Knowledge Graph")

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

    # Demo query buttons
    DEMO_QUERIES = [
        "What accessories are compatible with the T9?",
        "What wiring configs does the T9 support?",
        "What are the T9 specifications?",
    ]

    demo_cols = st.columns(3)
    for col, demo_q in zip(demo_cols, DEMO_QUERIES):
        with col:
            if st.button(demo_q):
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
                with st.spinner("Querying knowledge graph…"):
                    answer = run_query_structured(
                        current_question,
                        depth=depth,
                        provider=provider_name,
                        model=model_name,
                    )
            except Exception as exc:  # noqa: BLE001
                message = _friendly_error_message(exc)
                st.error(message)
            else:
                st.session_state.last_answer = answer
                st.session_state.last_question = current_question
                st.session_state.last_depth = depth
                _render_answer(answer)

    # Evidence export panel
    if st.session_state.last_answer is not None:
        st.divider()
        st.subheader("Export Evidence")
        payload = _build_export_payload(
            st.session_state.last_question,
            st.session_state.last_depth,
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

# ===========================================================================
# TAB 2 — Multi-Doc Queries
# ===========================================================================

with tab_mq:
    st.subheader("Ask a Multi-Doc Question")
    st.caption("Type any cross-document question — the graph will traverse all 4 PDFs.")

    mq_free_col, mq_free_btn_col = st.columns([4, 1])
    with mq_free_col:
        mq_free_q = st.text_input(
            "Your multi-doc question",
            placeholder="e.g. Which thermostats support heat-pump systems across multiple documents?",
            key="mq_free_question",
        )
    with mq_free_btn_col:
        mq_free_depth = st.slider("Depth", min_value=1, max_value=3, value=2, key="mq_free_depth")

    mq_free_run = st.button("Run Multi-Hop Query", type="primary", key="mq_free_run")

    if mq_free_run:
        if not mq_free_q.strip():
            st.warning("Please enter a question.")
        else:
            try:
                with st.spinner("Running multi-hop graph traversal…"):
                    free_answer = run_query_structured(
                        mq_free_q,
                        depth=mq_free_depth,
                        provider=provider_name,
                        model=model_name,
                    )
            except Exception as exc:
                st.error(_friendly_error_message(exc))
            else:
                _render_answer(free_answer)

    st.divider()
    st.subheader("Curated Cross-Document Queries")
    st.caption(
        "These queries are designed to exercise cross-document graph traversal. "
        "Queries marked Graph-only Win cannot be answered by vector search alone."
    )

    mq_path = os.path.join(os.getcwd(), "data", "eval", "multi_doc_queries.json")
    try:
        with open(mq_path) as f:
            mq_queries = json.load(f)
    except FileNotFoundError:
        st.error(f"multi_doc_queries.json not found at {mq_path}")
        mq_queries = []

    for mq in mq_queries:
        qid = mq.get("id", "")
        question_text = mq.get("question", "")
        expected_docs = mq.get("expected_source_docs", [])
        is_graph_only = mq.get("graph_only", False)
        q_depth = mq.get("depth", depth)

        with st.container():
            col_left, col_right = st.columns([5, 1])
            with col_left:
                badge_graph = " **Graph-only Win**" if is_graph_only else ""
                st.markdown(f"**{qid}**{badge_graph}")
                st.write(question_text)
                doc_badges = " ".join(f"`{d}`" for d in expected_docs)
                st.caption(f"Expected source docs: {doc_badges}")
            with col_right:
                run_clicked = st.button("Run", key=f"run_{qid}")

            if run_clicked:
                try:
                    with st.spinner(f"Running {qid}…"):
                        mq_answer = run_query_structured(
                            question_text,
                            depth=q_depth,
                            provider=provider_name,
                            model=model_name,
                        )
                    st.session_state.mq_results[qid] = mq_answer
                except Exception as exc:  # noqa: BLE001
                    st.error(_friendly_error_message(exc))

            if qid in st.session_state.mq_results:
                with st.container():
                    _render_answer(st.session_state.mq_results[qid])

            st.divider()

# ===========================================================================
# TAB 3 — Graph vs Vector comparison
# ===========================================================================

with tab_compare:
    st.subheader("Graph vs Vector Retrieval Comparison")
    st.caption("Pre-computed results from Phase 4. No live computation — static display.")

    comp_path = os.path.join(os.getcwd(), "data", "eval", "multi_doc_comparison.md")
    rows = _parse_comparison_md(comp_path)

    if rows:
        import pandas as pd

        df = pd.DataFrame(rows)

        def _color_verdict(val):
            if val == "graph":
                return "background-color: #d4edda; color: #155724;"
            elif val == "tie":
                return "background-color: #fff3cd; color: #856404;"
            return ""

        styled = df.style.applymap(_color_verdict, subset=["verdict"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.warning(f"Could not parse comparison table from {comp_path}")

    st.divider()
    st.subheader("Graph-only Wins")
    wins = _parse_graph_only_wins(comp_path)
    if wins:
        for w in wins:
            st.success(f"**{w['id']}**: {w['question']}")
    else:
        st.info("No graph-only wins found or file not available.")

# ===========================================================================
# TAB 4 — Corpus
# ===========================================================================

with tab_corpus:
    st.subheader("4-PDF Corpus")
    st.caption("Documents ingested into the knowledge graph.")

    manifest_path = os.path.join(os.getcwd(), "data", "raw", "manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        documents = manifest.get("documents", [])
    except FileNotFoundError:
        st.error(f"manifest.json not found at {manifest_path}")
        documents = []

    for doc in documents:
        with st.container():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{doc.get('title', 'Unknown')}**")
                st.caption(
                    f"doc_id: `{doc.get('doc_id', '')}` | "
                    f"SKU: `{doc.get('sku', 'N/A')}` | "
                    f"retrieved: {doc.get('retrieved_at', 'N/A')}"
                )
                if doc.get("notes"):
                    st.info(doc["notes"])
            with c2:
                if doc.get("source_url"):
                    st.link_button("Source", f"https://{doc['source_url']}")
            st.divider()

    st.subheader("Dry-Run Ingest")
    st.caption(
        "Run the batch ingestion pipeline in dry-run mode to verify all 4 PDFs "
        "would be processed without writing to Neo4j."
    )

    if st.button("Run Dry-Run Ingest", type="secondary"):
        batch_script = os.path.join(os.getcwd(), "scripts", "batch_ingest.py")
        with st.spinner("Running dry-run ingest…"):
            result = subprocess.run(
                ["python", batch_script, "--dry-run"],
                capture_output=True,
                text=True,
                cwd=os.getcwd(),
            )
        combined = result.stdout
        if result.stderr:
            combined += "\n--- stderr ---\n" + result.stderr
        st.code(combined or "(no output)", language="text")
        if result.returncode == 0:
            st.success("Dry-run completed successfully.")
        else:
            st.warning(f"Process exited with code {result.returncode}.")
