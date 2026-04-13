"""
LATAMSELLERS — NexusBI Dashboard
Dark navy theme with yellow accent, DM Mono numbers, Nunito Sans text.
Matches main_dashboard_nexus.html design language.
"""
import html as html_module
import json
import secrets

import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

from i18n import t


# ─── NexusBI Palette ────────────────────────────────────────
C = {
    "yellow":  "#FFD500",
    "yellow2": "#FFE94D",
    "ydim":    "rgba(255,213,0,0.10)",
    "blue":    "#38bdf8",
    "green":   "#22d3a5",
    "emerald": "#34d399",
    "purple":  "#a78bfa",
    "amber":   "#f59e0b",
    "red":     "#ff5757",
    "bg":      "#0b0e1a",
    "bg2":     "#111526",
    "bg3":     "#181d30",
    "border":  "#1f2540",
    "text":    "#f0f2ff",
    "text2":   "#a8b2d1",
    "text3":   "#6272a4",
}

SERIES_COLORS = [C["blue"], C["emerald"], C["purple"], C["amber"], C["yellow"], C["red"]]

PROJECT_COLORS = {
    "ARTUR": C["blue"],
    "ORGANIZADORES": C["emerald"],
    "JOOM": C["purple"],
    "ESTONIA": C["amber"],
}

# ─── Shared NexusBI CSS + auto-resize JS ────────────────────
_NEXUS_FONTS = "@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap');"

