import json
import uuid

import pandas as pd

import llm
from context import build_context, schema_card, sample_rows
from db import datasets_col, messages_col, now_iso
from sandbox import MAX_ROWS, GuardrailError, run_python, run_sql, to_frame

MAX_ATTEMPTS = 3

PLANNER_SYSTEM = """You are a senior data analyst agent. You turn a business user's natural-language question into ONE executable analysis step over a single tabular dataset, then return a strict JSON plan.

Execution environments:
1. approach "sql": DuckDB SQL. The dataset is a table named `data`. Quote column names with double quotes when they contain spaces or special characters. Use DuckDB functions (date_trunc, strftime, EXTRACT, ROUND, etc.). Only a single SELECT/WITH statement. Never modify data.
2. approach "python": pandas. The dataset is a DataFrame named `df`; `pd` and `np` are available. No imports, no file/network access, no attributes starting with `to_`/`read_`. Assign the final output (DataFrame, Series, scalar or dict) to a variable named `result`.

Rules:
- Prefer "sql" for filters, aggregations, rankings, group-bys, time bucketing. Prefer "python" for statistics (correlation, percentiles, growth rates, pivots, cohort/rolling computations) or multi-step transformations.
- Use only columns that exist in the schema. Respect their types (datetime columns are real timestamps).
- Keep results compact: at most ~500 rows; sort meaningfully; round money to 2 decimals.
- For time trends aggregate to a sensible grain (month/quarter) and order chronologically.
- Make assumptions explicit (e.g. "revenue = revenue column, not quantity*unit_price").
- If the question is not about this dataset, is impossible with these columns, or is ambiguous in a way that changes the answer, set needs_clarification=true and explain briefly; leave code empty.
- Chart: pick "bar" for category comparisons/rankings, "line" for time series, "pie" for share-of-total with <= 8 slices, "scatter" for two numeric measures, "none" for single values or wide tables. x must be a result column; y a result column or list of numeric result columns.

Reply with ONLY a JSON object (no markdown fences, no prose):
{
  "intent": "one sentence restating what will be computed",
  "approach": "sql" | "python",
  "code": "the SQL query or python code",
  "chart": {"type": "bar|line|pie|scatter|none", "x": "column", "y": "column or [columns]", "title": "short title"},
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification": ""
}"""

EXPLAINER_SYSTEM = """You are a data analyst explaining results to a business user who does not read code.
Use ONLY numbers that appear in the result preview or data context. Never invent values. Be specific and concise.
Format in markdown:
**Answer** — a direct 1-3 sentence answer with the key figures.
**Key insights** — 2-4 bullets: trends, outliers, concentrations, comparisons (with numbers and % where possible).
**How this was computed** — 1-2 plain-language sentences (mention filters/grouping; no code).
**Caveats** — only if relevant (data gaps, assumptions, truncated results)."""

OVERVIEW_SYSTEM = """You are a data analyst onboarding a business user to a new dataset. Given the schema and sample rows, reply with ONLY a JSON object:
{
  "briefing": "3-4 sentence markdown description of what this dataset represents, its grain (what one row is), time coverage and key measures/dimensions",
  "insights": ["3-5 concrete observations grounded in the provided statistics (ranges, dominant categories, nulls, skew)"],
  "column_descriptions": {"<column>": "<= 12 word business meaning", ...for every column},
  "suggested_questions": ["5 high-value natural-language questions a business user would ask, answerable from these columns"]
}"""


def _chart_type_check(chart: dict, frame: pd.DataFrame, cols_meta: list[dict]) -> tuple[dict, str | None]:
    chart = dict(chart or {})
    ctype = chart.get("type", "none")
    if ctype in (None, "", "none") or frame.empty or (frame.shape == (1, 1)):
        return {"type": "none"}, None
    cols = list(frame.columns)
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(frame[c])]
    non_numeric = [c for c in cols if c not in numeric]
    note = None
    x = chart.get("x")
    y = chart.get("y")
    ys = y if isinstance(y, list) else ([y] if y else [])
    ys = [c for c in ys if c in cols]
    if x not in cols:
        x = (non_numeric or cols)[0]
        note = "chart x-axis adjusted to an existing column"
    if not ys:
        ys = [c for c in numeric if c != x][:3]
        note = note or "chart series adjusted to numeric columns"
    if not ys:
        return {"type": "none"}, "chart dropped: no numeric series"
    if ctype == "pie" and (len(frame) > 10 or len(ys) != 1):
        ctype = "bar"
        note = "pie switched to bar (too many slices)"
    if ctype == "scatter" and x not in numeric:
        ctype = "bar"
    return {"type": ctype, "x": x, "y": ys if len(ys) > 1 else ys[0], "title": chart.get("title") or ""}, note


def _frame_payload(frame: pd.DataFrame) -> dict:
    truncated = len(frame) > MAX_ROWS
    f = frame.head(MAX_ROWS)
    return {
        "columns": list(f.columns),
        "rows": json.loads(f.to_json(orient="records", date_format="iso")),
        "row_count": int(len(f)),
        "truncated": truncated,
    }


