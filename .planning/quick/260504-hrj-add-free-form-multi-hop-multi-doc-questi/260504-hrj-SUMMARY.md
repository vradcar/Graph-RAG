---
quick_id: 260504-hrj
slug: add-free-form-multi-hop-multi-doc-questi
status: complete
date: 2026-05-04
commit: 6f65162
---

# Quick Task 260504-hrj: Free-form Multi-Hop Question Input — Summary

**One-liner:** Free-form text input with depth slider and Run button inserted at the top of Tab 2, above the 7 curated queries, reusing the existing `run_query_structured` + `_render_answer` pipeline.

## What Was Done

- Inserted a "Ask a Multi-Doc Question" section at the top of the `with tab_mq:` block in `app.py`.
- Section contains: `st.text_input` (key `mq_free_question`), `st.slider` (key `mq_free_depth`), and a primary "Run Multi-Hop Query" button (key `mq_free_run`).
- Results render inline via `_render_answer()` with the same graph-evidence expander used in Tab 1.
- Added `st.divider()` and renamed the curated section heading to "Curated Cross-Document Queries" to visually separate the two sections.
- All existing curated-query content is unchanged.

## Files Modified

- `app.py` — 34 lines inserted in the `with tab_mq:` block

## Deviations from Plan

None — implemented exactly as specified.

## Self-Check

- [x] `mq_free_q = st.text_input(` present in `with tab_mq:` block
- [x] Commit 6f65162 exists on branch topic/t1-sai
