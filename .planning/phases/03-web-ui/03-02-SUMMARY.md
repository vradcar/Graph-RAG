---
phase: 03-web-ui
plan: "02"
subsystem: testing
tags: [streamlit, apptest, unit-tests, ui-verification]
dependency_graph:
  requires: [03-01]
  provides: [UI-01-verified, UI-02-verified, UI-03-verified]
  affects: []
tech_stack:
  added: []
  patterns: [AppTest harness, monkeypatch dual-namespace patching]
key_files:
  created:
    - tests/test_streamlit_app.py
  modified: []
decisions:
  - "Used index-based text_input[0] accessor instead of label-based accessor — AppTest 1.35 WidgetList.__call__ matches by key, not label"
  - "Sidebar Neo4j link verified via sidebar[0].proto string check — st.link_button renders as UnknownElement in AppTest 1.35 SpecialBlock (no link_button attribute exposed)"
  - "Patched run_query_structured in both src.pipeline.query and app namespaces to survive AppTest re-execution of app.py"
metrics:
  duration: "~10 minutes"
  completed: "2026-04-15"
  tasks_completed: 1
  tasks_total: 2
  files_created: 1
  files_modified: 0
---

# Phase 03 Plan 02: Streamlit UI Unit Tests Summary

AppTest-based unit tests for app.py covering widget structure, copy strings, branch logic, and error mapping — all 10 test items pass without a live Neo4j instance or LLM API key.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write AppTest-based unit tests for app.py | e9688f8 | tests/test_streamlit_app.py (created, 137 lines) |
| 2 | Human-verify live UI against Neo4j + LLM | PENDING | — human checkpoint, not yet verified |

## Task 2: Pending Human Checkpoint

**Task 2 is a `checkpoint:human-verify` gate.** It requires a human operator to:

1. Start Neo4j locally (`docker run` or `docker start neo4j-graphrag`)
2. Ensure `.env` has `NEO4J_PASSWORD` and an LLM API key set
3. Run `streamlit run app.py` from the repo root
4. Manually verify all 10 checklist sections from the plan:
   - Initial render (title, sidebar, no answer area)
   - Neo4j Browser link opens in new tab
   - Demo query 1 — accessories answer with evidence expander
   - Demo query 2 — wiring configs answer
   - Demo query 3 — specifications answer
   - Manual free-form question
   - Depth slider at 3 and 1
   - Error path (stop Neo4j, confirm friendly error banner)
   - Prohibited patterns absent (no iframe, no history, no provider picker)
   - Terminal cleanup (Ctrl-C exits cleanly)
5. Reply `approved` or report failed checklist items

This checkpoint CANNOT be automated — it verifies live browser behaviour (spinner animation, sidebar viewport layout, external link navigation, end-to-end pipeline response).

## pytest Output (Task 1)

```
collected 10 items

tests/test_streamlit_app.py::test_initial_render_has_required_widgets PASSED
tests/test_streamlit_app.py::test_initial_render_has_no_answer_area PASSED
tests/test_streamlit_app.py::test_friendly_error_message_mapping[exc0-...NEO4J...] PASSED
tests/test_streamlit_app.py::test_friendly_error_message_mapping[exc1-...NEO4J...] PASSED
tests/test_streamlit_app.py::test_friendly_error_message_mapping[exc2-...LLM...] PASSED
tests/test_streamlit_app.py::test_friendly_error_message_mapping[exc3-...LLM...] PASSED
tests/test_streamlit_app.py::test_friendly_error_message_mapping[exc4-...unknown...] PASSED
tests/test_streamlit_app.py::test_not_found_renders_info_and_hides_evidence PASSED
tests/test_streamlit_app.py::test_happy_path_renders_prose_and_evidence_expander PASSED
tests/test_streamlit_app.py::test_neo4j_error_renders_friendly_message PASSED

10 passed, 2 warnings in 0.97s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AppTest text_input accessor uses key, not label**
- **Found during:** Task 1 verification run
- **Issue:** `at.text_input("Your question")` raises `KeyError` — the `WidgetList.__call__` method matches by widget `key` attribute, not `label`. The text input in app.py has `key="question_input"`.
- **Fix:** Changed all three affected tests to use `at.text_input[0]` (index-based access), which is unambiguous since there is only one text input.
- **Files modified:** tests/test_streamlit_app.py
- **Commit:** e9688f8 (same task commit)

**2. [Rule 1 - Bug] at.sidebar.link_button not available in Streamlit 1.35 AppTest**
- **Found during:** Task 1 verification run
- **Issue:** `at.sidebar.link_button` raises `AttributeError: 'SpecialBlock' object has no attribute 'link_button'` — the sidebar block does not expose `link_button` as a typed accessor in this version.
- **Fix:** Verified the link button is present as `at.sidebar[0]` (an `UnknownElement`) with proto containing the URL. Updated assertion to `assert "http://localhost:7474" in str(sidebar_link.proto)`.
- **Files modified:** tests/test_streamlit_app.py
- **Commit:** e9688f8 (same task commit)

## Known Stubs

None — test file only, no UI stubs introduced.

## Threat Flags

None — test-only file, no network endpoints or auth paths introduced.

## Self-Check: PASSED

- [x] tests/test_streamlit_app.py exists (137 lines, >= 60)
- [x] Commit e9688f8 exists in git log
- [x] All 10 pytest items pass
- [x] No @pytest.mark.integration markers
- [x] All required grep patterns present (AppTest import, all 6 test function names, all locked copy strings, http://localhost:7474, Traversal Depth, Graph Evidence)
