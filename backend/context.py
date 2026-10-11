import re

import pandas as pd

from db import messages_col

STOP = {"the", "a", "an", "of", "by", "for", "in", "on", "and", "or", "to", "me", "show", "what", "which", "how",
        "many", "is", "are", "with", "per", "top", "bottom", "all", "list", "give", "find", "that", "this", "from"}


def tokens(text: str) -> set[str]:
    out = set()
    for t in re.findall(r"[a-z0-9]+", str(text).lower()):
        if t in STOP or len(t) < 2:
            continue
        out.add(t[:-1] if t.endswith("s") and len(t) > 3 else t)
    return out


def _col_text(col: dict, desc: str) -> str:
    return " ".join([col["name"].replace("_", " "), desc, " ".join(map(str, col.get("sample_values", [])))])


def retrieve_columns(dataset: dict, question: str, k: int = 14) -> list[dict]:
    cols = dataset["columns"]
    if len(cols) <= k:
        return cols
    q = tokens(question)
    descs = dataset.get("column_descriptions") or {}
    scored = []
    for c in cols:
        name_t = tokens(c["name"].replace("_", " "))
        other_t = tokens(_col_text(c, descs.get(c["name"], "")))
        score = 3 * len(q & name_t) + len(q & other_t)
        if c["type"] in ("datetime", "numeric"):
            score += 0.5
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def column_line(col: dict, desc: str) -> str:
    st = col.get("stats") or {}
    bits = [f"{col['type']}"]
    if col["type"] == "numeric" and st:
        bits.append(f"min {st.get('min')}, max {st.get('max')}, mean {st.get('mean')}")
    elif col["type"] == "datetime" and st:
        bits.append(f"{str(st.get('min'))[:10]} → {str(st.get('max'))[:10]}")
    elif st.get("top_values"):
        bits.append("values: " + ", ".join(list(st["top_values"])[:5]))
    elif col.get("sample_values"):
        bits.append("e.g. " + ", ".join(map(str, col["sample_values"][:3])))
    if col["nulls"]:
        bits.append(f"{col['nulls']} nulls")
    line = f'- "{col["name"]}" ({"; ".join(bits)})'
    return line + (f" — {desc}" if desc else "")


def schema_card(dataset: dict, cols: list[dict] | None = None) -> str:
    descs = dataset.get("column_descriptions") or {}
    cols = cols or dataset["columns"]
    lines = [f"Dataset: {dataset['name']} — {dataset['row_count']} rows, {dataset['col_count']} columns."]
    lines += [column_line(c, descs.get(c["name"], "")) for c in cols]
    return "\n".join(lines)


def sample_rows(df: pd.DataFrame, n: int = 5) -> str:
    return df.head(n).to_csv(index=False)


def retrieve_history(dataset_id: str, session_id: str, question: str, k: int = 3) -> list[dict]:
    docs = list(messages_col.find({"dataset_id": dataset_id, "session_id": session_id}).sort("created_at", -1).limit(20))
    if not docs:
        return []
    q = tokens(question)
    recent = docs[:2]
    rest = sorted(docs[2:], key=lambda d: -len(q & tokens(d["question"] + " " + d.get("answer", "")[:300])))
    picked = recent + [d for d in rest if len(q & tokens(d["question"])) > 0][: max(0, k - len(recent))]
    return list(reversed(picked))


def build_context(dataset: dict, df: pd.DataFrame, question: str, session_id: str) -> str:
    cols = retrieve_columns(dataset, question)
    parts = [schema_card(dataset, cols)]
    if len(cols) < len(dataset["columns"]):
        others = [c["name"] for c in dataset["columns"] if c not in cols]
        parts.append("Other available columns: " + ", ".join(f'"{c}"' for c in others))
    parts.append("Sample rows (CSV):\n" + sample_rows(df))
    history = retrieve_history(dataset["id"], session_id, question)
    if history:
        hist = "\n".join(
            f"Q: {h['question']}\nApproach: {h.get('approach')} | Code: {str(h.get('code'))[:300]}\nA (summary): {str(h.get('answer'))[:300]}"
            for h in history
        )
        parts.append("Relevant earlier conversation (use for follow-up questions):\n" + hist)
    return "\n\n".join(parts)
