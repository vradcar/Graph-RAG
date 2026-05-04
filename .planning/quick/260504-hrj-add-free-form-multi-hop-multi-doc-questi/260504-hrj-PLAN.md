---
quick_id: 260504-hrj
slug: add-free-form-multi-hop-multi-doc-questi
description: Add free-form multi-hop multi-doc question input to the UI so users can ask their own cross-document questions
date: 2026-05-04
status: planned
---

# Quick Task 260504-hrj: Free-form Multi-Hop Question Input

## Goal

The "Multi-Doc Queries" tab (Tab 2) currently only shows the 7 pre-curated queries.
Add a free-form input section at the top of Tab 2 so users can type their own
cross-document question, set traversal depth, and run it — with the same evidence
rendering as the Ask tab.

## Implementation Plan

### Task 1: Add free-form query section to Tab 2

**File:** `app.py`

**Action:** In the `with tab_mq:` block, insert a free-form input section ABOVE the
existing "Curated Queries" section:

```python
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
# ... existing curated queries below
```

The depth slider should sit beside the input (use st.columns to keep it compact).
Results render immediately below the Run button (no session state needed — transient).

**verify:** Tab 2 shows "Ask a Multi-Doc Question" section above the curated list with a text input, depth slider, and Run button

**done:** `mq_free_q = st.text_input(` present in `with tab_mq:` block in app.py

### Task 2: Commit

Commit `app.py` with message:
`feat(260504-hrj): add free-form multi-hop query input to Multi-Doc Queries tab`