def ask_stream(dataset: dict, df: pd.DataFrame, question: str, session_id: str, model_key: str):
    checks: list[dict] = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    yield {"type": "status", "message": "Retrieving dataset context…"}
    context = build_context(dataset, df, question, session_id)
    planner = llm.new_chat(model_key, PLANNER_SYSTEM)
    prompt = f"DATA CONTEXT\n{context}\n\nUSER QUESTION\n{question}"

    yield {"type": "status", "message": "Planning the analysis…"}
    plan, frame, error = None, None, None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            plan = llm.send_json(planner, prompt)
        except Exception as e:
            yield {"type": "error", "message": f"The model did not return a valid plan: {e}"}
            return
        plan.setdefault("assumptions", [])
        plan["approach"] = str(plan.get("approach", "sql")).lower()
        if attempt == 1:
            yield {"type": "plan", **{k: plan.get(k) for k in ("intent", "approach", "code", "chart", "assumptions", "needs_clarification", "clarification")}}
        if plan.get("needs_clarification"):
            yield {"type": "clarification", "message": plan.get("clarification") or "Could you clarify your question?", "intent": plan.get("intent")}
            return
        yield {"type": "status", "message": f"Executing {'SQL' if plan['approach'] == 'sql' else 'Python'} analysis… (attempt {attempt})"}
        try:
            code = plan.get("code") or ""
            raw = run_sql(df, code) if plan["approach"] == "sql" else run_python(df, code)
            frame = to_frame(raw)
            check("guardrails", True, "code passed static validation")
            check("execution", True, f"{plan['approach']} executed successfully")
            if frame.empty:
                raise GuardrailError("The query returned no rows")
            check("non_empty", True, f"{len(frame)} row(s)")
            error = None
            break
        except GuardrailError as e:
            error = str(e)
            check("attempt_%d" % attempt, False, error)
            # Guardrail violations should still get one shot at correction
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:400]}"
            check("attempt_%d" % attempt, False, error)
        yield {"type": "retry", "attempt": attempt, "error": error}
        prompt = (f"The previous {plan['approach']} code failed with this error:\n{error}\n\n"
                  "Fix it and reply again with ONLY the complete JSON plan (same schema). Use only existing columns.")

    if frame is None or error:
        yield {"type": "error", "message": f"Analysis failed after {MAX_ATTEMPTS} attempts: {error}", "checks": checks, "plan": plan}
        return

    chart, note = _chart_type_check(plan.get("chart"), frame, dataset["columns"])
    check("chart", True, note or "chart spec validated")
    payload = _frame_payload(frame)
    if payload["truncated"]:
        check("size_limit", True, f"result truncated to {MAX_ROWS} rows")
    retries = sum(1 for c in checks if not c["ok"])
    validation = {"status": "warning" if (retries or note or payload["truncated"]) else "passed", "retries": retries, "checks": checks}
    yield {"type": "result", **payload, "chart": chart, "code": plan.get("code"), "approach": plan["approach"],
           "assumptions": plan.get("assumptions", []), "intent": plan.get("intent"), "validation": validation}

    yield {"type": "status", "message": "Writing explanation…"}
    preview = frame.head(40).to_csv(index=False)
    explain_prompt = (
        f"QUESTION: {question}\n\nINTENT: {plan.get('intent')}\nAPPROACH: {plan['approach']}\n"
        f"CODE:\n{plan.get('code')}\n\nASSUMPTIONS: {plan.get('assumptions')}\n"
        f"RESULT ({payload['row_count']} rows{', truncated' if payload['truncated'] else ''}; first 40 shown as CSV):\n{preview}\n\n"
        f"DATASET: {dataset['name']} ({dataset['row_count']} rows)"
    )
    explainer = llm.new_chat(model_key, EXPLAINER_SYSTEM)
    answer = ""
    try:
        for tok in llm.stream(explainer, explain_prompt):
            answer += tok
            yield {"type": "token", "content": tok}
    except Exception as e:
        answer = answer or f"_Explanation unavailable: {e}_"
    msg_id = str(uuid.uuid4())
    messages_col.insert_one({
        "_id": msg_id, "dataset_id": dataset["id"], "session_id": session_id, "question": question, "answer": answer,
        "approach": plan["approach"], "code": plan.get("code"), "chart": chart, "row_count": payload["row_count"],
        "model": model_key, "created_at": now_iso(),
    })
    yield {"type": "done", "answer": answer, "message_id": msg_id}


def generate_overview(dataset: dict, df: pd.DataFrame, model_key: str) -> dict:
    chat = llm.new_chat(model_key, OVERVIEW_SYSTEM)
    prompt = f"SCHEMA\n{schema_card(dataset)}\n\nSAMPLE ROWS (CSV)\n{sample_rows(df, 8)}"
    data = llm.send_json(chat, prompt)
    overview = {
        "briefing": data.get("briefing", ""),
        "insights": data.get("insights", [])[:6],
        "suggested_questions": data.get("suggested_questions", [])[:6],
        "model": model_key,
        "generated_at": now_iso(),
    }
    descs = {k: v for k, v in (data.get("column_descriptions") or {}).items() if isinstance(v, str)}
    datasets_col.update_one({"_id": dataset["id"]}, {"$set": {"overview": overview, "column_descriptions": descs}})
    return {**overview, "column_descriptions": descs}
