import pandas as pd
import streamlit as st

from ui import api
from ui.api import ApiError
from ui.charts import build_figure
from ui.styles import badge


def _badges(result: dict | None, error: str | None = None) -> str:
    if error:
        return badge("FAILED", "err", "guardrail-status-badge")
    if not result:
        return ""
    v = result.get("validation", {})
    status = v.get("status", "passed")
    parts = [badge(result["approach"].upper(), result["approach"], "approach-badge")]
    parts.append(badge("VALIDATED" if status == "passed" else "VALIDATED · WITH NOTES", "ok" if status == "passed" else "warn", "guardrail-status-badge"))
    parts.append(badge(f"{result['row_count']} ROWS" + (" (TRUNCATED)" if result.get("truncated") else ""), "dim", "row-count-badge"))
    if v.get("retries"):
        parts.append(badge(f"{v['retries']} SELF-CORRECTION{'S' if v['retries'] > 1 else ''}", "warn", "retries-badge"))
    return "".join(parts)


def _render_result(result: dict):
    if result.get("intent"):
        st.markdown(f'<div class="intent" data-testid="plan-intent">{result["intent"]}</div>', unsafe_allow_html=True)
    fig = build_figure(result.get("rows", []), result.get("chart"))
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    rows = result.get("rows", [])
    if rows:
        with st.expander(f"Result table · {result['row_count']} rows", expanded=fig is None and len(rows) <= 15):
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander(f"How it was computed · {result['approach'].upper()} code & validation", expanded=False):
        st.code(result.get("code", ""), language="sql" if result["approach"] == "sql" else "python")
        if result.get("assumptions"):
            st.markdown('<div class="assume"><b>Assumptions</b></div>', unsafe_allow_html=True)
            for a in result["assumptions"]:
                st.markdown(f'<div class="assume">• {a}</div>', unsafe_allow_html=True)
        checks = result.get("validation", {}).get("checks", [])
        if checks:
            st.markdown('<div class="assume"><b>Validation checks</b></div>', unsafe_allow_html=True)
            for c in checks:
                mark = "✓" if c["ok"] else "✗"
                st.markdown(f'<div class="assume">{mark} {c["name"]} — {c["detail"]}</div>', unsafe_allow_html=True)


def render_history():
    for i, m in enumerate(st.session_state.messages):
        if m["role"] == "user":
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(m["content"])
        else:
            with st.chat_message("assistant", avatar=":material/insights:"):
                st.markdown(_badges(m.get("result"), m.get("error")), unsafe_allow_html=True)
                if m.get("error"):
                    st.error(m["error"])
                if m.get("answer"):
                    st.markdown(m["answer"])
                if m.get("result"):
                    _render_result(m["result"])


def ask(question: str):
    ds = st.session_state.dataset
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(question)
    msg = {"role": "assistant", "result": None, "answer": "", "error": None}
    with st.chat_message("assistant", avatar=":material/insights:"):
        badges_ph = st.empty()
        status_ph = st.empty()
        answer_ph = st.empty()
        body = st.container()
        answer = ""
        try:
            events = api.ask_stream(ds["id"], {"question": question, "session_id": st.session_state.session_id, "model": st.session_state.model})
            for ev in events:
                t = ev["type"]
                if t == "status":
                    status_ph.markdown(f'<div class="status-line" data-testid="agent-status">{ev["message"]}</div>', unsafe_allow_html=True)
                elif t == "retry":
                    status_ph.markdown(f'<div class="status-line" data-testid="agent-status">Attempt {ev["attempt"]} failed — self-correcting: <code>{ev["error"][:160]}</code></div>', unsafe_allow_html=True)
                elif t == "clarification":
                    status_ph.empty()
                    answer = f"**I need a bit more detail.** {ev['message']}"
                    answer_ph.markdown(answer)
                    badges_ph.markdown(badge("CLARIFICATION", "warn", "guardrail-status-badge"), unsafe_allow_html=True)
                elif t == "result":
                    msg["result"] = ev
                    badges_ph.markdown(_badges(ev), unsafe_allow_html=True)
                    with body:
                        _render_result(ev)
                elif t == "token":
                    answer += ev["content"]
                    answer_ph.markdown(answer + " ▌")
                elif t == "done":
                    status_ph.empty()
                    answer = ev.get("answer") or answer
                    answer_ph.markdown(answer)
                elif t == "error":
                    status_ph.empty()
                    msg["error"] = ev["message"]
                    badges_ph.markdown(_badges(None, ev["message"]), unsafe_allow_html=True)
                    answer_ph.error(ev["message"])
                    if ev.get("plan") and ev["plan"].get("code"):
                        with body.expander("Last attempted code"):
                            st.code(ev["plan"]["code"], language="sql" if ev["plan"].get("approach") == "sql" else "python")
        except ApiError as e:
            status_ph.empty()
            msg["error"] = str(e)
            answer_ph.error(str(e))
        except Exception as e:
            status_ph.empty()
            msg["error"] = f"Connection problem: {e}"
            answer_ph.error(msg["error"])
        msg["answer"] = answer
    st.session_state.messages.append(msg)
