---
quick_id: 260504-hk3
slug: spin-up-a-quick-ui-to-test-and-demonstra
status: complete
date: 2026-05-04
tags: [ui, streamlit, demo, milestone-2]
key-files:
  modified:
    - app.py
decisions:
  - Installed streamlit and pandas into project venv (were missing) as Rule 3 auto-fix
  - Used pandas StyleFrame for verdict coloring in Tab 3
  - Tab 2 Run buttons store results in st.session_state.mq_results keyed by query id
metrics:
  duration: ~8 minutes
  completed: 2026-05-04
  tasks_completed: 3
  files_modified: 1
---

# Quick Task 260504-hk3: Milestone 2.0 Demo UI — Summary

## One-liner

4-tab Streamlit UI extending app.py with multi-doc query runner, graph-vs-vector comparison table, corpus viewer, and dry-run ingest button — covers every Milestone 2.0 feature.

## What Was Done

### Task 1 + 2 + 3: Refactor + helpers + commit (done as single atomic change)

Extended `app.py` from a single-page query UI into a 4-tab layout:

- **Tab 1 — Ask**: all existing content preserved verbatim. `_render_answer()` updated to show `[source_doc]` badge next to each evidence triple when `triple.source_doc` attribute is present (degrades gracefully via `hasattr`).

- **Tab 2 — Multi-Doc Queries**: loads `data/eval/multi_doc_queries.json`, renders 7 query cards with question, expected source-doc badges, graph-only win badge, and a "Run" button per query. Results stored in `st.session_state.mq_results[qid]` and rendered inline via `_render_answer()`.

- **Tab 3 — Graph vs Vector**: added `_parse_comparison_md()` helper (regex on pipe-table lines starting with `| mq`). Renders 7-row `st.dataframe` with green/orange verdict coloring via pandas Styler. Below the table, `_parse_graph_only_wins()` extracts the wins section and shows each as `st.success` callout.

- **Tab 4 — Corpus**: loads `data/raw/manifest.json`, shows 4 document cards with title, doc_id, SKU, retrieved_at, notes, and optional source link. "Dry-Run Ingest" button runs `scripts/batch_ingest.py --dry-run` via `subprocess.run` and shows stdout in `st.code`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] streamlit and pandas not installed in project venv**
- **Found during:** import verification step
- **Issue:** `streamlit` and `pandas` were absent from the virtual environment (`ls .venv/bin/` showed neither). The existing `requirements.txt` lists streamlit but the venv was not fully populated.
- **Fix:** Ran `.venv/bin/pip install streamlit pandas`.
- **Files modified:** none (environment change only)

## Known Stubs

None — all 4 tabs are wired to real data sources (`multi_doc_queries.json`, `multi_doc_comparison.md`, `manifest.json`) and live query calls.

## Threat Flags

None — no new network endpoints or auth paths introduced. Tab 4 dry-run ingest uses subprocess with a fixed script path; no user-controlled input flows into it.

## Self-Check: PASSED

- `app.py` exists and parses cleanly (ast.parse)
- `_parse_comparison_md` returns 7 rows (verified)
- Commit `207d733` present in git log
- `st.tabs(["🔍 Ask", ...])` present in app.py
