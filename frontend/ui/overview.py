import pandas as pd
import streamlit as st

from ui import api
from ui.api import ApiError


def render(ds: dict):
    st.markdown('<div class="eyebrow">Active dataset</div>', unsafe_allow_html=True)
    st.markdown(f"## {ds['name']}")
    numeric = sum(1 for c in ds["columns"] if c["type"] == "numeric")
    dates = sum(1 for c in ds["columns"] if c["type"] == "datetime")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{ds['row_count']:,}")
    c2.metric("Columns", ds["col_count"])
    c3.metric("Numeric / Date", f"{numeric} / {dates}")
    c4.metric("Size", f"{ds['memory_mb']} MB")

    with st.expander("Schema & profile", expanded=False):
        descs = st.session_state.get("overview", {}) or {}
        descs = descs.get("column_descriptions") or ds.get("column_descriptions") or {}
        rows = [{
            "column": c["name"], "type": c["type"], "unique": c["unique"], "nulls": c["nulls"],
            "range / top values": _range(c), "meaning": descs.get(c["name"], ""),
        } for c in ds["columns"]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(420, 38 * len(rows) + 40))
        st.caption("First rows")
        st.dataframe(pd.DataFrame(ds["preview"]), use_container_width=True, hide_index=True)

    if st.session_state.get("overview") is None:
        try:
            with st.spinner("Reading your dataset and preparing a briefing…"):
                st.session_state.overview = api.post(f"/datasets/{ds['id']}/overview", {"model": st.session_state.model})
        except ApiError as e:
            st.session_state.overview = {"error": str(e)}
    ov = st.session_state.overview
    if ov.get("error"):
        st.warning(f"Briefing unavailable: {ov['error']}")
        return
    st.markdown('<div class="section-title">Dataset briefing</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f'<div data-testid="dataset-briefing">{ov.get("briefing", "")}</div>', unsafe_allow_html=True)
        for i, ins in enumerate(ov.get("insights", [])):
            st.markdown(f'<div class="insight" data-testid="auto-insight-{i}">{ins}</div>', unsafe_allow_html=True)
    qs = ov.get("suggested_questions", [])
    if qs:
        st.markdown('<div class="section-title">Suggested questions</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, q in enumerate(qs):
            if cols[i % 2].button(q, key=f"suggested-q-{i}", use_container_width=True):
                st.session_state.pending_question = q
                st.rerun()


def _range(c: dict) -> str:
    s = c.get("stats") or {}
    if c["type"] == "numeric" and s:
        return f"{s.get('min')} → {s.get('max')} (mean {s.get('mean')})"
    if c["type"] == "datetime" and s:
        return f"{str(s.get('min'))[:10]} → {str(s.get('max'))[:10]}"
    if s.get("top_values"):
        return ", ".join(list(s["top_values"])[:4])
    return ", ".join(map(str, c.get("sample_values", [])[:3]))
