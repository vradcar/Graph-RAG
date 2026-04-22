---
phase: 01-graph-schema-ingestion
plan: "01"
subsystem: graph-schema
tags: [schema, config, dependencies, neo4j, groq]
dependency_graph:
  requires: []
  provides:
    - src/graph/schema.py exports NODE_KIND, ALLOWED_RELATIONS, VALID_KINDS, VALID_RELATIONS
    - config/settings.yaml has neo4j and llm sections
    - requirements.txt pins all Phase 1 libraries
  affects:
    - plan 02 (Neo4jGraphStore imports NODE_KIND, VALID_RELATIONS from schema.py)
    - plan 04 (entity_extractor.py imports NODE_KIND, ALLOWED_RELATIONS from schema.py)
    - plan 05 (ingest CLI reads config/settings.yaml graph.neo4j_uri)
tech_stack:
  added:
    - PyMuPDF==1.27.2.2
    - pdfplumber==0.11.9
    - groq==1.1.2
    - instructor==1.15.1
    - pydantic==2.12.5
    - pytest==9.0.2
    - neo4j==5.28.3 (upgraded from 5.28.1)
  patterns:
    - Closed-world enum via Literal + get_args() for compile-time and runtime safety
    - __post_init__ validation on dataclasses for domain invariant enforcement
key_files:
  created: []
  modified:
    - src/graph/schema.py
    - config/settings.yaml
    - requirements.txt
    - .env.example
decisions:
  - "Used Literal + get_args() for NODE_KIND/ALLOWED_RELATIONS to enable both type-checking and runtime set membership checks from a single source of truth"
  - "Preserved all existing dataclass field names (node_id, label, kind, properties, source_id, target_id, relation) — downstream plans depend on these"
  - "neo4j_password in settings.yaml set to default Docker password 'password'; callers override via os.getenv('NEO4J_PASSWORD')"
  - "llm.model set to llama-3.1-8b-instant as single configurable placeholder per CLAUDE.md constraint"
metrics:
  duration_seconds: 56
  completed_date: "2026-04-15"
  tasks_completed: 2
  files_modified: 4
---

# Phase 01 Plan 01: Graph Schema Extension and Config Setup Summary

**One-liner:** Closed-world schema constants (5 node kinds, 4 relation types) added to schema.py via Literal + get_args(), with Neo4j/Groq config and pinned Phase 1 dependencies.

## What Was Done

### Task 1: Extend schema.py with closed-world enum constants and kind validation

Extended `src/graph/schema.py` to add:

- `NODE_KIND = Literal["Product", "Accessory", "WiringConfig", "HVACSystemType", "Spec"]` — type alias for the 5 valid node kinds
- `ALLOWED_RELATIONS = Literal["COMPATIBLE_WITH", "REPLACES", "SUPPORTS_WIRING", "HAS_SPEC"]` — type alias for the 4 valid relation types
- `VALID_KINDS: set[str] = set(get_args(NODE_KIND))` — runtime set for membership checks
- `VALID_RELATIONS: set[str] = set(get_args(ALLOWED_RELATIONS))` — runtime set for membership checks
- `EntityNode.__post_init__` — raises `ValueError` if `kind` not in `VALID_KINDS`
- `RelationEdge.__post_init__` — raises `ValueError` if `relation` not in `VALID_RELATIONS`

All existing dataclass fields preserved unchanged. Imports updated to include `Literal, get_args`.

**Exports added:** `NODE_KIND`, `ALLOWED_RELATIONS`, `VALID_KINDS`, `VALID_RELATIONS`

### Task 2: Update config/settings.yaml, requirements.txt, and .env.example

**config/settings.yaml:**
- Switched `graph.backend` from `networkx` to `neo4j`
- Added `graph.neo4j_uri: bolt://localhost:7687`
- Added `graph.neo4j_user: neo4j`
- Added `graph.neo4j_password: "password"` (default Docker password; override via `NEO4J_PASSWORD` env var)
- Added `llm:` section with `provider: groq` and `model: llama-3.1-8b-instant`
- Preserved all existing keys (project, retrieval, evaluation)

**requirements.txt:**
- Upgraded `neo4j` from 5.28.1 to 5.28.3
- Added: `PyMuPDF==1.27.2.2`, `pdfplumber==0.11.9`, `groq==1.1.2`, `instructor==1.15.1`, `pydantic==2.12.5`, `pytest==9.0.2`

**.env.example:**
- Appended `GROQ_API_KEY=your_groq_api_key_here` placeholder
- Appended `NEO4J_PASSWORD=password` override placeholder
- Preserved existing `LLM_PROVIDER`, `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` entries

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 86a7568 | feat(01-01): extend schema.py with closed-world enum constants and kind validation |
| 2 | ec687be | chore(01-01): update config, requirements, and env example for Neo4j + Groq |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None introduced in this plan. schema.py dataclasses are complete; config values are real defaults.

## Threat Flags

None. No new network endpoints, auth paths, or file access patterns introduced. T-01-02 (.env.example placeholder only) and T-01-03 (local config, no network exposure) are both accepted per the plan's threat model.

## Self-Check: PASSED

- `src/graph/schema.py` — FOUND, verified imports and validation
- `config/settings.yaml` — FOUND, verified neo4j_uri and llm.model via load_settings()
- `requirements.txt` — FOUND, verified all pinned versions
- `.env.example` — FOUND, verified GROQ_API_KEY present
- Commit 86a7568 — FOUND
- Commit ec687be — FOUND
