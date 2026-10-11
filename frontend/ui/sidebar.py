import streamlit as st

from ui import api
from ui.api import ApiError


@st.cache_data(ttl=600)
def _samples():
    return api.get("/datasets/samples")


@st.cache_data(ttl=3600)
def _models():
    return api.get("/models")


def set_dataset(doc: dict):
    st.session_state.dataset = doc
    st.session_state.messages = []
    st.session_state.overview = None
    st.session_state.pending_question = None
    st.rerun()


def _load(fn, label):
    try:
        with st.spinner(f"Loading {label}…"):
            set_dataset(fn())
    except ApiError as e:
        st.error(str(e))


def render():
    with st.sidebar:
        st.markdown(
            '<div class="brand" data-testid="brand"><div class="brand-mark">Σ</div><div><div class="brand-name">DataSage</div>'
            '<div class="brand-sub">Natural-language data analyst</div></div></div>',
            unsafe_allow_html=True,
        )
        models = _models()
        keys = [m["key"] for m in models["models"]]
        labels = {m["key"]: m["label"] for m in models["models"]}
        st.selectbox("Model", keys, index=keys.index(models["default"]), format_func=lambda k: labels[k], key="model")

        st.markdown('<div class="section-title">Data source</div>', unsafe_allow_html=True)
        tab_up, tab_samples, tab_sql = st.tabs(["Upload", "Samples", "SQL"])
        with tab_up:
            f = st.file_uploader("CSV or Excel", type=["csv", "xlsx", "xls"], key="uploader", label_visibility="collapsed")
            if f is not None and st.button("Analyze file", key="load-file-btn", type="primary", use_container_width=True):
                _load(lambda: api.post("/datasets/upload", files={"file": (f.name, f.getvalue())}), f.name)
        with tab_samples:
            data = _samples()
            for s in data["samples"]:
                if st.button(s["title"], key=f"sample-{s['key']}", help=s["description"], use_container_width=True):
                    _load(lambda k=s["key"]: api.post(f"/datasets/samples/{k}"), s["title"])
        with tab_sql:
            conn = st.text_input("Connection string", key="sql-conn", type="password",
                                 placeholder="postgresql://user:pass@host:5432/db")
            table = st.text_input("Table", key="sql-table", placeholder="orders")
            query = st.text_area("…or a SELECT query", key="sql-query", height=80, placeholder="SELECT * FROM orders WHERE year = 2025")
            st.caption(f"Demo: `{_samples().get('demo_sql_url', '')}` · tables `sales`, `customers`")
            if st.button("Connect & load", key="sql-connect-btn", type="primary", use_container_width=True):
                _load(lambda: api.post("/datasets/sql", {"connection_string": conn, "table": table, "query": query}), "SQL data")

        ds = st.session_state.get("dataset")
        if ds:
            st.markdown('<div class="section-title">Active dataset</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="ds-card" data-testid="active-dataset-card"><div class="n">{ds["name"]}</div>'
                f'<div class="m">{ds["row_count"]:,} rows · {ds["col_count"]} cols · {ds["source"]}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Clear conversation", key="clear-chat-btn", use_container_width=True):
                st.session_state.messages = []
                st.session_state.pending_question = None
                st.rerun()
        st.markdown('<div class="section-title">Guardrails</div>', unsafe_allow_html=True)
        st.caption("Read-only SQL · sandboxed pandas · AST validation · 30s timeout · 500-row cap · retries with self-correction")
