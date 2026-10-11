import pandas as pd
import plotly.express as px

from ui.styles import CHART_SEQ, COLORS


def build_figure(rows: list[dict], chart: dict):
    ctype = (chart or {}).get("type", "none")
    if ctype == "none" or not rows:
        return None
    df = pd.DataFrame(rows)
    x, y, title = chart.get("x"), chart.get("y"), chart.get("title") or ""
    if x not in df.columns:
        return None
    ys = y if isinstance(y, list) else [y]
    ys = [c for c in ys if c in df.columns]
    if not ys:
        return None
    kw = dict(title=title, color_discrete_sequence=CHART_SEQ, template="plotly_dark")
    try:
        if ctype == "line":
            fig = px.line(df, x=x, y=ys, markers=True, **kw)
        elif ctype == "pie":
            fig = px.pie(df, names=x, values=ys[0], hole=0.45, **kw)
        elif ctype == "scatter":
            fig = px.scatter(df, x=x, y=ys[0], **kw)
        else:
            fig = px.bar(df, x=x, y=ys, barmode="group" if len(ys) > 1 else "relative", **kw)
            if len(df) > 6 and len(ys) == 1 and not pd.api.types.is_numeric_dtype(df[x]):
                fig.update_layout(xaxis_tickangle=-30)
    except Exception:
        return None
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"], font_color=COLORS["text"],
        font_family="Plus Jakarta Sans", margin=dict(l=20, r=20, t=50 if title else 20, b=20), height=380,
        legend=dict(orientation="h", y=-0.2, title_text=""), title_font_size=15,
    )
    if len(ys) > 1:
        fig.update_layout(yaxis_title="")
    fig.update_xaxes(gridcolor=COLORS["border"], zeroline=False)
    fig.update_yaxes(gridcolor=COLORS["border"], zeroline=False)
    return fig
