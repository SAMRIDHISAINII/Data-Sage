import uuid

import streamlit as st

from ui import chat, overview, sidebar
from ui.styles import inject_css

st.set_page_config(page_title="DataSage — AI Data Analyst", page_icon=":material/analytics:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()

for k, v in {"session_id": str(uuid.uuid4()), "dataset": None, "messages": [], "overview": None, "pending_question": None}.items():
    st.session_state.setdefault(k, v)

sidebar.render()
ds = st.session_state.dataset

if ds is None:
    st.markdown('<div class="eyebrow">AI data analysis agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">Ask your data anything.<br/><span>No SQL required.</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Upload a CSV or Excel file, pick a sample, or connect a database. Then ask questions like '
        '<i>"Show me the top 10 customers by revenue and explain the trend."</i> DataSage plans the analysis, runs validated '
        'SQL or Python, charts the result and explains it in plain language.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="cap-grid">'
        '<div class="cap"><span class="k">01 · UNDERSTAND</span><b>Dataset understanding</b><span>Automatic profiling, column semantics and a briefing with suggested questions.</span></div>'
        '<div class="cap"><span class="k">02 · PLAN</span><b>Agentic SQL / Python</b><span>Chooses the right tool, writes the code, self-corrects on errors.</span></div>'
        '<div class="cap"><span class="k">03 · GUARD</span><b>Guardrails & validation</b><span>Read-only SQL, sandboxed pandas, result checks, explicit assumptions.</span></div>'
        '<div class="cap"><span class="k">04 · EXPLAIN</span><b>Explainable results</b><span>Charts, tables, the exact code that ran and a plain-language narrative.</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-title">Start with a sample dataset</div>', unsafe_allow_html=True)
    samples = sidebar._samples()["samples"]
    cols = st.columns(len(samples))
    for col, s in zip(cols, samples):
        with col:
            if st.button(s["title"], key=f"hero-sample-{s['key']}", type="primary", use_container_width=True):
                sidebar._load(lambda k=s["key"]: sidebar.api.post(f"/datasets/samples/{k}"), s["title"])
            st.caption(s["description"])
    st.chat_input("Load a dataset first to start asking questions…", disabled=True, key="chat-input-disabled")
else:
    overview.render(ds)
    st.markdown('<div class="section-title">Conversation</div>', unsafe_allow_html=True)
    chat.render_history()
    question = st.chat_input("Ask a question about this dataset…", key="chat-input")
    pending = st.session_state.pending_question
    if pending:
        st.session_state.pending_question = None
        question = pending
    if question:
        chat.ask(question)