_NEXUS_BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body,html{background:transparent;font-family:'Nunito Sans','Inter','Segoe UI',system-ui,sans-serif;color:#f0f2ff}

:root{
  --bg:#0b0e1a;--bg2:#111526;--bg3:#181d30;--border:#1f2540;
  --yellow:#FFD500;--yellow2:#FFE94D;--ydim:rgba(255,213,0,0.10);
  --text:#f0f2ff;--text2:#a8b2d1;--text3:#6272a4;
  --green:#22d3a5;--red:#ff5757;--amber:#f59e0b;
  --blue:#38bdf8;--purple:#a78bfa;--emerald:#34d399;
  --shadow:none;--bar-bud:#2d3560;
  --bg-card:rgba(255,255,255,0.04);--bg-card-hover:rgba(255,255,255,0.08);
  --kpi-hover-border:rgba(255,213,0,0.2);
  --tip-bg:#1f2540;--tip-fg:#f0f2ff;--tip-bd:#6272a4;
  --tip-shadow:0 4px 20px rgba(0,0,0,0.45);
  --wl-total-bg:#0d1c2e;
  --fr-btn-hov-bd:rgba(255,213,0,0.35);
  --fr-pop-row:rgba(255,255,255,0.06);
  --fr-pop-shadow:0 8px 24px rgba(0,0,0,0.45);
}

/* ── Responsive: Tablet ── */
@media (max-width: 1024px) {
    .kpi-card { min-width: 140px !important; }
    .kpi-val { font-size: 20px !important; }
    .wl-card { min-width: 100px !important; }
    .wl-bal { font-size: 16px !important; }
    .bank-card { min-width: 120px !important; }
}

/* ── Responsive: Mobile ── */
@media (max-width: 768px) {
    /* KPI — сетка из двух колонок (см. render_kpi_header); не складываем в одну колонку */
    .kpi-row { gap: 8px !important; }
    .kpi-card { min-width: unset !important; }
    .wl-row { flex-direction: column !important; gap: 8px !important; }
    .wl-card { min-width: unset !important; }
    .bank-row { flex-direction: column !important; gap: 8px !important; }
    .bank-card { min-width: unset !important; }
    .row2 { grid-template-columns: 1fr !important; }
    .row4 { grid-template-columns: 1fr !important; }
    .ex-row { flex-wrap: wrap !important; gap: 4px 8px !important; }
    .ex-proj { flex: 0 0 auto !important; }
    .ex-cat { flex: 0 0 100% !important; order: 5; }
    .ex-amt { flex: 1 !important; text-align: left !important; }
}
"""

# Дневные токены (как .day в pnl_wide_small_months.html); --text3 затемнён для WCAG AA на белом
_NEXUS_DAY_ROOT_CSS = """
body,html{color:var(--text)}
:root{
  --bg:#F4F6FA;--bg2:#FFFFFF;--bg3:#EEF1F8;--border:#DDE2EF;
  --yellow:#E6B800;--yellow2:#FFD500;--ydim:rgba(230,184,0,0.10);
  --text:#0d1033;--text2:#5a6385;--text3:#586174;
  --green:#0a9e72;--red:#e03535;--amber:#c27803;
  --blue:#0284c7;--purple:#7c3aed;--emerald:#0a9e72;
  --shadow:0 1px 4px rgba(0,0,0,0.08);--bar-bud:#dde2ef;
  --bg-card:rgba(13,16,51,0.04);--bg-card-hover:rgba(13,16,51,0.07);
  --kpi-hover-border:rgba(230,184,0,0.42);
  --tip-bg:#FFFFFF;--tip-fg:#0d1033;--tip-bd:#DDE2EF;
  --tip-shadow:0 4px 18px rgba(13,16,51,0.12);
  --wl-total-bg:#E8F4FC;
  --fr-btn-hov-bd:rgba(230,184,0,0.45);
  --fr-pop-row:rgba(13,16,51,0.06);
  --fr-pop-shadow:0 8px 24px rgba(13,16,51,0.14);
}
"""

_AUTO_RESIZE_JS = """
<script>
(function() {
    function measure() {
        var b = document.body, e = document.documentElement;
        return Math.max(
            b.scrollHeight, b.offsetHeight, e.clientHeight, e.scrollHeight, e.offsetHeight,
            0
        );
    }
    function resize() {
        var h = Math.max(measure() + 6, 120);
        window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
    }
    function schedule() {
        resize();
        requestAnimationFrame(function() {
            requestAnimationFrame(resize);
        });
        setTimeout(resize, 0);
        setTimeout(resize, 80);
        setTimeout(resize, 350);
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(resize).catch(function() { resize(); });
        }
    }
    schedule();
    window.addEventListener('load', schedule);
    if (typeof ResizeObserver !== 'undefined') {
        var ro = new ResizeObserver(resize);
        ro.observe(document.body);
        ro.observe(document.documentElement);
    }
})();
</script>
"""


def _get_theme() -> str:
    """Get current theme from session state."""
    try:
        return st.session_state.get("theme", "night")
    except Exception:
        return "night"


def plotly_theme() -> dict[str, str]:
    """Цвета Plotly/HTML вне CSS-переменных iframe — синхронно с дневной/ночной темой."""
    day = _get_theme() == "day"
    return {
        "accent": "#E6B800" if day else "#FFD500",
        "text": "#0d1033" if day else "#f0f2ff",
        "text_legend": "#5a6385" if day else "#a8b2d1",
        "text_axis": "#586174" if day else "#8892b0",
        "tick_soft": "rgba(88,97,116,0.92)" if day else "rgba(168,178,209,0.85)",
        "pie_line": "#FFFFFF" if day else "#0b0e1a",
        "donut_line": "#FFFFFF" if day else "#111526",
        "fill_accent_soft": "rgba(230,184,0,0.14)" if day else "rgba(255,213,0,0.06)",
        "grid": "rgba(13,16,51,0.10)" if day else "rgba(255,255,255,0.03)",
        "gauge_track": "rgba(13,16,51,0.06)" if day else "rgba(255,255,255,0.03)",
        "waterfall_text": "#5a6385" if day else "#8892b0",
        "waterfall_grid": "rgba(13,16,51,0.10)" if day else "rgba(255,255,255,0.025)",
        "connector": "rgba(13,16,51,0.14)" if day else "rgba(136,146,176,0.15)",
        "increase": "#0a9e72" if day else "#22d3a5",
        "decrease": "#e03535" if day else "#ff5757",
        "fifo_green": "#0a9e72" if day else "#34d399",
    }


def _render_html(html: str, fallback_h: int):
    """Wrap HTML with NexusBI theme CSS and auto-resize script, then render."""
    css = _NEXUS_FONTS + _NEXUS_BASE_CSS
    if _get_theme() == "day":
        css += _NEXUS_DAY_ROOT_CSS
    full = f"<style>{css}</style>{html}{_AUTO_RESIZE_JS}"
    components.html(full, height=fallback_h, scrolling=False)


# ─── SKU page (NexusBI, same palette as P&L / dashboard) ───────

def sku_page_css() -> str:
    """Scoped styles for iframe fragments on the SKU mapping page."""
    return """
    .sku-top { color: var(--text); }
    .sku-header h1 {
        font-size: 15px; font-weight: 800; color: var(--text); margin: 0 0 4px 0;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-header p {
        font-size: 10px; color: var(--text2); margin: 0; font-weight: 600;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-section-label {
        font-size: 9px; color: var(--text3); text-transform: uppercase;
        letter-spacing: 1px; font-weight: 700; margin: 14px 0 8px;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-map-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 10px;
    }
    .sku-map-card {
        background: var(--bg2); border: 1px solid var(--border); border-radius: 10px;
        padding: 12px 14px; position: relative; overflow: hidden; box-shadow: var(--shadow);
    }
    .sku-map-card::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
        background: var(--accent, var(--yellow2));
    }
    .sku-map-card-wide { grid-column: 1 / -1; }
    .sku-map-card-label {
        font-size: 9px; color: var(--text2); text-transform: uppercase;
        letter-spacing: 0.8px; font-weight: 700; margin-bottom: 6px;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-map-card-val {
        font-family: 'DM Mono', monospace; font-size: 11px; color: var(--yellow);
        line-height: 1.5; word-break: break-word;
    }
    .sku-map-card-meta {
        font-size: 10px; color: var(--text3); margin-bottom: 6px;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-details summary {
        cursor: pointer; font-size: 10px; color: var(--blue); margin-top: 8px;
        font-weight: 700; font-family: 'Nunito Sans', sans-serif;
    }
    .sku-map-scroll { max-height: 140px; overflow-y: auto; margin-top: 8px; }
    .sku-callout {
        display: flex; gap: 10px; align-items: flex-start;
        background: var(--bg2); border: 1px solid var(--border); border-radius: 10px;
        padding: 12px 14px; border-left: 3px solid var(--amber);
    }
    .sku-callout-ic {
        flex-shrink: 0; width: 22px; height: 22px; border-radius: 6px;
        background: rgba(245, 158, 11, 0.15); color: var(--amber);
        font-weight: 800; font-size: 12px; display: flex; align-items: center;
        justify-content: center; font-family: 'Nunito Sans', sans-serif;
    }
    .sku-callout-txt {
        font-size: 11px; color: var(--text2); line-height: 1.45;
        font-family: 'Nunito Sans', sans-serif;
    }
    .sku-callout-txt strong { color: var(--text); }
    .sku-badge {
        display: inline-flex; align-items: center; gap: 8px; padding: 10px 14px;
        border-radius: 10px; font-size: 12px; font-weight: 600;
        font-family: 'Nunito Sans', sans-serif; border: 1px solid var(--border);
        max-width: 100%; flex-wrap: wrap; word-break: break-word;
    }
    .sku-badge-ok { background: rgba(34, 211, 165, 0.12); color: var(--green); }
    .sku-badge-bad { background: rgba(255, 87, 87, 0.12); color: var(--red); }
    .sku-badge code { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--yellow); }
    """


def sku_page_streamlit_markdown() -> str:
    """Inject once on SKU page: section titles, catalog shell, dividers."""
    bg2, border, text2, text3 = C["bg2"], C["border"], C["text2"], C["text3"]
    return f"""
<style>
.sku-section-title {{
    font-size: 11px; font-weight: 800; color: {text2}; text-transform: uppercase;
    letter-spacing: 0.9px; margin: 20px 0 10px 0; padding-bottom: 6px;
    border-bottom: 1px solid {border}; font-family: 'Nunito Sans', sans-serif;
}}
.sku-hint-cap {{
    font-size: 9px; color: {text3}; text-transform: uppercase;
    letter-spacing: 0.8px; font-weight: 700; margin: 0 0 12px 0;
    font-family: 'Nunito Sans', sans-serif;
}}
.sku-divider {{
    border: none; height: 1px;
    background: linear-gradient(90deg, transparent, {border}, transparent);
    margin: 18px 0;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stDataEditor"]) {{
    background: {bg2};
    border-color: {border} !important;
    border-radius: 10px;
    padding: 6px 2px 10px;
}}
</style>
"""


def render_sku_page_top(
    title: str,
    subtitle: str,
    sku_prefixes: dict,
    fallback_ids: list,
    labels: dict,
    fallback_h: int = 320,
) -> None:
    """Header + mapping cards grid + MLB fallback card (single iframe)."""
    import html as html_module

    esc = html_module.escape
    cards = []
    for proj_id, prefixes in sku_prefixes.items():
        accent = PROJECT_COLORS.get(proj_id, C["yellow"])
        inner = ", ".join(f"`{esc(str(p))}`" for p in prefixes)
        cards.append(f"""
        <div class="sku-map-card" style="--accent:{accent}">
            <div class="sku-map-card-label">{esc(str(proj_id))}</div>
            <div class="sku-map-card-val">{inner}</div>
        </div>
        """)

    n = len(fallback_ids)
    first5 = fallback_ids[:5]
    first5_html = ", ".join(f"`{esc(str(x))}`" for x in first5) if first5 else "—"
    rest = fallback_ids[5:]
    rest_html = ", ".join(f"`{esc(str(x))}`" for x in rest) if rest else ""
    details_block = ""
    if rest:
        summ = esc(labels.get("show_all", "…"))
        details_block = (
            f'<details class="sku-details"><summary>{summ}</summary>'
            f'<div class="sku-map-card-val sku-map-scroll">{rest_html}</div></details>'
        )

    mlb_l = esc(labels.get("mlb_fallback", "MLB"))
    total_l = esc(labels.get("total_label", ""))
    sect = esc(labels.get("section_mapping", ""))
    meta = f"{n} {total_l}" if total_l else str(n)

    cards.append(f"""
    <div class="sku-map-card sku-map-card-wide" style="--accent:{C["amber"]}">
        <div class="sku-map-card-label">{mlb_l}</div>
        <div class="sku-map-card-meta">{esc(meta)}</div>
        <div class="sku-map-card-val">{first5_html}</div>
        {details_block}
    </div>
    """)

    html = f"""
    <style>{sku_page_css()}</style>
    <div class="sku-top">
        <div class="sku-header">
            <h1>{esc(title)}</h1>
            <p>{esc(subtitle)}</p>
        </div>
        <div class="sku-section-label">{sect}</div>
        <div class="sku-map-grid">{"".join(cards)}</div>
    </div>
    """
    est_h = 100 + len(cards) * 72
    _render_html(html, fallback_h=max(fallback_h, min(est_h, 520)))


def render_sku_warn_callout(message: str, fallback_h: int = 96) -> None:
    import html as html_module

    html = f"""
    <style>{sku_page_css()}</style>
    <div class="sku-callout">
        <span class="sku-callout-ic">!</span>
        <div class="sku-callout-txt">{html_module.escape(message)}</div>
    </div>
    """
    _render_html(html, fallback_h=fallback_h)


def render_sku_test_badge(ok: bool, line: str, fallback_h: int = 56) -> None:
    import html as html_module

    cls = "sku-badge-ok" if ok else "sku-badge-bad"
    sym = "OK" if ok else "✕"
    html = f"""
    <style>{sku_page_css()}</style>
    <div class="sku-badge {cls}"><span>{sym}</span><span>{html_module.escape(line)}</span></div>
    """
    _render_html(html, fallback_h=fallback_h)


# ─── Helpers ─────────────────────────────────────────────────

def fmt_brl(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"R$ {v/1_000_000:,.2f}M"
    if abs(v) >= 1_000:
        s = f"{v:,.0f}".replace(",", ".")
        return f"R$ {s}"
    return f"R$ {v:,.0f}"

def fmt_number(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:,.1f}M"
    s = f"{v:,.0f}".replace(",", ".")
    return s


# ─── Dark Plotly layout base ────────────────────────────────

def _layout(height: int = 340, **kw) -> dict:
    pt = plotly_theme()
    if _get_theme() == "day":
        base = dict(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(
                family="'Nunito Sans','Inter',system-ui,sans-serif",
                color=pt["text_legend"],
                size=11,
            ),
            height=height,
            margin=dict(l=0, r=0, t=8, b=0),
            xaxis=dict(
                showgrid=False, zeroline=False, showline=False,
                tickfont=dict(color=pt["text_axis"], size=10),
            ),
            yaxis=dict(
                showgrid=True, gridcolor=pt["grid"], zeroline=False,
                showline=False, gridwidth=1,
                tickfont=dict(color=pt["text_axis"], size=10),
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=11, color=pt["text_legend"]),
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            ),
            hovermode="x unified",
            bargap=0.3,
        )
    else:
        base = dict(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="'Nunito Sans','Inter',system-ui,sans-serif", color="#a8b2d1", size=11),
            height=height,
            margin=dict(l=0, r=0, t=8, b=0),
            xaxis=dict(showgrid=False, zeroline=False, showline=False,
                       tickfont=dict(color="#a8b2d1", size=10)),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.03)", zeroline=False,
                       showline=False, gridwidth=1,
                       tickfont=dict(color="#a8b2d1", size=10)),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11, color="#a8b2d1"),
                        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            hovermode="x unified",
            bargap=0.3,
        )
    base.update(kw)
    return base


def _get_project_color(name: str) -> str:
    return PROJECT_COLORS.get(name, SERIES_COLORS[hash(name) % len(SERIES_COLORS)])


# ═══════════════════════════════════════════════════════════════
# KPI HEADER — NexusBI dark cards with sparkline SVGs
# ═══════════════════════════════════════════════════════════════

def _sparkline_svg(points: list[float], color: str, labels: list[str] | None = None,
                    fmt: str = "currency", width: int = 260, height: int = 82, card_id: str = "0",
                    dot_stroke: str | None = None) -> str:
    if not points or len(points) < 2:
        return ""

    if dot_stroke is None:
        dot_stroke = "#DDE2EF" if _get_theme() == "day" else "#111526"

    mn, mx = min(points), max(points)
    rng = mx - mn if mx != mn else 1
    # Запас под маркеры, обводку и невидимую зону наведения (spark-hit)
    pad_x = 16
    pad_top = 12
    pad_bot = 14
    inner_w = max(width - 2 * pad_x, 1)
    inner_h = max(height - pad_top - pad_bot, 1)

    coords = []
    n = len(points)
    for i, v in enumerate(points):
        x = pad_x + (i / (n - 1)) * inner_w
        y = pad_top + inner_h - ((v - mn) / rng) * inner_h
        coords.append((x, y))

    path_d = f"M {coords[0][0]:.1f},{coords[0][1]:.1f}"
    for i in range(1, len(coords)):
        x0, y0 = coords[i - 1]
        x1, y1 = coords[i]
        cx = (x0 + x1) / 2
        path_d += f" C {cx:.1f},{y0:.1f} {cx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"

    area_d = path_d + f" L {width},{height} L 0,{height} Z"
    uid = f"g{card_id}_{abs(hash(color)) % 99999}"

    dots_html = ""
    dot_r = 4.0
    hit_r = 16
    for i, (x, y) in enumerate(coords):
        lbl = labels[i] if labels and i < len(labels) else f"#{i+1}"
        if fmt == "currency":
            val_str = f"R$ {points[i]:,.0f}".replace(",", ".")
        elif fmt == "pct":
            val_str = f"{points[i]:.0f}%"
        else:
            val_str = f"{points[i]:,.0f}".replace(",", ".")
        tip_raw = f"{lbl}: {val_str}"
        tip_esc = html_module.escape(tip_raw, quote=True)
        dots_html += f"""
        <g class="spark-point">
        <circle class="spark-hit" cx="{x:.1f}" cy="{y:.1f}" r="{hit_r}"
                fill="transparent" data-tip="{tip_esc}" />
        <circle class="spark-dot" cx="{x:.1f}" cy="{y:.1f}" r="{dot_r}"
                fill="{color}" stroke="{dot_stroke}" stroke-width="1.75"
                pointer-events="none" />
        </g>"""

    return f"""
    <svg class="spark-svg" width="100%" height="{height}" viewBox="0 0 {width} {height}"
         preserveAspectRatio="xMidYMid meet" overflow="visible"
         style="display:block;max-width:100%;min-height:{height}px;" data-uid="{uid}">
        <defs>
            <linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="{color}" stop-opacity="0.25"/>
                <stop offset="100%" stop-color="{color}" stop-opacity="0.01"/>
            </linearGradient>
        </defs>
        <path d="{area_d}" fill="url(#{uid})" />
        <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.25"
              stroke-linecap="round" stroke-linejoin="round"/>
        {dots_html}
    </svg>"""


def render_kpi_header(cards: list[dict], height: int = 200):
    """Render NexusBI-style KPI cards with sparklines.

    cards: list of {label, value, sub, color, sparkline, months, fmt}
    """
    day = _get_theme() == "day"
    y = "#E6B800" if day else "#FFD500"
    color_hex = {
        "yellow": y, "blue": "#38bdf8", "purple": "#a78bfa",
        "pink": "#ec4899", "green": "#22d3a5", "amber": "#f59e0b",
        "orange": "#f59e0b",
    }

    card_htmls = []
    for idx, card in enumerate(cards):
        col = color_hex.get(card.get("color", "yellow"), y)
        spark_data = card.get("sparkline", [])
        spark_labels = card.get("months", [])
        spark_fmt = card.get("fmt", "currency")
        svg = _sparkline_svg(spark_data, col, labels=spark_labels,
                             fmt=spark_fmt, card_id=str(idx))

        sub = card.get("sub", "")
        sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""

        card_htmls.append(f"""
        <div class="kpi-card">
            <div class="kpi-bar" style="background:{col}"></div>
            <div class="kpi-body">
                <div class="kpi-lbl">{card['label']}</div>
                <div class="kpi-val" style="color:{col}">{card['value']}</div>
                {sub_html}
            </div>
            <div class="kpi-spark">{svg}</div>
        </div>""")

    html = f"""
    <div class="kpi-row">{''.join(card_htmls)}</div>
    <div id="spark-tooltip" class="spark-tip"></div>
    <style>
        .kpi-row {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            width: 100%;
            min-height: 1px;
            align-items: stretch;
            margin-bottom: 0;
        }}
        .kpi-card {{
            min-width: 0;
            max-width: 100%;
            min-height: 128px;
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(100px, 42%);
            grid-template-rows: auto 1fr;
            grid-template-areas:
                "kbar kbar"
                "kbody kspark";
            position: relative;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: var(--kpi-hover-border);
        }}
        .kpi-bar {{
            grid-area: kbar;
            height: 3px;
            width: 100%;
        }}
        .kpi-body {{
            grid-area: kbody;
            align-self: center;
            padding: 12px 8px 12px 14px;
            min-width: 0;
        }}
        .kpi-lbl {{
            font-size: 9px; font-weight: 700; text-transform: uppercase;
            letter-spacing: 1px; color: var(--text2); margin-bottom: 4px;
            background: transparent;
            user-select: none;
            -webkit-user-select: none;
        }}
        .kpi-val {{
            font-size: 22px; font-weight: 800;
            font-family: 'DM Mono', monospace;
            line-height: 1; margin-bottom: 4px;
            word-break: break-word;
        }}
        .kpi-sub {{
            font-size: 10px; color: var(--text2);
            line-height: 1.35;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        .kpi-sub span {{ font-weight: 700; }}
        .kpi-spark {{
            grid-area: kspark;
            align-self: stretch;
            display: flex;
            align-items: flex-end;
            justify-content: stretch;
            line-height: 0;
            padding: 6px 12px 10px 4px;
            min-width: 0;
            min-height: 0;
        }}
        .kpi-spark .spark-svg {{
            width: 100%;
            max-width: 100%;
        }}

        @media (max-width: 420px) {{
            .kpi-row {{ grid-template-columns: 1fr; }}
            .kpi-card {{
                grid-template-columns: 1fr;
                grid-template-rows: auto auto auto;
                grid-template-areas:
                    "kbar"
                    "kbody"
                    "kspark";
            }}
            .kpi-body {{ padding: 10px 14px 4px; }}
            .kpi-spark {{
                justify-content: center;
                padding: 4px 10px 12px;
                max-height: 92px;
            }}
        }}

        .spark-hit {{ cursor: pointer; }}
        .spark-dot {{
            opacity: 0;
            transition: opacity 0.15s ease;
        }}
        .kpi-card:hover .spark-dot {{ opacity: 0.55; }}
        .spark-hit:hover + .spark-dot {{ opacity: 1 !important; }}

        .spark-tip {{
            position: fixed;
            left: 0;
            top: 0;
            padding: 6px 11px;
            background: var(--tip-bg);
            border: 1px solid var(--tip-bd);
            border-radius: 6px;
            color: var(--tip-fg);
            font-size: 11px; font-weight: 600;
            font-family: 'DM Mono', monospace;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.12s ease;
            z-index: 99999;
            white-space: nowrap;
            box-shadow: var(--tip-shadow);
        }}
        .spark-tip.visible {{ opacity: 1; }}
    </style>
    <script>
        (function() {{
            var tip = document.getElementById('spark-tooltip');
            if (!tip) return;
            function placeTip(anchor) {{
                var text = anchor.getAttribute('data-tip');
                if (text) tip.textContent = text;
                tip.classList.add('visible');
                tip.style.visibility = 'hidden';
                tip.style.left = '0px';
                tip.style.top = '0px';
                var tw = tip.offsetWidth;
                var th = tip.offsetHeight;
                var rect = anchor.getBoundingClientRect();
                var gap = 10;
                var vw = window.innerWidth || document.documentElement.clientWidth;
                var vh = window.innerHeight || document.documentElement.clientHeight;
                var left = rect.left - tw - gap;
                if (left < 6) {{
                    left = rect.right + gap;
                }}
                if (left + tw > vw - 6) {{
                    left = Math.max(6, vw - tw - 6);
                }}
                var top = rect.top + (rect.height / 2) - (th / 2);
                if (top < 6) top = 6;
                if (top + th > vh - 6) top = Math.max(6, vh - th - 6);
                tip.style.left = left + 'px';
                tip.style.top = top + 'px';
                tip.style.visibility = 'visible';
            }}
            document.querySelectorAll('.spark-hit').forEach(function(hit) {{
                hit.addEventListener('mouseenter', function() {{
                    placeTip(hit);
                }});
                hit.addEventListener('mousemove', function() {{
                    placeTip(hit);
                }});
                hit.addEventListener('mouseleave', function() {{
                    tip.classList.remove('visible');
                    tip.style.visibility = '';
                }});
            }});
        }})();
    </script>"""
    _render_html(html, fallback_h=height)


# ═══════════════════════════════════════════════════════════════
# SECTION HEADER — NexusBI style with line
# ═══════════════════════════════════════════════════════════════

def section_header(text: str):
    day = _get_theme() == "day"
    accent = "#E6B800" if day else "#FFD500"
    line = "#DDE2EF" if day else "#1f2540"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:0 0 6px">'
        f'<span style="font-size:10px;color:{accent};text-transform:uppercase;letter-spacing:1.2px;'
        f'font-weight:800;white-space:nowrap">{text}</span>'
        f'<span style="flex:1;height:1px;background:{line}"></span></div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════
# BANNERS — NexusBI alert banners
# ═══════════════════════════════════════════════════════════════

def render_banners(banners: list[dict], height: int = 0):
    """Render NexusBI-style alert banners.

    banners: [{type: 'red'|'yellow', icon, text}]
    """
    if not banners:
        return

    day = _get_theme() == "day"
    banners_html = ""
    for b in banners:
        btype = b.get("type", "yellow")
        if btype == "red":
            if day:
                bg = "rgba(224,53,53,0.10)"
                border = "rgba(185,28,28,0.35)"
                color = "#991b1b"
            else:
                bg = "rgba(255,87,87,0.12)"
                border = "rgba(255,87,87,0.3)"
                color = "#ff9999"
        else:
            if day:
                bg = "rgba(245,158,11,0.12)"
                border = "rgba(217,119,6,0.4)"
                color = "#9a3412"
            else:
                bg = "rgba(245,158,11,0.1)"
                border = "rgba(245,158,11,0.3)"
                color = "#fbbf24"

        icon = b.get("icon", "")
        text = b.get("text", "")

        banners_html += f"""
        <div class="banner" style="background:{bg};border:1px solid {border};color:{color}">
            <span class="banner-icon">{icon}</span>
            <span class="banner-text">{text}</span>
        </div>"""

    html = f"""
    <div class="banners">{banners_html}</div>
    <style>
        .banners {{ display:flex; flex-direction:column; gap:6px; }}
        .banner {{
            border-radius:8px; padding:9px 14px;
            display:flex; align-items:center; gap:10px;
            font-size:11px; font-weight:600;
        }}
        .banner-icon {{ font-size:14px; flex-shrink:0; }}
        .banner-text {{ flex:1; line-height:1.4; }}
    </style>"""
    auto_h = len(banners) * 48 + 8
    _render_html(html, fallback_h=height or auto_h)


# ═══════════════════════════════════════════════════════════════
# REVENUE CHARTS — Plotly with NexusBI dark theme
# ═══════════════════════════════════════════════════════════════

def chart_project_breakdown(projects: dict[str, float], title: str = ""):
    """Horizontal bar: project -> NET revenue."""
    pt = plotly_theme()
    items = sorted(projects.items(), key=lambda x: x[1])
    names = [i[0] for i in items]
    vals = [i[1] for i in items]
    colors = [_get_project_color(n) for n in names]

    fig = go.Figure(go.Bar(
        y=names, x=vals, orientation="h",
        marker=dict(color=colors, cornerradius=4, line=dict(width=0)),
        text=[fmt_brl(v) for v in vals],
        textposition="inside",
        textfont=dict(color="#ffffff", size=12, family="DM Mono,monospace"),
        insidetextanchor="end",
        hovertemplate="%{y}: R$ %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_layout(height=max(140, len(names) * 48 + 30),
                                yaxis=dict(showgrid=False, tickfont=dict(color=pt["text"], size=11, family="Nunito Sans")),
                                xaxis=dict(showgrid=False, showticklabels=False)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def chart_monthly_trend(months: list[str], series: dict[str, list[float]],
                        chart_type: str = "area", title: str = ""):
    """Multi-series area or bar chart with NexusBI theme."""
    if not months:
        return

    pt = plotly_theme()
    fig = go.Figure()

    for i, (name, vals) in enumerate(series.items()):
        color = _get_project_color(name)
        if chart_type == "area":
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            fig.add_trace(go.Scatter(
                x=months, y=vals, name=name,
                fill="tozeroy",
                fillcolor=f"rgba({r},{g},{b},0.10)",
                line=dict(color=color, width=2.5, shape="spline"),
                mode="lines+markers",
                marker=dict(size=6, color=color, line=dict(color=pt["donut_line"], width=2)),
                hovertemplate=f"{name}: R$ %{{y:,.0f}}<extra></extra>",
            ))
        else:
            fig.add_trace(go.Bar(
                x=months, y=vals, name=name,
                marker=dict(color=color, cornerradius=3, opacity=0.85),
                hovertemplate=f"{name}: R$ %{{y:,.0f}}<extra></extra>",
            ))

    layout_kw = dict(barmode="group") if chart_type == "bar" else {}
    fig.update_layout(**_layout(height=300,
                                xaxis=dict(type="category", showgrid=False,
                                           tickfont=dict(color=pt["tick_soft"], size=10)),
                                yaxis=dict(tickformat=",.0f",
                                           tickfont=dict(color=pt["tick_soft"], size=9)),
                                legend=dict(font=dict(color=pt["text_legend"], size=10)),
                                **layout_kw))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def chart_donut(labels: list[str], values: list[float], center_text: str = "", title: str = ""):
    """Donut chart with NexusBI theme."""
    pt = plotly_theme()
    pairs = [(l, v) for l, v in zip(labels, values) if v > 0]
    if not pairs:
        return
    labs, vals = zip(*pairs)
    n = len(labs)
    colors = [_get_project_color(l) for l in labs]

    fig = go.Figure(go.Pie(
        labels=labs, values=vals, hole=0.65,
        marker=dict(colors=colors, line=dict(color=pt["donut_line"], width=2)),
        textinfo="percent",
        textfont=dict(size=11, color=pt["text"]),
        hovertemplate="%{label}<br>R$ %{value:,.0f}<br>%{percent}<extra></extra>",
        sort=True, direction="clockwise",
    ))
    if center_text:
        fig.add_annotation(text=center_text, font=dict(size=20, color=pt["accent"], family="DM Mono"),
                           showarrow=False, x=0.5, y=0.5)

    fig.update_layout(**_layout(height=280, showlegend=True,
                                legend=dict(orientation="v", yanchor="middle", y=0.5,
                                            xanchor="left", x=1.02, font=dict(size=11, color=pt["text_legend"])),
                                margin=dict(l=10, r=100, t=10, b=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def chart_sales_bars(months: list[str], counts: list[int]):
    """Bar chart for sales volume with NexusBI theme."""
    if not months:
        return
    max_c = max(counts) if counts else 1
    colors = [f"rgba(56,189,248,{0.35 + 0.65*(c/max_c)})" for c in counts] if max_c > 0 else [C["blue"]]

    pt = plotly_theme()
    fig = go.Figure(go.Bar(
        x=months, y=counts,
        marker=dict(color=colors, cornerradius=4, line=dict(width=0)),
        text=[str(c) for c in counts],
        textposition="outside",
        textfont=dict(color=pt["text_legend"], size=11, family="DM Mono"),
        hovertemplate="%{x}: %{y} vendas<extra></extra>",
    ))
    fig.update_layout(**_layout(height=260,
                                xaxis=dict(type="category", showgrid=False),
                                yaxis=dict(showgrid=False, showticklabels=False)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════
# MARGIN GAUGE
# ═══════════════════════════════════════════════════════════════

def chart_margin_gauge(pct: float):
    """Radial gauge for margin %."""
    pt = plotly_theme()
    color = C["green"] if pct >= 30 else (C["amber"] if pct >= 15 else C["red"])
    if _get_theme() == "day":
        color = pt["increase"] if pct >= 30 else (C["amber"] if pct >= 15 else pt["decrease"])

    fig = go.Figure(go.Pie(
        values=[pct, 100 - max(pct, 0)],
        hole=0.78,
        marker=dict(colors=[color, pt["gauge_track"]], line=dict(width=0)),
        textinfo="none", hoverinfo="skip", sort=False, direction="clockwise",
        rotation=270,
    ))
    fig.add_annotation(text=f"<b>{pct:.0f}%</b>",
                       font=dict(size=30, color=color, family="DM Mono"),
                       showarrow=False, x=0.5, y=0.5)

    fig.update_layout(**_layout(height=200, showlegend=False,
                                margin=dict(l=20, r=20, t=10, b=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════
# DATA FRESHNESS TABLE — NexusBI compact card
# ═══════════════════════════════════════════════════════════════

def render_data_freshness_table(
    sources: list[dict], height: int = 0, primary_n: int = 3, lang: str = "ru",
):
    """Render NexusBI-style data freshness card (same footprint as KPI row).

    sources: [{name, loaded, date_max (str|None), days_old (int|None)}]
    First *primary_n* rows visible; rest open via «Подробнее» / «Mais» (popover).
    """
    uid = secrets.token_hex(4)
    title = t("freshness_title", lang)
    more_lbl = t("freshness_more", lang)
    collapse_lbl = t("freshness_collapse", lang)
    more_js = json.dumps(more_lbl)
    collapse_js = json.dumps(collapse_lbl)

    def one_row(s: dict) -> str:
        if not s["loaded"]:
            dot_color = "#ff5757"
            date_str = "—"
            age_str = "—"
            age_color = "#ff5757"
        else:
            days = s.get("days_old")
            date_str = s.get("date_max", "—") or "—"
            if days is not None:
                if days <= 7:
                    dot_color = "#22d3a5"
                    age_color = "#22d3a5"
                elif days <= 30:
                    dot_color = "#f59e0b"
                    age_color = "#f59e0b"
                else:
                    dot_color = "#ff5757"
                    age_color = "#ff5757"
                age_str = f"{days}d"
            else:
                dot_color = "#22d3a5"
                age_color = "#22d3a5"
                age_str = "—"

        return f"""
        <div class="fr-row">
            <span class="fr-name">
                <span class="fr-dot" style="background:{dot_color}"></span>
                {s['name']}
            </span>
            <span class="fr-date">{date_str}</span>
            <span class="fr-age" style="color:{age_color}">{age_str}</span>
        </div>"""

    primary = sources[:primary_n]
    more = sources[primary_n:]
    primary_html = "".join(one_row(s) for s in primary)
    more_html = "".join(one_row(s) for s in more)

    more_block = ""
    foot_html = ""
    script_html = ""
    if more_html:
        more_block = f'<div class="fr-pop" id="frPop{uid}">{more_html}</div>'
        foot_html = (
            f'<div class="fr-foot">'
            f'<button type="button" class="fr-btn" id="frBtn{uid}" '
            f'aria-expanded="false" aria-controls="frPop{uid}">{more_lbl}</button>'
            f"</div>"
        )
        script_html = f"""
<script>
(function() {{
  const card = document.getElementById('frCard{uid}');
  const btn = document.getElementById('frBtn{uid}');
  const moreL = {more_js};
  const collapseL = {collapse_js};
  btn.addEventListener('click', function(e) {{
    e.stopPropagation();
    var o = !card.classList.contains('pop-open');
    card.classList.toggle('pop-open', o);
    btn.textContent = o ? collapseL : moreL;
    btn.setAttribute('aria-expanded', o ? 'true' : 'false');
  }});
  card.addEventListener('click', function(e) {{ e.stopPropagation(); }});
  document.addEventListener('click', function() {{
    if (!card.classList.contains('pop-open')) return;
    card.classList.remove('pop-open');
    btn.textContent = moreL;
    btn.setAttribute('aria-expanded', 'false');
  }});
}})();
</script>"""

    html = f"""
    <div class="fr-shell" id="frShell{uid}">
    <div class="fr-card" id="frCard{uid}">
        <div class="fr-bar"></div>
        <div class="fr-title">{title}</div>
        <div class="fr-body">
            <div class="fr-primary">{primary_html}</div>
            {foot_html}
        </div>
        {more_block}
    </div>
    </div>
    <style>
        .fr-shell {{
            box-sizing: border-box;
        }}
        .fr-card {{
            position: relative;
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }}
        .fr-bar {{
            height: 3px;
            width: 100%;
            background: var(--yellow);
            flex-shrink: 0;
        }}
        .fr-title {{
            font-size: 9px; color: var(--yellow);
            text-transform: uppercase; letter-spacing: 1px;
            font-weight: 800; margin: 10px 16px 6px;
            flex-shrink: 0;
        }}
        .fr-body {{
            flex: 0 1 auto;
            min-height: 0;
            display: flex;
            flex-direction: column;
            padding: 0 16px 12px;
        }}
        .fr-primary {{ flex-shrink: 0; }}
        .fr-foot {{ flex-shrink: 0; padding-top: 8px; }}
        .fr-btn {{
            width: 100%;
            background: transparent;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text2);
            font-size: 9px;
            font-weight: 700;
            padding: 5px 8px;
            cursor: pointer;
            font-family: 'Nunito Sans', sans-serif;
        }}
        .fr-btn:hover {{
            background: var(--ydim);
            border-color: var(--fr-btn-hov-bd);
            color: var(--yellow);
        }}
        .fr-pop {{
            display: none;
            position: absolute;
            left: 10px;
            right: 10px;
            bottom: 40px;
            z-index: 30;
            background: var(--bg3);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: var(--fr-pop-shadow);
            max-height: min(200px, 42vh);
            overflow-y: auto;
            padding: 6px 8px;
        }}
        .fr-card.pop-open .fr-pop {{ display: block; }}
        .fr-pop .fr-row {{ border-bottom-color: var(--fr-pop-row); }}
        .fr-pop .fr-row:last-child {{ border-bottom: none; }}
        .fr-primary .fr-row:last-child {{ border-bottom: none; }}
        .fr-row {{
            display:flex; align-items:center; justify-content:space-between;
            padding:4px 0; border-bottom:1px solid var(--border);
            font-size:10px; transition:background 0.1s;
        }}
        .fr-row:hover {{ background: var(--ydim); }}
        .fr-dot {{
            width:7px; height:7px; border-radius:50%;
            flex-shrink:0; margin-right:6px; display:inline-block;
        }}
        .fr-name {{
            color:var(--text2); display:flex; align-items:center; flex:1;
            font-size:10px; min-width:0;
        }}
        .fr-date {{
            font-family:'DM Mono',monospace; color:var(--text3); font-size:9px;
            margin-left:6px; flex-shrink:0;
        }}
        .fr-age {{
            font-size:9px; font-weight:700; min-width:30px; text-align:right;
            flex-shrink:0;
        }}
    </style>
    {script_html}"""
    _render_html(html, fallback_h=height or 155)


# ═══════════════════════════════════════════════════════════════
# WALLET CARDS — NexusBI project-colored
# ═══════════════════════════════════════════════════════════════

def render_wallet_cards(
    projects: list[dict], total: float,
    expected: list[dict] | None = None, height: int = 0, lang: str = "ru",
):
    """Render NexusBI-style wallet cards.

    projects: [{name, balance}]
    total: sum of balances
    """
    total_fmt = f"{total:,.0f}".replace(",", ".")
    all_projects = t("dash_wallet_all_projects", lang)

    cards_html = f"""
    <div class="wl-card wl-total">
        <div class="wl-name" style="color:var(--blue)">TOTAL</div>
        <div class="wl-bal" style="color:var(--blue)">R$ {total_fmt}</div>
        <div class="wl-sub">{all_projects}</div>
    </div>"""

    for p in projects:
        bal = p["balance"]
        name = p["name"]
        color = _get_project_color(name)
        bal_fmt = f"{bal:,.0f}".replace(",", ".")

        cards_html += f"""
        <div class="wl-card" style="border-color:{color}40">
            <div class="wl-name" style="color:{color}">{name}</div>
            <div class="wl-bal" style="color:{color}">R$ {bal_fmt}</div>
        </div>"""

    html = f"""
    <div class="wl-row">{cards_html}</div>
    <style>
        .wl-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
        .wl-card {{
            flex:1; min-width:110px; padding:11px 14px;
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            transition: transform 0.15s;
        }}
        .wl-card:hover {{ transform:translateY(-2px); }}
        .wl-total {{
            border-color: rgba(56,189,248,0.4) !important;
            background: var(--wl-total-bg);
        }}
        .wl-name {{
            font-size:9px; font-weight:700; text-transform:uppercase;
            letter-spacing:.8px; margin-bottom:4px;
        }}
        .wl-bal {{
            font-size:18px; font-weight:800;
            font-family:'DM Mono',monospace; line-height:1;
        }}
        .wl-sub {{
            font-size:9px; color:var(--text2); margin-top:3px;
        }}
    </style>"""
    auto_h = 85
    _render_html(html, fallback_h=height or auto_h)


# ═══════════════════════════════════════════════════════════════
# BANK CARDS — NexusBI style
# ═══════════════════════════════════════════════════════════════

def render_bank_cards(balances: list[dict], height: int = 0):
    """Render NexusBI-style bank balance cards.

    balances: [{bank, icon, balance, date, color, currency?, fifo_brl?, fifo_rate?, net_movement?, note?}]
    """
    if not balances:
        return

    fifo_green = plotly_theme()["fifo_green"]
    cards_html = ""
    for b in balances:
        cur = b.get("currency", "BRL")
        cur_sym = "US$" if cur == "USD" else "R$"
        color = b.get("color")

        if b.get("balance") is not None:
            val = b["balance"]
            val_fmt = f"{abs(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if val < 0:
                val_str = f"\u2212{cur_sym} {val_fmt}"
            else:
                val_str = f"{cur_sym} {val_fmt}"
            sub_text = b.get("date", "")
        else:
            mv = b.get("net_movement", 0)
            sign = "+" if mv >= 0 else ""
            val_fmt = f"{abs(mv):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            val_str = f"{sign}{cur_sym} {val_fmt}"
            sub_text = f"{b.get('note', '')} ({b['date']})"

        fifo_line = ""
        if b.get("fifo_brl"):
            fbrl = f"{b['fifo_brl']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            frate = f"{b['fifo_rate']:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".") if b.get("fifo_rate") else ""
            fifo_line = (
                f'<div style="font-size:10px;color:{fifo_green};margin-top:2px">'
                f'= R$ {fbrl} <span style="font-size:8px;color:var(--text3)">(FIFO {frate})</span>'
                f'</div>'
            )

        icon = b.get("icon", "")
        val_color = f' style="color:{color}"' if color else ""

        cards_html += f"""
        <div class="bank-card">
            <div class="bank-icon">{icon}</div>
            <div class="bank-name">{b['bank']}</div>
            <div class="bank-val"{val_color}>{val_str}</div>
            {fifo_line}
            <div class="bank-sub">{sub_text}</div>
        </div>"""

    html = f"""
    <div class="bank-row">{cards_html}</div>
    <style>
        .bank-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
        .bank-card {{
            flex:1; min-width:140px; padding:10px 13px;
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 10px;
            transition: transform 0.15s;
        }}
        .bank-card:hover {{ transform:translateY(-2px); }}
        .bank-icon {{ font-size:13px; margin-bottom:4px; }}
        .bank-name {{
            font-size:9px; color:var(--text2); font-weight:700;
            text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px;
        }}
        .bank-val {{
            font-size:15px; font-weight:800;
            font-family:'DM Mono',monospace;
            color: var(--text2);
        }}
        .bank-sub {{
            font-size:8px; color:var(--text3); margin-top:2px;
        }}
    </style>"""
    has_fifo = any(b.get("fifo_brl") for b in balances)
    import math
    rows = math.ceil(len(balances) / 3)
    row_h = 105 if has_fifo else 90
    auto_h = row_h * rows + 8 * max(0, rows - 1)
    _render_html(html, fallback_h=height or auto_h)


# ═══════════════════════════════════════════════════════════════
# EXPENSES TABLE — NexusBI dark theme
# ═══════════════════════════════════════════════════════════════

def render_expenses_table(expenses: list[dict], height: int = 0):
    """Render NexusBI-style expenses table.

    expenses: [{project, category, amount, currency, next_date, note, brl_equivalent?}]
    """
    if not expenses:
        return

    rows_html = []
    for e in expenses:
        amt = e.get("amount", 0)
        cur = e.get("currency", "BRL")
        if cur == "USD":
            brl_eq = e.get("brl_equivalent", 0)
            if brl_eq > 0:
                brl_f = f"{brl_eq:,.0f}".replace(",", ".")
                amt_str = f"${amt:,.0f} <span style='font-size:9px;color:var(--text3)'>(R$ {brl_f})</span>"
            else:
                amt_str = f"${amt:,.0f}"
        else:
            amt_f = f"{amt:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            amt_str = f"R$ {amt_f}"

        dt = e.get("next_date") or "\u2014"
        note = e.get("note", "")

        row_cls = "ex-row"
        if dt != "\u2014":
            try:
                from datetime import datetime as _dt
                d = _dt.strptime(dt, "%Y-%m-%d").date()
                if d < _dt.now().date():
                    row_cls = "ex-row ex-overdue"
            except Exception:
                pass

        proj_color = _get_project_color(e.get("project", ""))

        rows_html.append(f"""
        <div class="{row_cls}">
            <div class="ex-proj" style="color:{proj_color}">{e.get('project', '')}</div>
            <div class="ex-cat">{e.get('category', '')}</div>
            <div class="ex-amt">{amt_str}</div>
            <div class="ex-date">{dt}</div>
            <div class="ex-note">{note}</div>
        </div>""")

    html = f"""
    <div class="ex-table">{''.join(rows_html)}</div>
    <style>
        .ex-table {{ display:flex; flex-direction:column; gap:1px; }}
        .ex-row {{
            display:flex; align-items:center; gap:8px; padding:7px 12px;
            background: var(--bg2);
            border-radius: 6px;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
        }}
        .ex-row:hover {{ background: var(--ydim); }}
        .ex-row:last-child {{ border-bottom: none; }}
        .ex-overdue {{ border-left: 3px solid var(--red); }}
        .ex-proj {{
            flex:0 0 100px; font-size:10px; font-weight:700;
            text-transform:uppercase; letter-spacing:.5px;
        }}
        .ex-cat {{
            flex:1; font-size:10px; color:var(--text2);
        }}
        .ex-amt {{
            flex:0 0 140px; font-size:11px; font-weight:700;
            font-family:'DM Mono',monospace;
            text-align:right; color:var(--text);
        }}
        .ex-date {{
            flex:0 0 80px; font-size:10px; color:var(--text3);
            text-align:right; font-family:'DM Mono',monospace;
        }}
        .ex-note {{
            flex:0 0 80px; font-size:9px; color:var(--text3);
            text-align:right;
        }}
    </style>"""
    auto_h = len(expenses) * 36 + 8
    _render_html(html, fallback_h=height or auto_h)


# ═══════════════════════════════════════════════════════════════
# TOP PRODUCTS — NexusBI dark table
# ═══════════════════════════════════════════════════════════════

def render_top_products(products: list[dict], max_rows: int = 10, height: int = 0):
    """Render a NexusBI-styled product ranking table."""
    if not products:
        return

    top = sorted(products, key=lambda x: x.get("net", 0) or x.get("gross", 0), reverse=True)[:max_rows]
    if not top:
        return

    max_val = max(p.get("net", 0) or p.get("gross", 0) for p in top) or 1

    rows_html = []
    for i, p in enumerate(top):
        title = (p.get("title") or p.get("sku") or "\u2014")[:45]
        sku = p.get("sku", "")[:20]
        units = p.get("units", 0)
        val = p.get("net", 0) or p.get("gross", 0)
        pct = (val / max_val) * 100 if max_val else 0
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        rank = i + 1

        rows_html.append(f"""
        <div class="prod-row">
            <div class="prod-rank" style="color:{color}">{rank}</div>
            <div class="prod-info">
                <div class="prod-title">{title}</div>
                <div class="prod-sku">{sku} &middot; {units} un</div>
            </div>
            <div class="prod-bar-wrap">
                <div class="prod-bar" style="width:{pct:.0f}%;background:linear-gradient(90deg,{color}22,{color}88)"></div>
            </div>
            <div class="prod-val">R$ {val:,.0f}</div>
        </div>""")

    html = f"""
    <div class="prod-table">{''.join(rows_html)}</div>
    <style>
        .prod-table {{ display:flex; flex-direction:column; gap:2px; }}
        .prod-row {{
            display:flex; align-items:center; gap:10px; padding:8px 12px;
            background:var(--bg2); border-radius:6px;
            transition:background 0.15s;
        }}
        .prod-row:hover {{ background:var(--ydim); }}
        .prod-rank {{ font-size:14px; font-weight:800; min-width:22px; text-align:center; font-family:'DM Mono',monospace; }}
        .prod-info {{ flex:0 0 200px; overflow:hidden; }}
        .prod-title {{ font-size:11px; color:var(--text); font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .prod-sku {{ font-size:9px; color:var(--text3); margin-top:2px; }}
        .prod-bar-wrap {{ flex:1; height:5px; background:var(--bg3); border-radius:3px; overflow:hidden; }}
        .prod-bar {{ height:100%; border-radius:3px; transition:width 0.3s ease; }}
        .prod-val {{ font-size:12px; font-weight:700; color:var(--text2); min-width:80px; text-align:right; font-family:'DM Mono',monospace; }}
    </style>"""
    row_h = 40
    auto_h = len(top) * row_h + 12
    _render_html(html, fallback_h=height or auto_h)
