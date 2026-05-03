# Phase 3: Web UI - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

A Streamlit web app that lets a user ask natural language questions about the T9 thermostat, displays the LLM-generated answer with its supporting graph-evidence triples, and provides a link into Neo4j Browser for visual graph exploration. Wraps the existing `run_query_structured()` pipeline — no new retrieval or generation logic.

</domain>

<decisions>
## Implementation Decisions

### Neo4j Visualization
- **D-01:** Expose Neo4j Browser via an external clickable link/button to `http://localhost:7474` (no iframe embed, no inline subgraph render). Satisfies UI-03 with zero CORS/framing risk.
- **D-02:** Link always opens the default Neo4j Browser view (full graph). No deep-linking into per-query subgraphs.

### Layout & Evidence Display
- **D-03:** Single-column layout. LLM prose rendered in the main area; graph-evidence triples placed inside an `st.expander("Graph Evidence")` below the prose (collapsed by default).
- **D-04:** Evidence triples rendered as a formatted bullet list in the form `source --[RELATION]--> target`, matching the CLI `format_answer()` output style.
- **D-05:** App has a sidebar containing: the Neo4j Browser link, a traversal-depth slider (default 2, range 1–3 to match `graph.max_default_depth`), and a read-only display of the active LLM provider + model (sourced from `settings.yaml`).

### Query UX
- **D-06:** Query input is a single-line `st.text_input` with an explicit Submit button ("Ask"). No chat interface, no multi-line text area.
- **D-07:** Below the input, render the 3 canonical demo queries (from Phase 2 D-10) as clickable buttons. Clicking a button populates the input and submits the query in one action.
- **D-08:** Only the latest answer is shown. Each submission replaces the previous answer — no scrolling history log.

### Loading & Error States
- **D-09:** Wrap the query pipeline call in `st.spinner("Querying knowledge graph…")` (or similar) to cover both Neo4j traversal and LLM generation as a single progress indicator.
- **D-10:** Catch backend exceptions (Neo4j connection errors, LLM errors, missing `NEO4J_PASSWORD` / API key) and render a friendly `st.error(...)` message. Do not surface raw tracebacks.
- **D-11:** When `QueryAnswer.not_found` is true, render an `st.info(...)` banner showing the model's `suggestion` text. Hide the evidence expander in this state.

### Claude's Discretion
- Page title, favicon/emoji, exact copy of spinner/error/info messages
- Streamlit `set_page_config` layout choice (`centered` vs `wide`) — pick whichever looks best with sidebar + expander
- Session-state plumbing for the "clickable demo query" behavior
- Whether to cache the `Neo4jGraphStore` + instructor client via `@st.cache_resource` to avoid reconnecting on every rerun

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Constraints & Requirements
- `.planning/PROJECT.md` — Project constraints (Neo4j, Groq, single-PDF scope, Streamlit/Gradio UI)
- `.planning/REQUIREMENTS.md` §UI — UI-01 (text input), UI-02 (answer display), UI-03 (Neo4j Browser link/embed)
- `.planning/ROADMAP.md` §"Phase 3: Web UI" — Goal and success criteria
- `CLAUDE.md` §"Web UI" — Streamlit 1.35.x recommendation and suggested panel layout

### Prior Phase Context
- `.planning/phases/02-query-pipeline/02-CONTEXT.md` — Decisions D-06 to D-10 on `QueryAnswer` structure and demo-query set that Phase 3 renders

### Existing Code (integration targets, reused as-is)
- `src/pipeline/query.py` — `run_query_structured(question, depth, provider=None, model=None) -> QueryAnswer` is the single entry point the UI will call
- `src/llm/generate.py` — `QueryAnswer` Pydantic model (prose, evidence, not_found, suggestion) and `format_answer()` for reference formatting
- `src/common/config.py` — `load_settings()` for sidebar display of provider/model
- `config/settings.yaml` — Source of default provider/model, `graph.max_default_depth`, Neo4j URI

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/pipeline/query.py::run_query_structured()` — Already accepts `depth`, `provider`, `model` overrides and returns a typed `QueryAnswer`. The UI can call it directly without touching retrieval or LLM code.
- `src/llm/generate.py::QueryAnswer` — Fields (`prose`, `evidence: list[EvidenceTriple]`, `not_found`, `suggestion`) map 1:1 onto the decisions above (D-03, D-04, D-11).
- `src/common/config.py::load_settings()` — Used for the sidebar's read-only provider/model display (D-05).

### Established Patterns
- `load_dotenv()` must be called before any module that reads env vars (see `src/pipeline/query.py:7-8`). The Streamlit entry point must follow the same pattern.
- Settings-driven configuration: runtime overrides come via function args, defaults come from `settings.yaml`.
- Provider factory pattern (`build_instructor_client`) — no need to re-instantiate in UI code; `run_query_structured()` already wraps this.

### Integration Points
- New top-level file (tentatively `src/ui/app.py` or `app.py` at repo root) invoked via `streamlit run ...`.
- `requirements.txt` additions: `streamlit==1.35.*` (not currently pinned).
- No changes to `src/pipeline/`, `src/retrieval/`, `src/llm/`, or `src/graph/` expected.

</code_context>

<specifics>
## Specific Ideas

- Demo query buttons use the exact 3 canned questions from Phase 2 D-10:
  1. "What accessories are compatible with the T9?"
  2. "What wiring configs does the T9 support?"
  3. "What are the T9 specifications?"
- CLAUDE.md's suggested panel layout informed D-03/D-05 (main area for Q&A, sidebar for Neo4j link, expander for graph context).

</specifics>

<deferred>
## Deferred Ideas

- Provider/model picker (runtime toggle in sidebar) — out of scope for UI-01/02/03; sidebar shows provider/model read-only only. CLI flags already exist for experimentation.
- Inline subgraph rendering (pyvis / streamlit-agraph) — deferred; external link to Neo4j Browser satisfies UI-03 for the demo.
- Per-query deep-link into Neo4j Browser (Cypher prefilled) — deferred with inline viz.
- Query history / chat-style persistent log — not in UI requirements; single-shot input is sufficient for the demo.
- Iframe embed of Neo4j Browser — rejected due to `X-Frame-Options` behavior and simpler alternative.
- Step-by-step status progress (entity resolution → traversal → generation) — deferred; single `st.spinner` is enough.
- Docker packaging / deployment beyond `streamlit run` locally — explicitly out of scope per REQUIREMENTS.md.

</deferred>

---

*Phase: 03-web-ui*
*Context gathered: 2026-04-15*
