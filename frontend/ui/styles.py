import streamlit as st

COLORS = {
    "base": "#0B0F17", "surface": "#131B2A", "raised": "#1E293B", "border": "#1E293B", "border_bold": "#334155",
    "text": "#F8FAFC", "muted": "#94A3B8", "dim": "#64748B", "accent": "#38BDF8", "accent2": "#818CF8",
    "success": "#34D399", "warning": "#FBBF24", "error": "#F87171",
}
CHART_SEQ = ["#38BDF8", "#818CF8", "#34D399", "#FBBF24", "#F472B6", "#A78BFA", "#3861FB", "#FB923C"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
html, body, [class*="st-"], .stApp, .stMarkdown, button, input, textarea { font-family: 'Plus Jakarta Sans', sans-serif; }
code, pre, [data-testid="stCodeBlock"] * { font-family: 'JetBrains Mono', monospace !important; }
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] { font-family: 'Material Symbols Rounded' !important; }
.stApp { background: #0B0F17; }
.block-container { padding-top: 2.2rem; padding-bottom: 6rem; max-width: 1180px; }
[data-testid="stSidebar"] { background: #0D131F; border-right: 1px solid #1E293B; }
[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
h1, h2, h3 { letter-spacing: -0.02em; }
[data-testid="stMetric"] { background: #131B2A; border: 1px solid #1E293B; border-radius: 10px; padding: 14px 18px; }
[data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
[data-testid="stMetricValue"] { color: #F8FAFC; font-weight: 700; }
[data-testid="stChatMessage"] { background: #0F172A; border: 1px solid rgba(56,189,248,0.18); border-radius: 14px; padding: 1rem 1.2rem; margin-bottom: 0.9rem; box-shadow: 0 6px 24px rgba(0,0,0,0.25); animation: rise .35s ease; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #1E293B; border-color: #334155; }
[data-testid="stChatInput"] { border: 1px solid #334155; border-radius: 12px; background: #131B2A; }
[data-testid="stChatInput"]:focus-within { border-color: #38BDF8; box-shadow: 0 0 0 3px rgba(56,189,248,0.18); }
.stButton > button { border-radius: 8px; border: 1px solid #334155; background: #131B2A; color: #F8FAFC; font-weight: 600; transition: border-color .2s, background-color .2s, transform .15s; }
.stButton > button:hover { border-color: #38BDF8; background: #1E293B; color: #38BDF8; transform: translateY(-1px); }
.stButton > button[kind="primary"] { background: #38BDF8; color: #0B0F17; border: none; }
.stButton > button[kind="primary"]:hover { background: #7DD3FC; color: #0B0F17; }
[data-testid="stExpander"] { border: 1px solid #1E293B; border-radius: 10px; background: #0F172A; }
[data-testid="stFileUploaderDropzone"] { background: #131B2A; border: 1px dashed #334155; border-radius: 10px; }
[data-testid="stTabs"] [data-baseweb="tab"] { font-weight: 600; }
.brand { display:flex; align-items:center; gap:.65rem; margin-bottom: .4rem; }
.brand-mark { width: 34px; height: 34px; border-radius: 9px; background: #38BDF8; display:grid; place-items:center; color:#0B0F17; font-weight:800; font-family:'JetBrains Mono',monospace; }
.brand-name { font-size: 1.25rem; font-weight: 800; letter-spacing: -0.03em; }
.brand-sub { color:#64748B; font-size:.78rem; margin-top:-2px; }
.eyebrow { color:#38BDF8; font-family:'JetBrains Mono',monospace; font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; }
.hero-title { font-size: clamp(2.2rem, 4.5vw, 3.6rem); font-weight: 800; line-height: 1.05; letter-spacing:-0.035em; margin:.5rem 0 1rem; }
.hero-title span { color:#38BDF8; }
.hero-sub { color:#94A3B8; font-size:1.05rem; max-width: 640px; line-height:1.6; }
.cap-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: .9rem; margin: 1.6rem 0 .5rem; }
.cap { background:#131B2A; border:1px solid #1E293B; border-radius: 12px; padding: 1.1rem 1.2rem; animation: rise .5s ease both; }
.cap:nth-child(2){animation-delay:.08s}.cap:nth-child(3){animation-delay:.16s}.cap:nth-child(4){animation-delay:.24s}
.cap b { display:block; color:#F8FAFC; margin-bottom:.3rem; }
.cap span { color:#94A3B8; font-size:.88rem; line-height:1.5; }
.cap .k { color:#38BDF8; font-family:'JetBrains Mono',monospace; font-size:.7rem; letter-spacing:.1em; }
.badge { display:inline-block; padding:4px 10px; border-radius:6px; font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:600; margin-right:6px; margin-bottom:6px; border:1px solid transparent; }
.badge-sql { background: rgba(56,189,248,.15); color:#38BDF8; border-color: rgba(56,189,248,.3); }
.badge-python { background: rgba(129,140,248,.15); color:#818CF8; border-color: rgba(129,140,248,.3); }
.badge-ok { background: rgba(52,211,153,.15); color:#34D399; border-color: rgba(52,211,153,.3); }
.badge-warn { background: rgba(251,191,36,.15); color:#FBBF24; border-color: rgba(251,191,36,.3); }
.badge-err { background: rgba(248,113,113,.15); color:#F87171; border-color: rgba(248,113,113,.3); }
.badge-dim { background: #1E293B; color:#94A3B8; border-color:#334155; }
.status-line { color:#94A3B8; font-size:.88rem; display:flex; align-items:center; gap:.5rem; }
.status-line::before { content:""; width:8px; height:8px; border-radius:50%; background:#38BDF8; animation: pulse 1.1s infinite; }
@keyframes pulse { 0%,100%{opacity:.25; transform:scale(.8)} 50%{opacity:1; transform:scale(1)} }
@keyframes rise { from { opacity:0; transform: translateY(8px);} to { opacity:1; transform:none;} }
.ds-card { background:#131B2A; border:1px solid #1E293B; border-radius: 10px; padding: .85rem 1rem; }
.ds-card .n { font-weight:700; }
.ds-card .m { color:#64748B; font-size:.78rem; font-family:'JetBrains Mono',monospace; }
.insight { border-left: 2px solid #38BDF8; padding: .25rem .8rem; margin: .45rem 0; color:#CBD5E1; font-size:.93rem; }
.section-title { font-size:.78rem; color:#64748B; text-transform:uppercase; letter-spacing:.12em; font-family:'JetBrains Mono',monospace; margin: 1.2rem 0 .5rem; }
.intent { color:#94A3B8; font-size:.85rem; font-style: italic; margin-bottom:.4rem; }
.assume { color:#94A3B8; font-size:.82rem; }
::selection { background: rgba(56,189,248,.35); }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def badge(text: str, kind: str = "dim", testid: str = "") -> str:
    tid = f' data-testid="{testid}"' if testid else ""
    return f'<span class="badge badge-{kind}"{tid}>{text}</span>'
