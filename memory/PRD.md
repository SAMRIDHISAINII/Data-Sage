# DataSage — AI Data Analysis Agent (PRD)

## Original problem statement
AI DATA ANALYSIS AGENT — Natural-Language Data Assistant. Business users want answers from structured data without writing SQL. Capabilities: natural-language data analysis, dataset understanding, SQL/Python analysis, automated insights, RAG/context layer, structured output, guardrails & validation, explainable results. Stack constraint: Python / Streamlit / Flask only, no JS.

## User choices
- Streamlit frontend (port 3000) + Flask backend (port 8001, run through uvicorn via a2wsgi) — pure Python
- LLMs: GPT 6 Luna + Claude Sonnet 5.5 via Emergent Universal Key (switchable in sidebar)
- Data sources: CSV/Excel upload, built-in samples (Sales Orders, Customer Accounts, HR & Workforce), external SQL (SQLAlchemy: Postgres/MySQL/SQLite)
- Auto charts (Plotly bar/line/pie/scatter)
- No login, session-based

## Architecture
- `backend/server.py` Flask routes (`/api/*`), NDJSON streaming for `/ask`
- `backend/agent.py` agentic loop: context → planner (JSON plan: approach sql|python, code, chart, assumptions) → sandboxed execution → up to 3 self-correcting attempts → validation → streamed explanation
- `backend/sandbox.py` guardrails: read-only DuckDB SQL (keyword blocklist, single statement), AST-validated pandas exec (no imports/dunder/IO), 30s timeout, 500-row cap
- `backend/context.py` RAG layer: schema card, column retrieval by token overlap, LLM column descriptions, relevant prior Q&A from Mongo
- `backend/datasets.py` loading, type coercion, profiling, parquet storage, sample generators, SQL connector, demo SQLite
- `frontend/app.py` + `frontend/ui/*` Streamlit UI (sidebar sources, overview/briefing, chat with streaming, charts, code & validation expanders)
- MongoDB: `datasets` (profile, overview, column descriptions), `messages` (Q&A history per session)

## User personas
- Business analyst / manager asking questions of exported CSVs or a warehouse table
- Data-curious ops user who wants explained, trustworthy numbers without SQL

## Core requirements (static)
NL question → validated code → result table + chart + plain-language explanation, with visible assumptions, code and validation checks.

## Implemented (2026-06)
- [x] Upload CSV/Excel with automatic numeric/date coercion
- [x] Sample datasets + demo SQLite; external SQL connector (SELECT-only)
- [x] Dataset profiling, briefing, auto insights, suggested questions, column semantics
- [x] Agentic SQL/Python planning with self-correction, guardrails, validation badges
- [x] Streaming explanation, Plotly charts, result table, code viewer
- [x] RAG context: column retrieval + conversation history for follow-ups
- [x] Model switch GPT 6 Luna / Claude Sonnet 5.5
- [x] Tested: 24/24 backend tests + Streamlit E2E (iteration_1)

## Backlog
- P1: Export answer/result as CSV or PDF report
- P1: Multi-dataset joins (ask across two tables)
- P2: Scheduled/recurring insight digests
- P2: Saved dashboards of pinned answers
- P2: Persist conversation across browser refresh (session restore)
