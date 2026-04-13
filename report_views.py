"""
Тонкий рендер для PnL/CashFlow/Balance отчётов из finance.py.
Никаких вычислений — только Streamlit-виджеты поверх готовых dataclass'ов.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from finance import BalanceReport, CashFlowReport, PnLReport
from i18n import current_lang, t
from reports import (
    add_manual_cashflow_entry,
    delete_manual_cashflow_entry,
    get_armazenagem_by_period,
    get_artur_monthly_pnl,
    get_collection_mp_by_project,
    build_monthly_pnl_matrix,
    get_collection_mp_credited_by_period,
    get_devolucoes_by_project,
    get_mp_credited_for_orders,
    get_products_by_project,
    get_publicidade_by_period,
    get_vendas_ml_by_project,
    parse_approved_artur_detailed,
)


def _tl(key: str, **kwargs) -> str:
    s = t(key, current_lang())
    return s.format(**kwargs) if kwargs else s


def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def _money_col(label: str = "R$"):
    # printf format → "R$ -1234.56" вместо accounting "(R$ 1234.56)"
    return st.column_config.NumberColumn(label, format="R$ %.2f")


def _fmt_money_signed(v: float) -> str:
    """R$ -1.234,56 (минус впереди, без скобок)."""
    if v is None:
        return ""
    sign = "-" if v < 0 else ""
    return f"R$ {sign}{abs(v):,.2f}"


# ─────────────────────────────────────────────
# P&L
# ─────────────────────────────────────────────

def _fmt_brl_paren(v: float) -> str:
    """Форматирует число как R$ с пробелами-разделителями. Минус впереди."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if abs(v) < 0.005:
        return "—"
    sign = "-" if v < 0 else ""
    s = f"{abs(v):,.0f}".replace(",", " ")
    return f"R$ {sign}{s}"


def render_monthly_pnl_matrix(project: str) -> None:
    """Помесячный P&L matrix как в Yoga Studio Business Model.
    Колонки: годовые тоталы + месяцы. Строки: статьи P&L."""
    data = build_monthly_pnl_matrix(project)
    months = data.get("months") or []
    rows = data.get("rows") or []
    if not months or not rows:
        return

    years = data.get("years") or []
    # Колонки: сначала годовые, потом месяцы
    year_cols = [f"Год {y}" for y in years]
    month_cols = months
    all_cols = year_cols + month_cols

    # Группировка месяцев по годам для расчёта годовых сумм
    months_by_year: dict = {y: [m for m in months if m.startswith(y)] for y in years}

    table_rows = []
    for r in rows:
        row_dict = {"Статья": r["label"]}
        # Годовые суммы
        for y in years:
            ms = months_by_year[y]
            if r.get("is_pct"):
                # для маржи берём avg по непустым месяцам внутри года
                vals = [r["values"].get(m, 0.0) for m in ms]
                row_dict[f"Год {y}"] = sum(vals) / len(vals) if vals else 0.0
            else:
                row_dict[f"Год {y}"] = sum(r["values"].get(m, 0.0) for m in ms)
        for m in months:
            row_dict[m] = r["values"].get(m, 0.0)
        row_dict["__section"] = r.get("section", "")
        row_dict["__is_total"] = r.get("is_total", False)
        row_dict["__is_pct"] = r.get("is_pct", False)
        row_dict["__is_count"] = r.get("is_count", False)
        row_dict["__is_info"] = r.get("is_info", False)
        table_rows.append(row_dict)

    df = pd.DataFrame(table_rows)
    meta_cols = ["__section", "__is_total", "__is_pct", "__is_count", "__is_info"]
    display_cols = ["Статья"] + all_cols
    display_df = df[display_cols].copy()

    # Форматирование значений в строки
    def _fmt_cell(val, is_pct, is_count):
        if pd.isna(val):
            return ""
        if is_pct:
            return f"{val:.1f}%"
        if is_count:
            return f"{int(val):,}".replace(",", " ") if val else "—"
        return _fmt_brl_paren(float(val))

    formatted = display_df.astype(object).copy()
    for i, row in df.iterrows():
        is_pct = row["__is_pct"]
        is_count = row["__is_count"]
        for c in all_cols:
            formatted.at[i, c] = _fmt_cell(display_df.at[i, c], is_pct, is_count)

    # Стилизация: цвета и жирность через Styler
    def _row_style(row_idx):
        meta = df.iloc[row_idx]
        styles = [""] * len(display_cols)
        if meta["__is_total"]:
            for j in range(len(styles)):
                styles[j] = "font-weight: 700; background-color: #fff5e6; border-top: 2px solid #ff8800;"
        elif meta["__is_info"]:
            for j in range(len(styles)):
                styles[j] = "color: #888; font-style: italic;"
        elif meta["__section"] == "ВЫРУЧКА" and meta["Статья"].startswith("="):
            for j in range(len(styles)):
                styles[j] = "font-weight: 600; background-color: #f0f8ff;"
        return styles

    def _cell_color(val, col_name):
        if col_name == "Статья":
            return ""
        s = str(val)
        if s.startswith("("):
            return "color: #c0392b;"  # red for negatives
        return ""

    styler = formatted.style.apply(lambda r: _row_style(r.name), axis=1)
    styler = styler.map(
        lambda v: _cell_color(v, ""), subset=all_cols,
    )
    # Закрепить первую колонку и подсветить годовые
    styler = styler.set_properties(
        subset=["Статья"],
        **{"font-weight": "500", "text-align": "left", "min-width": "260px"},
    )
    styler = styler.set_properties(
        subset=year_cols,
        **{"background-color": "#fafafa", "font-weight": "600", "border-left": "2px solid #ddd"},
    )
    styler = styler.set_properties(subset=all_cols, **{"text-align": "right"})

    st.markdown(_tl("rv_pnl_matrix_title"))
    st.caption(_tl("rv_pnl_matrix_caption", m0=months[0], m1=months[-1]))
    st.dataframe(styler, width="stretch", hide_index=True, height=min(38 * (len(formatted) + 1) + 4, 600))


# ═════════════════════════════════════════════════════════════
# NEW PNL DESIGN (pnl_wide_small_months style)
# ═════════════════════════════════════════════════════════════

def _pnl_find_row(matrix: dict, *keywords) -> dict | None:
    """Find a row in PNL matrix by keyword match in label."""
    for r in matrix.get("rows", []):
        lbl = r.get("label", "").lower()
        if any(k in lbl for k in keywords):
            return r
    return None


def _pnl_fmt(v: float, is_pct=False, is_count=False) -> str:
    """Format PNL value for HTML display."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if abs(v) < 0.005 and not is_pct:
        return "—"
    if is_pct:
        return f"{v:.1f}%"
    if is_count:
        return f"{int(v):,}".replace(",", " ")
    sign = "-" if v < 0 else ""
    s = f"{abs(v):,.0f}".replace(",", " ")
    return f"{sign}{s}"


def render_pnl_kpi_cards(matrix: dict) -> None:
    """Row 1: KPI cards styled like pnl_wide_small_months."""
    from dashboard_charts import _render_html, _get_theme, fmt_brl

    bruto_row = _pnl_find_row(matrix, "receita por produtos")
    net_row = _pnl_find_row(matrix, "выручка net")
    profit_row = _pnl_find_row(matrix, "операционная прибыль")
    margin_row = _pnl_find_row(matrix, "маржа")

    cards = []
    for label, row, is_pct in [
        (_tl("rv_kpi_gross"), bruto_row, False),
        (_tl("rv_kpi_net"), net_row, False),
        (_tl("rv_kpi_op_profit"), profit_row, False),
        (_tl("rv_kpi_margin"), margin_row, True),
    ]:
        if not row:
            continue
        total = row.get("total", 0)
        if is_pct:
            val_str = f"{total:.1f}%"
        else:
            val_str = fmt_brl(total)
        # Determine delta (last month vs prev)
        months = sorted(row.get("values", {}).keys())
        delta_html = ""
        if len(months) >= 2:
            cur = row["values"].get(months[-1], 0)
            prev = row["values"].get(months[-2], 0)
            if prev != 0:
                pct = ((cur - prev) / abs(prev)) * 100
                sign = "↑" if pct > 0 else "↓"
                cls = "c-pos" if pct > 0 else "c-neg"
                delta_html = f'<div class="kpi-sub {cls}">{sign} {abs(pct):.1f}% vs {months[-2]}</div>'

        cards.append(f"""
        <div class="kpi-c">
            <div class="kpi-label">{label}</div>
            <div class="kpi-val">{val_str}</div>
            {delta_html}
        </div>""")

    html = f"""
    <div class="kpi-group">{''.join(cards)}</div>
    <style>
        .kpi-group {{ display:flex; gap:10px; margin-bottom:12px; }}
        .kpi-c {{
            background:var(--bg2); border:1px solid var(--border);
            border-radius:10px; padding:14px 18px; flex:1;
            position:relative; overflow:hidden; box-shadow:var(--shadow);
            transition:background .3s,border .3s;
        }}
        .kpi-c::before {{
            content:''; position:absolute; top:0; left:0; right:0;
            height:3px; background:var(--yellow2);
        }}
        .kpi-label {{
            font-size:9px; color:var(--text2); text-transform:uppercase;
            letter-spacing:1px; margin-bottom:5px; font-weight:700;
        }}
        .kpi-val {{
            font-size:24px; font-weight:800;
            font-family:'DM Mono',monospace; color:var(--yellow); line-height:1;
        }}
        .kpi-sub {{
            font-size:10px; margin-top:5px; font-weight:700;
        }}
        .c-pos {{ color:var(--green) !important; }}
        .c-neg {{ color:var(--red) !important; }}
    </style>"""
    _render_html(html, fallback_h=100)


def render_pnl_charts(matrix: dict, project: str) -> None:
    """Row 2: Revenue donut + Monthly NET bars."""
    from dashboard_charts import _layout, _get_theme, plotly_theme
    import plotly.graph_objects as go

    theme = _get_theme()
    pt = plotly_theme()
    months = matrix.get("months", [])
    if not months:
        return

    # Revenue structure donut
    bruto = _pnl_find_row(matrix, "receita por produtos")
    tarifa = _pnl_find_row(matrix, "tarifa de venda")
    envios = _pnl_find_row(matrix, "envios")
    cancel = _pnl_find_row(matrix, "cancelamentos")
    net = _pnl_find_row(matrix, "выручка net")

    col1, col2 = st.columns(2)

    with col1:
        labels_d, vals_d, colors_d = [], [], []
        # Светлый текст на долях; NET в день — чуть темнее золота, чтоб белые % читались
        _net_donut = "#9a7800" if theme == "day" else pt["accent"]
        for lbl, row, clr in [
            ("NET", net, _net_donut),
            (_tl("rv_trace_tarifa_ml"), tarifa, "#b38f00"),
            (_tl("rv_trace_envios"), envios, "#5c4800"),
            (_tl("rv_trace_cancels"), cancel, "#3d2e00"),
        ]:
            if row and abs(row.get("total", 0)) > 0:
                labels_d.append(lbl)
                vals_d.append(abs(row["total"]))
                colors_d.append(clr)

        if vals_d:
            fig = go.Figure(go.Pie(
                labels=labels_d, values=vals_d, hole=0.65,
                marker=dict(colors=colors_d, line=dict(
                    color=pt["pie_line"], width=2)),
                textinfo="percent",
                textfont=dict(size=12, color="#f8fafc", family="DM Mono, monospace"),
                hovertemplate="%{label}<br>R$ %{value:,.0f}<br>%{percent}<extra></extra>",
            ))
            fig.update_layout(**_layout(height=300,
                showlegend=True,
                legend=dict(orientation="v", yanchor="middle", y=0.5,
                            xanchor="left", x=1.02,
                            font=dict(size=12, color=pt["text_legend"])),
                margin=dict(l=10, r=120, t=30, b=10),
                title=dict(text=_tl("rv_chart_rev_structure"), font=dict(size=12,
                    color=pt["accent"]), x=0, y=0.98),
            ))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col2:
        # Monthly NET vs Expenses bars
        net_vals = [net["values"].get(m, 0) for m in months] if net else []
        # Sum expenses per month
        expense_rows = [r for r in matrix.get("rows", []) if r.get("section") == "РАСХОДЫ"]
        exp_vals = []
        for m in months:
            total_exp = sum(abs(r["values"].get(m, 0)) for r in expense_rows)
            exp_vals.append(total_exp)

        if net_vals:
            fig2 = go.Figure()
            yellow = pt["accent"]
            bar_exp = "#5c6bc0" if theme == "night" else "#4f46e5"
            fig2.add_trace(go.Bar(
                x=months, y=net_vals, name="NET",
                marker=dict(color=yellow, cornerradius=4),
                hovertemplate="NET: R$ %{y:,.0f}<extra></extra>",
            ))
            _exp_lbl = _tl("chart_expenses")
            fig2.add_trace(go.Bar(
                x=months, y=exp_vals, name=_exp_lbl,
                marker=dict(color=bar_exp, cornerradius=4),
                hovertemplate=_exp_lbl + ": R$ %{y:,.0f}<extra></extra>",
            ))
            fig2.update_layout(**_layout(height=340,
                barmode="group",
                xaxis=dict(type="category", showgrid=False,
                           tickangle=-45,
                           tickfont=dict(size=10, color=pt["text_axis"])),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="center", x=0.5,
                            font=dict(size=11, color=pt["text_legend"])),
                title=dict(text=_tl("rv_chart_net_vs_exp"), font=dict(size=12,
                    color=pt["accent"]), x=0, y=0.97),
                margin=dict(l=0, r=0, t=60, b=50),
            ))
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})


def render_pnl_table_html(matrix: dict) -> None:
    """Row 3: PNL table styled like pnl_wide_small_months with collapsible sections."""
    from dashboard_charts import _render_html
    import html as html_mod

    months = matrix.get("months", [])
    rows = matrix.get("rows", [])
    if not months or not rows:
        return

    # Build header
    th_cells = f'<th style="text-align:left;width:240px">{_tl("rv_col_line_item")}</th>'
    th_cells += f'<th>{_tl("rv_col_grand_total")}</th>'
    for m in months:
        th_cells += f'<th>{m[5:]}/{m[2:4]}</th>'  # "09/25"

    # Build rows with section grouping
    current_section = None
    section_id = 0
    body_rows = []

    for r in rows:
        label = html_mod.escape(r.get("label", ""))
        total = r.get("total", 0)
        is_total = r.get("is_total", False)
        is_pct = r.get("is_pct", False)
        is_count = r.get("is_count", False)
        is_info = r.get("is_info", False)
        section = r.get("section", "")

        # Determine row class
        if is_total:
            row_class = "r-total"
        elif section != current_section and not is_info:
            row_class = "r-head"
            current_section = section
            section_id += 1
        elif is_info:
            row_class = "r-sub r-info"
        else:
            row_class = "r-sub"

        # Format total
        total_fmt = _pnl_fmt(total, is_pct, is_count)
        # Color class for total
        if is_pct or is_count:
            total_cls = ""
        elif total > 0:
            total_cls = "c-pos"
        elif total < 0:
            total_cls = "c-neg"
        else:
            total_cls = ""

        # Build cells
        cells = f'<td>{label}</td>'
        cells += f'<td class="{total_cls}">{total_fmt}</td>'
        for m in months:
            v = r.get("values", {}).get(m, 0)
            v_fmt = _pnl_fmt(v, is_pct, is_count)
            if is_pct or is_count:
                v_cls = ""
            elif v > 0:
                v_cls = "c-pos"
            elif v < 0:
                v_cls = "c-neg"
            else:
                v_cls = ""
            cells += f'<td class="{v_cls}">{v_fmt}</td>'

        # Add data-section for collapsible
        if "r-sub" in row_class:
            body_rows.append(f'<tr class="{row_class}" data-section="s{section_id}">{cells}</tr>')
        else:
            toggle = ""
            if row_class == "r-head":
                toggle = f'<span class="tog-btn" onclick="togSec(\'s{section_id}\')">▼</span>'
                # Re-build first cell with toggle
                cells = f'<td>{toggle}{label}</td>' + cells.split("</td>", 1)[1]
            body_rows.append(f'<tr class="{row_class}">{cells}</tr>')

    tbody = "\n".join(body_rows)
    n_cols = 2 + len(months)  # label + total + months

    html = f"""
    <div class="tbl-wrap">
        <table>
            <thead><tr>{th_cells}</tr></thead>
            <tbody>{tbody}</tbody>
        </table>
    </div>
    <style>
        .tbl-wrap {{
            background:var(--bg2); border:1px solid var(--border);
            border-radius:10px; overflow-x:auto; box-shadow:var(--shadow);
            transition:background .3s,border .3s;
        }}
        table {{ width:100%; border-collapse:collapse; font-size:11px; }}
        thead th {{
            background:var(--bg3); color:var(--text2); font-size:9px;
            text-transform:uppercase; letter-spacing:.8px; padding:9px 10px;
            text-align:right; border-bottom:2px solid var(--yellow);
            font-weight:700; white-space:nowrap; transition:background .3s;
            position:sticky; top:0; z-index:1;
        }}
        thead th:first-child {{ text-align:left; }}
        tr.r-head td {{
            padding:8px 10px; background:var(--bg3); border-bottom:1px solid var(--border);
            text-align:right; font-family:'DM Mono',monospace; font-weight:700;
            font-size:11px; color:var(--text); transition:background .3s;
        }}
        tr.r-head td:first-child {{
            text-align:left; font-family:'Nunito Sans',sans-serif;
            color:var(--yellow); display:flex; align-items:center; gap:6px;
        }}
        tr.r-sub td {{
            padding:6px 10px; border-bottom:1px solid var(--border);
            background:var(--bg); text-align:right; font-family:'DM Mono',monospace;
            color:var(--text2); font-size:10px; transition:background .3s;
        }}
        tr.r-sub td:first-child {{
            text-align:left; color:var(--text3);
            font-family:'Nunito Sans',sans-serif; padding-left:28px;
        }}
        tr.r-info td {{ font-style:italic; color:var(--text3) !important; }}
        tr.r-total td {{
            padding:9px 10px; background:var(--bg3);
            border-top:1px solid var(--yellow); border-bottom:1px solid var(--border);
            text-align:right; font-family:'DM Mono',monospace;
            font-size:12px; font-weight:800; color:var(--text); transition:background .3s;
        }}
        tr.r-total td:first-child {{
            text-align:left; color:var(--yellow);
            font-family:'Nunito Sans',sans-serif; font-size:11px;
        }}
        tr:hover td {{ background:var(--yellow-dim) !important; }}
        .c-pos {{ color:var(--green) !important; }}
        .c-neg {{ color:var(--red) !important; }}
        .tog-btn {{
            cursor:pointer; width:14px; height:14px;
            display:inline-flex; align-items:center; justify-content:center;
            background:var(--yellow-dim); border:1px solid rgba(230,184,0,0.3);
            border-radius:3px; font-size:8px; color:var(--yellow); flex-shrink:0;
            margin-right:6px;
        }}
    </style>
    <script>
    function togSec(id) {{
        document.querySelectorAll('[data-section="'+id+'"]').forEach(function(row) {{
            row.style.display = row.style.display === 'none' ? '' : 'none';
        }});
    }}
    </script>"""

    row_count = len(body_rows)
    _render_html(html, fallback_h=min(row_count * 38 + 60, 1200))


def render_pnl_tab(pnl: PnLReport) -> None:
    """Redesigned PNL tab with KPI cards, charts, and styled table."""
    matrix = build_monthly_pnl_matrix(pnl.project)

    if not matrix.get("months"):
        st.info(_tl("report_no_vendas_matrix"))
        return

    # Row 1: KPI Cards
    render_pnl_kpi_cards(matrix)

    # Row 2: Charts (donut + bars)
    render_pnl_charts(matrix, pnl.project)

    # Row 3: PNL Table
    render_pnl_table_html(matrix)

    # Products breakdown (keep existing)
    products = get_products_by_project(pnl.project)
    if products:
        with st.expander(f"📦 {_tl('report_products_expander', n=len(products))}", expanded=False):
            _ct = _tl("col_product_title")
            _cq = _tl("col_qty_short")
            df_p = pd.DataFrame([
                {"SKU": p["sku"],
                 _ct: (p["title"] or "")[:60],
                 _cq: p["units"],
                 "Bruto R$": p["gross"],
                 "NET R$": p["net"],
                 "MLB": p["mlb"]}
                for p in products
            ])
            st.dataframe(
                df_p, width="stretch", hide_index=True,
                column_config={
                    "Bruto R$": _money_col("Bruto R$"),
                    "NET R$": _money_col("NET R$"),
                },
            )


# ═════════════════════════════════════════════════════════════
# CASH FLOW (ДДС) — NexusBI design (dds_improved.html)
# ═════════════════════════════════════════════════════════════

def _cf_fmt(v: float) -> str:
    """Format BRL for cash flow display: R$ 24.604"""
    s = f"{abs(v):,.0f}".replace(",", ".")
    return f"R$ {s}"


def _render_cf_kpi(cf: CashFlowReport) -> None:
    """KPI cards: profit, invest, expenses, cash position."""
    from dashboard_charts import _render_html

    profit = cf.inflows_operating
    invest = cf.inflows_financing + cf.inflows_partner
    expenses = cf.outflows_operating + cf.outflows_other
    cash = cf.closing_balance

    cards = [
        (_tl("rv_cf_kpi_op"), profit, "green", "kpi-g"),
        (_tl("rv_cf_kpi_invest"), invest, "blue", "kpi-b"),
        (_tl("rv_cf_kpi_exp"), expenses, "red", "kpi-r"),
        (_tl("rv_cf_kpi_cash"), cash, "yellow", "kpi-y"),
    ]

    cards_html = ""
    for label, val, color, cls in cards:
        cards_html += f"""
        <div class="kpi {cls}">
            <div class="kpi-lbl">{label}</div>
            <div class="kpi-val" style="color:var(--{color})">{_cf_fmt(val)}</div>
        </div>"""

    html = f"""
    <div class="banner">ℹ {_tl("rv_cf_simplified_banner")}</div>
    <div class="kpi-row">{cards_html}</div>
    <style>
        .banner {{
            display:flex; align-items:center; gap:8px;
            background:rgba(56,189,248,0.05); border:1px solid rgba(56,189,248,0.12);
            border-radius:7px; padding:7px 11px; margin-bottom:12px;
            font-size:10px; color:rgba(56,189,248,0.7);
        }}
        .kpi-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:12px; }}
        .kpi {{
            background:var(--bg2,#111526); border:1px solid var(--border,#1f2540);
            border-radius:9px; padding:10px 12px; position:relative; overflow:hidden;
            min-width:0;
        }}
        .kpi::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; }}
        .kpi-g::before {{ background:var(--green,#22d3a5); }}
        .kpi-b::before {{ background:var(--blue,#38bdf8); }}
        .kpi-r::before {{ background:var(--red,#ff5757); }}
        .kpi-y::before {{ background:var(--yellow,#FFD500); }}
        .kpi-lbl {{
            font-size:8px; color:var(--text2,#8892b0); text-transform:uppercase;
            letter-spacing:.6px; font-weight:700; margin-bottom:3px;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .kpi-val {{
            font-size:15px; font-weight:800; font-family:'DM Mono',monospace; line-height:1;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        @media (min-width:600px) {{
            .kpi-val {{ font-size:18px; }}
            .kpi-lbl {{ font-size:9px; }}
        }}
    </style>"""
    _render_html(html, fallback_h=90)


def _render_cf_waterfall(cf: CashFlowReport) -> None:
    """Waterfall chart: Нач → Прибыль → USDT → Партнёр → Расх.пост → Прочие → Итого."""
    from dashboard_charts import _layout, plotly_theme
    import plotly.graph_objects as go

    pt = plotly_theme()
    steps = [
        (_tl("rv_wf_start"), cf.opening_balance, "total"),
        (_tl("rv_wf_profit"), cf.inflows_operating, "increase"),
        (_tl("rv_wf_usdt"), cf.inflows_financing, "increase"),
        (_tl("rv_wf_partner"), cf.inflows_partner, "increase"),
        (_tl("rv_wf_opex"), -cf.outflows_operating, "decrease"),
        (_tl("rv_wf_other"), -cf.outflows_other, "decrease"),
        (_tl("rv_wf_total"), cf.closing_balance, "total"),
    ]

    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps],
        y=[s[1] for s in steps],
        measure=[s[2] for s in steps],
        increasing=dict(marker=dict(color=pt["increase"])),
        decreasing=dict(marker=dict(color=pt["decrease"])),
        totals=dict(marker=dict(color=pt["accent"])),
        connector=dict(line=dict(color=pt["connector"], width=1)),
        textposition="outside",
        text=[f"{abs(s[1])/1000:.0f}k" if abs(s[1]) >= 1000 else ("" if abs(s[1]) == 0 else f"{abs(s[1]):.0f}") for s in steps],
        textfont=dict(size=8, color=pt["waterfall_text"], family="DM Mono, monospace"),
        hovertemplate="%{x}: R$ %{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(**_layout(height=240,
        xaxis=dict(type="category", showgrid=False,
                   tickfont=dict(size=9, color=pt["text_axis"])),
        yaxis=dict(showgrid=True, gridcolor=pt["waterfall_grid"],
                   tickfont=dict(size=9, color=pt["text_axis"])),
        margin=dict(l=0, r=0, t=10, b=30),
    ))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_cf_trend(cf: CashFlowReport) -> None:
    """Trend line chart: Cash position (yellow) + Expenses (red dashed) over months.
    Uses PNL matrix data for monthly breakdown, like dds_improved.html."""
    from dashboard_charts import _layout, plotly_theme
    from reports import build_monthly_pnl_matrix
    import plotly.graph_objects as go

    pt = plotly_theme()
    # Try to get monthly data from PNL matrix
    matrix = build_monthly_pnl_matrix(cf.project)
    months = matrix.get("months", [])

    if len(months) >= 2:
        # Monthly NET (cumulative cash proxy)
        net_row = None
        exp_rows = []
        for r in matrix.get("rows", []):
            lbl = r.get("label", "").lower()
            if "выручка net" in lbl:
                net_row = r
            if r.get("section") == "РАСХОДЫ":
                exp_rows.append(r)

        # Build cumulative cash and monthly expenses
        cash_vals = []
        exp_vals = []
        cumulative = 0
        for m in months:
            net_m = net_row["values"].get(m, 0) if net_row else 0
            exp_m = sum(abs(r["values"].get(m, 0)) for r in exp_rows)
            cumulative += net_m - exp_m
            cash_vals.append(cumulative)
            exp_vals.append(exp_m)

        # Shorten month labels
        labels = [f"{m[5:]}/{m[2:4]}" for m in months]
    else:
        # Fallback: single point
        labels = [_tl("rv_cf_trend_single")]
        cash_vals = [cf.closing_balance]
        exp_vals = [cf.outflows_operating + cf.outflows_other]

    fig = go.Figure()
    # Cash line (yellow, solid, with dots)
    _cash_nm = _tl("rv_cf_trend_cash")
    _exp_nm = _tl("rv_cf_trend_exp")
    fig.add_trace(go.Scatter(
        x=labels, y=cash_vals, name=_cash_nm,
        mode="lines+markers",
        line=dict(color=pt["accent"], width=2.5, shape="spline"),
        marker=dict(size=6, color=pt["accent"]),
        fill="tozeroy",
        fillcolor=pt["fill_accent_soft"],
        hovertemplate=_cash_nm + ": R$ %{y:,.0f}<extra></extra>",
    ))
    # Expenses line (red, dashed, no dots)
    fig.add_trace(go.Scatter(
        x=labels, y=exp_vals, name=_exp_nm,
        mode="lines",
        line=dict(color=pt["decrease"], width=1.5, dash="dash", shape="spline"),
        hovertemplate=_exp_nm + ": R$ %{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(**_layout(height=240,
        xaxis=dict(type="category", showgrid=False,
                   tickfont=dict(size=9, color=pt["text_axis"])),
        yaxis=dict(showgrid=True, gridcolor=pt["waterfall_grid"],
                   tickfont=dict(size=9, color=pt["text_axis"])),
        showlegend=False,
        title=dict(text=_tl("rv_cf_trend_title", n=len(labels)),
                   font=dict(size=10, color=pt["accent"]), x=0, y=0.98),
        margin=dict(l=0, r=0, t=25, b=25),
    ))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_cf_table(cf: CashFlowReport) -> None:
    """Cash Position table with colored zones and collapsible details."""
    from dashboard_charts import _render_html
    import html as html_mod

    def _detail_rows(txs, color_var, sign):
        """Build detail HTML rows from transaction list."""
        rows_h = ""
        for tx in txs:
            desc = html_mod.escape(str(tx.get("Descrição", tx.get("note", "")))[:55])
            date = str(tx.get("Data", tx.get("date", "")))[:10]
            val = float(tx.get("Valor", tx.get("valor", 0)) or 0)
            val_fmt = f"{sign}R$ {abs(val):,.0f}".replace(",", ".")
            rows_h += f"""
            <div class="cp-detail-row">
                <span class="cp-detail-desc">{desc}</span>
                <span class="cp-detail-date">{date}</span>
                <span class="cp-detail-amt" style="color:var({color_var})">{val_fmt}</span>
            </div>"""
        return rows_h

    # Build rows
    sections = []

    # Opening balance
    sections.append(f"""
    <div class="cp-row zone-neu">
        <div class="cp-cell"><div class="cp-dot" style="background:var(--text3)"></div>
            <span class="cp-name">{_tl("rv_cp_opening")}</span></div>
        <div class="cp-cell" style="color:var(--text3)">—</div>
        <div class="cp-cell" style="color:var(--text2)">{_cf_fmt(cf.opening_balance)}</div>
    </div>""")

    # (+) Operating profit
    detail_id = "d_op"
    sections.append(f"""
    <div class="cp-row zone-in" onclick="toggleD('{detail_id}')">
        <div class="cp-cell"><div class="cp-dot" style="background:var(--green)"></div>
            <span class="cp-arrow" id="{detail_id}-arr">▶</span>
            <span class="cp-name">{_tl("rv_cp_op_profit")}</span></div>
        <div class="cp-cell" style="color:var(--text2)">{cf.inflows_count}</div>
        <div class="cp-cell" style="color:var(--green);font-weight:700">+{_cf_fmt(cf.inflows_operating)}</div>
    </div>""")

    # (+) USDT
    if cf.inflows_financing > 0:
        sections.append(f"""
        <div class="cp-row zone-in">
            <div class="cp-cell"><div class="cp-dot" style="background:var(--blue)"></div>
                <span class="cp-name">{_tl("rv_cp_usdt_topup")}</span></div>
            <div class="cp-cell" style="color:var(--text3)">—</div>
            <div class="cp-cell" style="color:var(--blue);font-weight:700">+{_cf_fmt(cf.inflows_financing)}</div>
        </div>""")

    # (+) Partner
    if cf.inflows_partner > 0:
        detail_id = "d_partner"
        partner_details = _detail_rows(cf.partner_txs, "--amber", "+")
        sections.append(f"""
        <div class="cp-row zone-in" onclick="toggleD('{detail_id}')">
            <div class="cp-cell"><div class="cp-dot" style="background:var(--amber)"></div>
                <span class="cp-arrow" id="{detail_id}-arr">▶</span>
                <span class="cp-name">{_tl("rv_cp_partner_in")}</span></div>
            <div class="cp-cell" style="color:var(--text2)">{len(cf.partner_txs)}</div>
            <div class="cp-cell" style="color:var(--amber);font-weight:700">+{_cf_fmt(cf.inflows_partner)}</div>
        </div>
        <div class="cp-detail" id="{detail_id}">{partner_details}</div>""")

    # (-) Supplier expenses
    if cf.outflows_operating > 0:
        detail_id = "d_supplier"
        supplier_details = _detail_rows(cf.new_transactions, "--red", "−")
        sections.append(f"""
        <div class="cp-row zone-out" onclick="toggleD('{detail_id}')">
            <div class="cp-cell"><div class="cp-dot" style="background:var(--red)"></div>
                <span class="cp-arrow" id="{detail_id}-arr">▶</span>
                <span class="cp-name">{_tl("rv_cp_supplier_out")}</span></div>
            <div class="cp-cell" style="color:var(--text2)">{len(cf.new_transactions)}</div>
            <div class="cp-cell" style="color:var(--red);font-weight:700">−{_cf_fmt(cf.outflows_operating)}</div>
        </div>
        <div class="cp-detail" id="{detail_id}">{supplier_details}</div>""")

    # (-) Other expenses
    if cf.outflows_other > 0:
        detail_id = "d_other"
        other_details = _detail_rows(cf.other_expenses_txs, "--red", "−")
        sections.append(f"""
        <div class="cp-row zone-out" onclick="toggleD('{detail_id}')">
            <div class="cp-cell"><div class="cp-dot" style="background:var(--red)"></div>
                <span class="cp-arrow" id="{detail_id}-arr">▶</span>
                <span class="cp-name">{_tl("rv_cp_other_out")}</span></div>
            <div class="cp-cell" style="color:var(--text2)">{len(cf.other_expenses_txs)}</div>
            <div class="cp-cell" style="color:var(--red);font-weight:700">−{_cf_fmt(cf.outflows_other)}</div>
        </div>
        <div class="cp-detail" id="{detail_id}">{other_details}</div>""")

    # Total
    sections.append(f"""
    <div class="cp-row total">
        <div class="cp-cell"><div class="cp-dot" style="background:var(--yellow)"></div>
            <span class="cp-name">{_tl("rv_cp_cash_position")}</span></div>
        <div class="cp-cell" style="color:var(--text3)">—</div>
        <div class="cp-cell" style="color:var(--yellow);font-size:14px;font-weight:800">{_cf_fmt(cf.closing_balance)}</div>
    </div>""")

    body = "\n".join(sections)
    row_count = len(sections)

    _col_art = t("rv_col_line_item", current_lang())
    _col_qty = t("col_qty_short", current_lang())
    _col_brl = t("rv_cp_col_brl", current_lang())
    html = f"""
    <div class="cp-card">
        <div class="cp-thead">
            <div class="cp-thead-cell">{_col_art}</div>
            <div class="cp-thead-cell">{_col_qty}</div>
            <div class="cp-thead-cell">{_col_brl}</div>
        </div>
        {body}
    </div>
    <style>
        .cp-card {{
            background:var(--bg2,#111526); border:1px solid var(--border,#1f2540);
            border-radius:10px; overflow:hidden; margin-bottom:10px;
        }}
        .cp-thead {{
            display:grid; grid-template-columns:1fr 60px 130px;
            background:var(--bg3,#181d30); border-bottom:2px solid var(--yellow,#FFD500);
        }}
        .cp-thead-cell {{
            font-size:8px; color:var(--text3,#3d4570); text-transform:uppercase;
            letter-spacing:.8px; font-weight:700; padding:8px 12px;
        }}
        .cp-thead-cell:not(:first-child) {{ text-align:right; }}
        .cp-row {{
            display:grid; grid-template-columns:1fr 60px 130px;
            border-bottom:1px solid rgba(31,37,64,0.4); cursor:pointer; transition:background .15s;
        }}
        .cp-row:last-child {{ border-bottom:none; }}
        .cp-row.zone-in {{ background:rgba(34,211,165,0.03); }}
        .cp-row.zone-in:hover {{ background:rgba(34,211,165,0.07); }}
        .cp-row.zone-out {{ background:rgba(255,87,87,0.03); }}
        .cp-row.zone-out:hover {{ background:rgba(255,87,87,0.07); }}
        .cp-row.zone-neu:hover {{ background:var(--ydim,rgba(255,213,0,0.08)); }}
        .cp-row.total {{
            background:rgba(255,213,0,0.06); border-top:2px solid var(--yellow,#FFD500); cursor:default;
        }}
        .cp-row.total:hover {{ background:rgba(255,213,0,0.08); }}
        .cp-cell {{
            padding:9px 12px; font-size:11px; font-family:'DM Mono',monospace;
            text-align:right; display:flex; align-items:center; justify-content:flex-end;
        }}
        .cp-cell:first-child {{ text-align:left; justify-content:flex-start; gap:8px; }}
        .cp-dot {{ width:7px; height:7px; border-radius:2px; flex-shrink:0; }}
        .cp-arrow {{
            font-size:9px; color:var(--text3,#3d4570); transition:transform .2s; flex-shrink:0;
        }}
        .cp-arrow.open {{ transform:rotate(90deg); }}
        .cp-name {{ font-size:11px; color:var(--text2,#8892b0); }}
        .cp-row.total .cp-name {{ color:var(--yellow,#FFD500); font-weight:800; font-size:12px; }}
        .cp-detail {{ display:none; border-bottom:1px solid rgba(31,37,64,0.4); }}
        .cp-detail.open {{ display:block; }}
        .cp-detail-row {{
            display:grid; grid-template-columns:1fr auto auto;
            padding:6px 12px 6px 38px; border-bottom:1px solid rgba(31,37,64,0.25);
            font-size:10px; transition:.12s;
        }}
        .cp-detail-row:last-child {{ border-bottom:none; }}
        .cp-detail-row:hover {{ background:var(--ydim,rgba(255,213,0,0.08)); }}
        .cp-detail-desc {{ color:var(--text2,#8892b0); font-family:'Nunito Sans',sans-serif; }}
        .cp-detail-date {{
            font-family:'DM Mono',monospace; color:var(--text3,#3d4570);
            font-size:9px; text-align:right; padding:0 10px;
        }}
        .cp-detail-amt {{
            font-family:'DM Mono',monospace; font-size:10px; font-weight:700;
            min-width:90px; text-align:right;
        }}
    </style>"""

    # Prepend script so toggleD is available before onclick fires
    script = """
    <script>
    function toggleD(id) {
        var d = document.getElementById(id);
        var a = document.getElementById(id + '-arr');
        if (d) {
            var open = d.classList.toggle('open');
            if (a) a.classList.toggle('open', open);
        }
        // Resize iframe after toggle
        setTimeout(function() {
            var h = document.body.scrollHeight + 2;
            window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
        }, 50);
    }
    </script>"""
    html = script + html

    detail_count = len(cf.partner_txs) + len(cf.new_transactions) + len(cf.other_expenses_txs)
    _render_html(html, fallback_h=row_count * 55 + detail_count * 30 + 100)


def render_cashflow_tab(cf: CashFlowReport) -> None:
    """Redesigned ДДС tab — NexusBI style (dds_improved.html)."""

    # KPI cards
    _render_cf_kpi(cf)

    # Charts row: Waterfall + Trend (like dds_improved.html)
    col_wf, col_trend = st.columns([3, 2])
    with col_wf:
        _render_cf_waterfall(cf)
    with col_trend:
        _render_cf_trend(cf)

    # Cash Position table
    _render_cf_table(cf)

    # ── Form: добавить запись вручную (native Streamlit) ──
    with st.expander(_tl("rv_cf_add_expander"), expanded=False):
        _k_partner = _tl("rv_cf_kind_partner")
        _k_other = _tl("rv_cf_kind_other")
        _k_supplier = _tl("rv_cf_kind_supplier")
        kind_map = {
            _k_partner: "partner_contributions",
            _k_other: "manual_expenses",
            _k_supplier: "manual_supplier",
        }
        kind_label = st.radio(
            _tl("rv_cf_type"),
            list(kind_map.keys()),
            horizontal=True,
            key=f"cf_add_kind_{cf.project}",
        )
        kind = kind_map[kind_label]

        with st.form(key=f"cf_add_form_{cf.project}", clear_on_submit=True):
            col_d, col_v = st.columns(2)
            from datetime import date as _d
            d_val = col_d.date_input(_tl("rv_cf_date"), _d.today(), key=f"cf_add_date_{cf.project}")
            v_val = col_v.number_input(_tl("rv_cf_amount"), min_value=0.0, step=100.0, format="%.2f",
                                       key=f"cf_add_val_{cf.project}")
            note = st.text_input(_tl("rv_cf_note"), key=f"cf_add_note_{cf.project}")
            extra_field = ""
            if kind == "partner_contributions":
                extra_field = st.text_input(_tl("rv_cf_from"), key=f"cf_add_from_{cf.project}")
            elif kind == "manual_expenses":
                extra_field = st.text_input(_tl("rv_cf_category"), value="expense", key=f"cf_add_cat_{cf.project}")
            elif kind == "manual_supplier":
                extra_field = st.text_input(_tl("rv_cf_source"),
                                            key=f"cf_add_src_{cf.project}")

            if st.form_submit_button(_tl("rv_cf_save")):
                if v_val > 0:
                    entry = {
                        "date": d_val.strftime("%Y-%m-%d"),
                        "valor": float(v_val),
                        "note": note,
                    }
                    if kind == "partner_contributions":
                        entry["from"] = extra_field
                    elif kind == "manual_expenses":
                        entry["category"] = extra_field or "expense"
                    elif kind == "manual_supplier":
                        entry["source"] = extra_field
                    if add_manual_cashflow_entry(cf.project, kind, entry):
                        st.success(_tl("rv_cf_added", label=kind_label, val=f"{v_val:,.2f}"))
                        st.rerun()
                    else:
                        st.error(_tl("rv_cf_save_err"))
                else:
                    st.warning(_tl("rv_cf_amount_warn"))


# ─────────────────────────────────────────────
# Balance
# ─────────────────────────────────────────────

def render_balance_tab(bal: BalanceReport) -> None:
    """Redesigned Balance tab — NexusBI style (balance_with_capital.html)."""
    from dashboard_charts import _render_html, plotly_theme

    def _bfmt(v):
        s = f"{abs(v):,.0f}".replace(",", ".")
        return f"R$ {s}"

    # ROI calculation
    roi_pct = (bal.saldo_final / bal.inflow_usdt_brl * 100) if bal.inflow_usdt_brl > 0 else 0

    # Stock value: каталог SKU + fallback avg (см. compute_balance)
    stock_val = float(bal.stock_value_brl or 0)
    if stock_val <= 0 and bal.cost_per_unit and bal.stock_units > 0:
        stock_val = bal.cost_per_unit * bal.stock_units
    total_assets = bal.saldo_final + stock_val + bal.pending_rental_brl

    # Percentages for "where is capital" bar
    total_invested = bal.inflows_total if bal.inflows_total > 0 else 1
    pct_cash = (bal.saldo_final / total_invested * 100) if bal.saldo_final > 0 else 0
    pct_stock = (stock_val / total_invested * 100) if stock_val > 0 else 0
    pct_debt = (bal.pending_rental_brl / total_invested * 100) if bal.pending_rental_brl > 0 else 0
    pct_spent = 100 - pct_cash - pct_stock - pct_debt

    # Outflow items for bar chart
    _acc = plotly_theme()["accent"]
    outflows = [
        (_tl("rv_out_goods"), bal.outflow_mercadoria, "#a78bfa"),
        (_tl("rv_out_ads"), bal.outflow_publicidade, "#f59e0b"),
        (_tl("rv_out_returns"), bal.outflow_devolucoes, "#ff5757"),
        (_tl("rv_out_full"), bal.outflow_full_express, "#38bdf8"),
        (_tl("rv_out_das"), bal.outflow_das, _acc),
        (_tl("rv_out_storage"), bal.outflow_armazenagem, "#3d4570"),
        (_tl("rv_out_rent"), bal.outflow_aluguel, "#8892b0"),
    ]
    outflows = [(l, v, c) for l, v, c in outflows if v > 0]

    # Build outflow rows with bars
    outflow_rows = ""
    for label, val, color in outflows:
        pct = (val / bal.outflows_total * 100) if bal.outflows_total > 0 else 0
        outflow_rows += f"""
        <div class="sec-row">
            <div class="row-dot" style="background:{color}"></div>
            <div style="flex:1"><div class="row-lbl">{label}</div></div>
            <div class="row-bar-w"><div class="row-bar-f" style="width:{pct:.0f}%;background:{color}"></div></div>
            <div class="row-pct">{pct:.0f}%</div>
            <div class="row-val" style="color:{color}">-{_bfmt(val)}</div>
        </div>"""

    # USD rate
    usd_rate = (bal.inflow_usdt_brl / bal.inflow_usdt_usd) if bal.inflow_usdt_usd > 0 else 5.64
    inflow_pct_usdt = (bal.inflow_usdt_brl / bal.inflows_total * 100) if bal.inflows_total > 0 else 0
    inflow_pct_sales = 100 - inflow_pct_usdt

    _orders_sub = _tl("rv_orders_n", n=bal.inflow_sales_count)
    _where_inv = _tl("rv_cap_where_title", inv=_bfmt(bal.inflows_total))
    _pct_inv_cash = _tl("rv_pct_of_inv", p=f"{pct_cash:.1f}")
    _pct_inv_stock = _tl("rv_pct_of_inv", p=f"{pct_stock:.1f}")
    _pct_inv_debt = _tl("rv_pct_of_inv", p=f"{pct_debt:.1f}")
    _pct_inv_assets = _tl("rv_pct_of_inv", p=f"{(total_assets / total_invested * 100):.1f}")
    _ar_sub = _tl("rv_where_ar_sub", usd=f"{bal.pending_rental_usd:,.0f}")
    _units_sub = _tl("rv_units_n", n=bal.stock_units)

    _rent_row = ""
    if bal.pending_rental_brl > 0:
        _rent_row = (
            f'<div class="final-row"><div class="final-lbl"><span style="color:var(--amber)">⏳</span> '
            f"{_tl('rv_final_rent_unpaid')}"
            f' <span style="font-family:DM Mono,monospace;font-size:9px;color:var(--amber)">'
            f'${bal.pending_rental_usd:,.0f}</span></div>'
            f'<div class="final-val" style="color:var(--amber)">-{_bfmt(bal.pending_rental_brl)}</div></div>'
        )
    _stock_row = ""
    if stock_val > 0:
        _stock_row = (
            f'<div class="final-row"><div class="final-lbl"><span style="color:var(--green)">📦</span> '
            f"{_tl('rv_final_stock_est')}"
            f' <span style="font-size:9px;color:var(--text3)">{_units_sub}</span></div>'
            f'<div class="final-val" style="color:#a78bfa">+{_bfmt(stock_val)}</div></div>'
        )

    html = f"""
    <!-- KPI ROW -->
    <div class="kpi-row">
        <div class="kpi kpi-in">
            <div class="kpi-lbl">{_tl("rv_bal_inflows")}</div>
            <div class="kpi-val" style="color:var(--green)">{_bfmt(bal.inflows_total)}</div>
            <div class="kpi-sub">{_tl("rv_bal_inflows_sub")}</div>
        </div>
        <div class="kpi kpi-out">
            <div class="kpi-lbl">{_tl("rv_bal_outflows")}</div>
            <div class="kpi-val" style="color:var(--red)">{_bfmt(bal.outflows_total)}</div>
            <div class="kpi-sub">{_tl("rv_bal_outflows_sub", n=len(outflows))}</div>
        </div>
        <div class="kpi kpi-bal">
            <div class="kpi-lbl">{_tl("rv_bal_saldo")}</div>
            <div class="kpi-val" style="color:var(--yellow)">{_bfmt(bal.saldo_final)}</div>
            <div class="kpi-sub">{_tl("rv_bal_saldo_sub")}</div>
        </div>
        <div class="kpi kpi-roi">
            <div class="kpi-lbl">{_tl("rv_bal_roi")}</div>
            <div class="kpi-val" style="color:var(--purple)">{'+' if roi_pct > 0 else ''}{roi_pct:.1f}%</div>
            <div class="kpi-sub">{_bfmt(bal.saldo_final)} / {_bfmt(bal.inflow_usdt_brl)}</div>
        </div>
    </div>

    <!-- CAPITAL BLOCK -->
    <div class="cap-card">
        <div class="cap-hdr">
            <span style="font-size:14px">💼</span>
            <span class="cap-hdr-title">{_tl("rv_cap_title")}</span>
            <span class="cap-hdr-sub">{_tl("rv_cap_sub")}</span>
        </div>
        <div class="cap-body">
            <div class="cap-col">
                <div class="cap-col-title">{_tl("rv_cap_sources")}</div>
                <div class="cap-row">
                    <div class="cap-dot" style="background:var(--blue)"></div>
                    <div class="cap-lbl">{_tl("rv_cap_usdt")}<div style="font-size:9px;color:var(--text3)">{bal.inflow_usdt_usd:,.0f} USDT × {usd_rate:.2f}</div></div>
                    <div class="cap-val" style="color:var(--blue)">{_bfmt(bal.inflow_usdt_brl)}</div>
                </div>
                <div class="cap-row">
                    <div class="cap-dot" style="background:var(--green)"></div>
                    <div class="cap-lbl">{_tl("rv_cap_sales_net")}<div style="font-size:9px;color:var(--text3)">{_orders_sub}</div></div>
                    <div class="cap-val" style="color:var(--green)">{_bfmt(bal.inflow_sales_net)}</div>
                </div>
                <div class="cap-row total-row">
                    <div class="cap-dot" style="background:var(--yellow);width:10px;height:10px"></div>
                    <div class="cap-lbl">{_tl("rv_cap_total_in")}</div>
                    <div class="cap-val" style="color:var(--yellow)">{_bfmt(bal.inflows_total)}</div>
                </div>
            </div>
            <div class="cap-col">
                <div class="cap-col-title">{_tl("rv_cap_spent_col")}</div>
                <div class="cap-row">
                    <div class="cap-dot" style="background:#a78bfa"></div>
                    <div class="cap-lbl">{_tl("rv_cap_cogs")}<div style="font-size:9px;color:var(--text3)">{_tl("rv_cap_cogs_hint")}</div></div>
                    <div class="cap-val" style="color:#a78bfa">-{_bfmt(bal.outflow_mercadoria)}</div>
                </div>
                <div class="cap-row">
                    <div class="cap-dot" style="background:var(--amber)"></div>
                    <div class="cap-lbl">{_tl("rv_cap_opex")}<div style="font-size:9px;color:var(--text3)">{_tl("rv_cap_opex_hint")}</div></div>
                    <div class="cap-val" style="color:var(--amber)">-{_bfmt(bal.outflows_total - bal.outflow_mercadoria)}</div>
                </div>
                <div class="cap-row total-row">
                    <div class="cap-dot" style="background:var(--red);width:10px;height:10px"></div>
                    <div class="cap-lbl">{_tl("rv_cap_total_out")}</div>
                    <div class="cap-val" style="color:var(--red)">-{_bfmt(bal.outflows_total)}</div>
                </div>
            </div>
            <div class="cap-where">
                <div class="cap-where-title">{_where_inv}</div>
                <div class="cap-bar-wrap">
                    <div class="cap-bar-seg" style="width:{pct_cash:.1f}%;background:var(--yellow)"></div>
                    <div class="cap-bar-seg" style="width:{pct_stock:.1f}%;background:#a78bfa"></div>
                    <div class="cap-bar-seg" style="width:{pct_debt:.1f}%;background:var(--amber)"></div>
                    <div class="cap-bar-seg" style="width:{pct_spent:.1f}%;background:var(--red);opacity:.4"></div>
                </div>
                <div class="cap-bar-legend">
                    <div class="cap-bar-leg-item"><div class="cap-bar-leg-dot" style="background:var(--yellow)"></div>{_tl("rv_cap_leg_cash", p=f"{pct_cash:.1f}")}</div>
                    <div class="cap-bar-leg-item"><div class="cap-bar-leg-dot" style="background:#a78bfa"></div>{_tl("rv_cap_leg_stock", p=f"{pct_stock:.1f}")}</div>
                    <div class="cap-bar-leg-item"><div class="cap-bar-leg-dot" style="background:var(--amber)"></div>{_tl("rv_cap_leg_ar", p=f"{pct_debt:.1f}")}</div>
                    <div class="cap-bar-leg-item"><div class="cap-bar-leg-dot" style="background:var(--red);opacity:.5"></div>{_tl("rv_cap_leg_spent", p=f"{pct_spent:.1f}")}</div>
                </div>
                <div class="where-items" style="margin-top:12px">
                    <div class="where-item where-cash">
                        <div class="where-icon">💰</div>
                        <div class="where-lbl">{_tl("rv_where_cash")}</div>
                        <div class="where-val" style="color:var(--yellow)">{_bfmt(bal.saldo_final)}</div>
                        <div class="where-sub">{_tl("rv_where_cash_sub")}</div>
                        <div class="where-pct" style="color:var(--yellow)">{_pct_inv_cash}</div>
                    </div>
                    <div class="where-item where-stock">
                        <div class="where-icon">📦</div>
                        <div class="where-lbl">{_tl("rv_where_stock")}</div>
                        <div class="where-val" style="color:#a78bfa">{_bfmt(stock_val)}</div>
                        <div class="where-sub">{_units_sub}</div>
                        <div class="where-pct" style="color:#a78bfa">{_pct_inv_stock}</div>
                    </div>
                    <div class="where-item where-debt">
                        <div class="where-icon">⏳</div>
                        <div class="where-lbl">{_tl("rv_where_ar")}</div>
                        <div class="where-val" style="color:var(--amber)">{_bfmt(bal.pending_rental_brl)}</div>
                        <div class="where-sub">{_ar_sub}</div>
                        <div class="where-pct" style="color:var(--amber)">{_pct_inv_debt}</div>
                    </div>
                    <div class="where-item where-pnl">
                        <div class="where-icon">📊</div>
                        <div class="where-lbl">{_tl("rv_where_total_assets")}</div>
                        <div class="where-val" style="color:var(--green)">{_bfmt(total_assets)}</div>
                        <div class="where-sub">{_tl("rv_where_assets_sub")}</div>
                        <div class="where-pct" style="color:var(--green)">{_pct_inv_assets}</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- INFLOWS / OUTFLOWS -->
    <div class="bottom-grid">
        <div class="sec">
            <div class="sec-hdr" style="background:rgba(34,211,165,0.06);border-bottom-color:rgba(34,211,165,0.18)">
                <span style="font-size:12px">⬇</span>
                <span class="sec-title" style="color:var(--green,#22d3a5)">{_tl("rv_sec_inflows")}</span>
                <span class="sec-total" style="color:var(--green)">+{_bfmt(bal.inflows_total)}</span>
            </div>
            <div class="sec-row">
                <div class="row-dot" style="background:var(--blue)"></div>
                <div style="flex:1"><div class="row-lbl">{_tl("rv_row_usdt_invest")}</div><div class="row-sub">{bal.inflow_usdt_usd:,.0f} USDT</div></div>
                <div class="row-bar-w"><div class="row-bar-f" style="width:{inflow_pct_usdt:.0f}%;background:var(--blue)"></div></div>
                <div class="row-pct">{inflow_pct_usdt:.0f}%</div>
                <div class="row-val" style="color:var(--blue)">{_bfmt(bal.inflow_usdt_brl)}</div>
            </div>
            <div class="sec-row">
                <div class="row-dot" style="background:var(--green)"></div>
                <div style="flex:1"><div class="row-lbl">{_tl("rv_cap_sales_net")}</div><div class="row-sub">{_orders_sub}</div></div>
                <div class="row-bar-w"><div class="row-bar-f" style="width:{inflow_pct_sales:.0f}%;background:var(--green)"></div></div>
                <div class="row-pct">{inflow_pct_sales:.0f}%</div>
                <div class="row-val" style="color:var(--green)">{_bfmt(bal.inflow_sales_net)}</div>
            </div>
        </div>
        <div class="sec">
            <div class="sec-hdr" style="background:rgba(255,87,87,0.06);border-bottom-color:rgba(255,87,87,0.18)">
                <span style="font-size:12px">⬆</span>
                <span class="sec-title" style="color:var(--red,#ff5757)">{_tl("rv_sec_outflows")}</span>
                <span class="sec-total" style="color:var(--red)">-{_bfmt(bal.outflows_total)}</span>
            </div>
            {outflow_rows}
        </div>
    </div>

    <!-- FINAL CARD -->
    <div class="final-card">
        <div class="final-row"><div class="final-lbl"><span style="color:var(--green)">⬇</span> {_tl("rv_bal_inflows")}</div><div class="final-val" style="color:var(--green)">+{_bfmt(bal.inflows_total)}</div></div>
        <div class="final-row"><div class="final-lbl"><span style="color:var(--red)">⬆</span> {_tl("rv_bal_outflows")}</div><div class="final-val" style="color:var(--red)">-{_bfmt(bal.outflows_total)}</div></div>
        <div class="final-row"><div class="final-lbl"><span style="color:var(--text2)">=</span> {_tl("rv_final_saldo")}</div><div class="final-val" style="color:var(--text)">{_bfmt(bal.saldo)}</div></div>
        {_rent_row}
        <div class="final-row hi"><div class="final-lbl"><span style="font-size:14px">💰</span> {_tl("rv_final_proj_saldo")}</div><div class="final-val" style="color:var(--yellow);font-size:16px">{_bfmt(bal.saldo_final)}</div></div>
        <div class="final-row" style="background:rgba(162,139,250,0.05)"><div class="final-lbl"><span style="color:var(--purple)">📈</span> ROI <span style="font-size:9px;color:var(--text3)">{_tl("rv_final_roi_note")}</span></div><div class="final-val" style="color:var(--purple)">{'+' if roi_pct > 0 else ''}{roi_pct:.1f}%</div></div>
        {_stock_row}
        <div class="final-row" style="background:rgba(34,211,165,0.05)"><div class="final-lbl" style="font-weight:700;color:var(--green);font-size:12px"><span>💼</span> {_tl("rv_final_total_proj_assets")}</div><div class="final-val" style="color:var(--green);font-size:16px">{_bfmt(total_assets)}</div></div>
    </div>

    <style>
        .kpi-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:12px; }}
        .kpi {{ background:var(--bg2,#111526); border:1px solid var(--border,#1f2540); border-radius:10px; padding:11px 13px; position:relative; overflow:hidden; }}
        .kpi::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; }}
        .kpi-in::before {{ background:var(--green,#22d3a5); }} .kpi-out::before {{ background:var(--red,#ff5757); }}
        .kpi-bal::before {{ background:var(--yellow,#FFD500); }} .kpi-roi::before {{ background:var(--purple,#a78bfa); }}
        .kpi-lbl {{ font-size:9px; color:var(--text2,#8892b0); text-transform:uppercase; letter-spacing:.8px; font-weight:700; margin-bottom:4px; }}
        .kpi-val {{ font-size:19px; font-weight:800; font-family:'DM Mono',monospace; line-height:1; margin-bottom:3px; }}
        .kpi-sub {{ font-size:9px; color:var(--text3,#3d4570); }}

        .cap-card {{ background:var(--bg2,#111526); border:1px solid rgba(255,213,0,0.22); border-radius:10px; overflow:hidden; margin-bottom:12px; }}
        .cap-hdr {{ display:flex; align-items:center; gap:8px; padding:11px 14px; border-bottom:1px solid rgba(255,213,0,0.22); background:rgba(255,213,0,0.07); }}
        .cap-hdr-title {{ font-size:12px; font-weight:800; color:var(--yellow,#FFD500); flex:1; }}
        .cap-hdr-sub {{ font-size:10px; color:var(--text2,#8892b0); }}
        .cap-body {{ display:grid; grid-template-columns:1fr 1fr; gap:0; }}
        .cap-col {{ padding:14px; }} .cap-col:first-child {{ border-right:1px solid var(--border,#1f2540); }}
        .cap-col-title {{ font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:.8px; color:var(--text3,#3d4570); margin-bottom:10px; }}
        .cap-row {{ display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(31,37,64,0.4); }}
        .cap-row:last-child {{ border-bottom:none; }}
        .cap-dot {{ width:8px; height:8px; border-radius:2px; flex-shrink:0; }}
        .cap-lbl {{ font-size:11px; color:var(--text2,#8892b0); flex:1; }}
        .cap-val {{ font-size:11px; font-weight:700; font-family:'DM Mono',monospace; text-align:right; }}
        .cap-row.total-row {{ padding-top:10px; margin-top:4px; border-top:1px solid var(--border,#1f2540); border-bottom:none; }}
        .cap-row.total-row .cap-lbl {{ color:var(--text,#f0f2ff); font-weight:700; font-size:12px; }}
        .cap-row.total-row .cap-val {{ font-size:13px; }}
        .cap-where {{ grid-column:1/-1; border-top:1px solid var(--border,#1f2540); padding:12px 14px; }}
        .cap-where-title {{ font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:.8px; color:var(--text3,#3d4570); margin-bottom:10px; }}
        .cap-bar-wrap {{ height:8px; background:var(--bg3,#181d30); border-radius:4px; overflow:hidden; display:flex; gap:1px; margin-bottom:2px; }}
        .cap-bar-seg {{ height:100%; border-radius:2px; }}
        .cap-bar-legend {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; }}
        .cap-bar-leg-item {{ display:flex; align-items:center; gap:4px; font-size:9px; color:var(--text2,#8892b0); }}
        .cap-bar-leg-dot {{ width:8px; height:6px; border-radius:2px; flex-shrink:0; }}
        .where-items {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }}
        .where-item {{ background:var(--bg3,#181d30); border:1px solid var(--border,#1f2540); border-radius:8px; padding:10px 12px; position:relative; overflow:hidden; }}
        .where-item::before {{ content:''; position:absolute; bottom:0; left:0; right:0; height:3px; }}
        .where-cash::before {{ background:var(--yellow,#FFD500); }} .where-stock::before {{ background:#a78bfa; }}
        .where-debt::before {{ background:var(--amber,#f59e0b); }} .where-pnl::before {{ background:var(--green,#22d3a5); }}
        .where-icon {{ font-size:16px; margin-bottom:6px; }}
        .where-lbl {{ font-size:9px; color:var(--text2,#8892b0); font-weight:700; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
        .where-val {{ font-size:15px; font-weight:800; font-family:'DM Mono',monospace; line-height:1; margin-bottom:3px; }}
        .where-sub {{ font-size:9px; color:var(--text3,#3d4570); }}
        .where-pct {{ font-size:10px; font-weight:800; margin-top:4px; }}

        .bottom-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px; }}
        .sec {{ background:var(--bg2,#111526); border:1px solid var(--border,#1f2540); border-radius:10px; overflow:hidden; }}
        .sec-hdr {{ display:flex; align-items:center; gap:8px; padding:10px 13px; border-bottom:1px solid var(--border,#1f2540); }}
        .sec-title {{ font-size:11px; font-weight:800; flex:1; }}
        .sec-total {{ font-size:12px; font-weight:800; font-family:'DM Mono',monospace; }}
        .sec-row {{ display:flex; align-items:center; gap:8px; padding:7px 13px; border-bottom:1px solid rgba(31,37,64,0.35); transition:.12s; }}
        .sec-row:last-child {{ border-bottom:none; }}
        .sec-row:hover {{ background:rgba(255,213,0,0.07); }}
        .row-dot {{ width:6px; height:6px; border-radius:50%; flex-shrink:0; }}
        .row-lbl {{ font-size:11px; color:var(--text2,#8892b0); flex:1; }}
        .row-sub {{ font-size:9px; color:var(--text3,#3d4570); }}
        .row-bar-w {{ width:50px; height:3px; background:var(--bg3,#181d30); border-radius:2px; overflow:hidden; flex-shrink:0; }}
        .row-bar-f {{ height:100%; border-radius:2px; }}
        .row-pct {{ font-size:9px; color:var(--text3,#3d4570); min-width:28px; text-align:right; font-family:'DM Mono',monospace; }}
        .row-val {{ font-size:11px; font-weight:700; font-family:'DM Mono',monospace; }}

        .final-card {{ background:var(--bg2,#111526); border:1px solid rgba(255,213,0,0.22); border-radius:10px; overflow:hidden; }}
        .final-row {{ display:flex; align-items:center; padding:9px 14px; border-bottom:1px solid rgba(31,37,64,0.4); }}
        .final-row:last-child {{ border-bottom:none; }}
        .final-lbl {{ font-size:11px; color:var(--text2,#8892b0); flex:1; display:flex; align-items:center; gap:7px; }}
        .final-val {{ font-size:13px; font-weight:800; font-family:'DM Mono',monospace; }}
        .final-row.hi {{ background:rgba(255,213,0,0.07); }}
        .final-row.hi .final-lbl {{ color:var(--yellow,#FFD500); font-weight:700; font-size:12px; }}
    </style>"""

    _render_html(html, fallback_h=1100)


# ─────────────────────────────────────────────
# Quality
# ─────────────────────────────────────────────

def _get_orphan_pacotes() -> list[dict]:
    """Возвращает список 'Pacote de N produtos' заказов с пустым SKU
    из vendas_ml.xlsx (это multi-item заказы, для которых ML не выгрузил детали)."""
    from reports import load_vendas_ml_report
    df = load_vendas_ml_report()
    if df is None or df.empty:
        return []
    orphan = df[df["__project"] == "PACOTE_SEM_SKU"]
    rows = []
    for _, r in orphan.iterrows():
        rows.append({
            "order_id": str(r.get("N.º de venda", "") or ""),
            "data": str(r.get("Data da venda", "") or ""),
            "estado": str(r.get("Estado", "") or ""),
            "comprador": str(r.get("Comprador", "") or ""),
            "total": float(pd.to_numeric(r.get("Total (BRL)"), errors="coerce") or 0),
            "bucket": str(r.get("__bucket", "") or ""),
        })
    return rows


def _vendas_ml_pnl_by_period(project: str, period_from, period_to) -> dict | None:
    """Считает полный P&L breakdown из vendas_ml.xlsx за период.
    Раздельно для delivered и returned. Возвращает все компоненты.
    """
    from reports import load_vendas_ml_report
    import re as _re
    df = load_vendas_ml_report()
    if df is None or df.empty:
        return None
    pt_months = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
        "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    from datetime import date as _date
    def _pdate(s):
        g = _re.search(r"(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})", str(s))
        if not g: return None
        mn = pt_months.get(g.group(2).lower())
        if not mn: return None
        try: return _date(int(g.group(3)), mn, int(g.group(1)))
        except (ValueError, TypeError): return None
    def _num(v):
        x = pd.to_numeric(v, errors="coerce")
        return 0.0 if pd.isna(x) else float(x)

    # Delivered
    d_gross = d_net = d_tv = d_cnt = 0
    # Returned
    r_gross = r_net = r_tv = r_cnc = r_cnt = 0
    # Реклама (Venda por publicidade = Sim) — только по доставленным
    ad_cnt = 0
    ad_gross = ad_net = 0.0
    delivered_order_ids: set = set()
    for _, row in df.iterrows():
        if row.get("__project") != project: continue
        bucket = row.get("__bucket")
        if bucket not in ("delivered", "returned"): continue
        d = _pdate(row.get("Data da venda"))
        if d is None or d < period_from or d > period_to: continue
        g = _num(row.get("Receita por produtos (BRL)"))
        n = _num(row.get("Total (BRL)"))
        tv = _num(row.get("Tarifa de venda e impostos (BRL)"))  # negative
        cnc = _num(row.get("Cancelamentos e reembolsos (BRL)"))  # negative
        is_ad = str(row.get("Venda por publicidade", "")).strip().lower() == "sim"
        if bucket == "delivered":
            d_gross += g; d_net += n; d_tv += tv; d_cnt += 1
            oid = str(row.get("N.º de venda", "") or "").strip().removesuffix(".0")
            if oid:
                delivered_order_ids.add(oid)
            if is_ad:
                ad_cnt += 1; ad_gross += g; ad_net += n
        else:
            r_gross += g; r_net += n; r_tv += tv; r_cnc += cnc; r_cnt += 1

    # Doplata envios = bruto + tarifa(neg) - cancel(neg) - net  → выводится из тождества
    # Для delivered cnc обычно 0, для returned tv и cnc оба отрицательные.
    d_envios = max(d_gross + d_tv - d_net, 0.0)  # tv negative → эквивалент gross-|tv|-net
    ad_share = (ad_cnt / d_cnt * 100.0) if d_cnt else 0.0
    return {
        "delivered": {"count": d_cnt, "gross": d_gross, "tarifa_venda": d_tv, "envios": d_envios, "net": d_net},
        "returned": {"count": r_cnt, "gross": r_gross, "tarifa_venda": r_tv, "cancelamentos": r_cnc, "net": r_net},
        "ads": {"count": ad_cnt, "gross": ad_gross, "net": ad_net, "share_pct": ad_share},
        "delivered_order_ids": delivered_order_ids,
        "total_net": d_net + r_net,
    }


def render_vendas_ml_tab(project: str, period_from=None, period_to=None) -> None:
    """Сводная панель из vendas_ml.xlsx — статусы, buckets, P&L, по товарам."""
    data = get_vendas_ml_by_project(project)
    if not data:
        st.info("Нет файла `vendas_ml.xlsx` в `_data/{месяц}/`. Выгрузи отчёт из ML и положи туда.")
        return

    # P&L breakdown за период (если period передан)
    if period_from is not None and period_to is not None:
        pnl_data = _vendas_ml_pnl_by_period(project, period_from, period_to)
        if pnl_data:
            d = pnl_data["delivered"]
            r = pnl_data["returned"]
            ads = pnl_data.get("ads", {"count": 0, "gross": 0.0, "net": 0.0, "share_pct": 0.0})
            total_net = pnl_data["total_net"]

            st.markdown(f"### 💰 P&L за период {period_from} → {period_to}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"✅ Доставлено NET ({d['count']})", _fmt_brl(d["net"]))
            c2.metric(f"↩️ Возвращено NET ({r['count']})", _fmt_brl(r["net"]))
            c3.metric("💰 Итого на счёт", _fmt_brl(total_net))
            c4.metric(
                f"📣 По рекламе ({ads['count']})",
                _fmt_brl(ads["net"]),
                help=f"{ads['share_pct']:.1f}% от доставленных заказов · Bruto {_fmt_brl(ads['gross'])}",
            )

            # ── Доставлено ──
            st.markdown("#### ✅ Доставлено")
            st.dataframe(
                pd.DataFrame([
                    {"Статья": f"Receita por produtos ({d['count']:,} заказов)", "R$": d["gross"]},
                    {"Статья": "(−) Tarifa de venda e impostos", "R$": d["tarifa_venda"]},
                    {"Статья": "(−) Доплата за доставку (envios)", "R$": -d["envios"]},
                    {"Статья": "= Total NET (доставленные)", "R$": d["net"]},
                ]),
                width="stretch",
                hide_index=True,
                column_config={"R$": _money_col()},
            )

            # ── Возвращено ──
            if r["count"] > 0:
                st.markdown("#### ↩️ Возвращено / отменено")
                st.dataframe(
                    pd.DataFrame([
                        {"Статья": f"Receita por produtos ({r['count']:,} заказов)", "R$": r["gross"]},
                        {"Статья": "(−) Tarifa de venda e impostos", "R$": r["tarifa_venda"]},
                        {"Статья": "(−) Cancelamentos e reembolsos", "R$": r["cancelamentos"]},
                        {"Статья": "= Total NET (возвращённые)", "R$": r["net"]},
                    ]),
                    width="stretch",
                    hide_index=True,
                    column_config={"R$": _money_col()},
                )

            # ── Итог ──
            st.markdown("#### 💰 Итого реально на счёте")
            st.dataframe(
                pd.DataFrame([
                    {"Статья": "Total NET доставленных", "R$": d["net"]},
                    {"Статья": "+ Total NET возвращённых (обычно ~0)", "R$": r["net"]},
                    {"Статья": "= ИТОГО на счёт", "R$": total_net},
                ]),
                width="stretch",
                hide_index=True,
                column_config={"R$": _money_col()},
            )
            st.caption(
                "Источник: vendas_ml.xlsx, колонки Receita por produtos / Tarifa de venda / "
                "Cancelamentos e reembolsos / Total (BRL). Учтены и доставленные, и возвращённые "
                "заказы за выбранный период (с учётом ручных назначений Pacotes)."
            )

            # ── Расходы за период (Mercado Ads + Armazenagem) ──
            st.markdown("#### 💸 Расходы за период (Mercado Ads + Armazenagem)")
            pub = get_publicidade_by_period(project, period_from, period_to)
            arm = get_armazenagem_by_period(project, period_from, period_to)

            ec1, ec2, ec3 = st.columns(3)
            ec1.metric("Publicidade", _fmt_brl(pub["total"]))
            ec2.metric("Armazenagem", _fmt_brl(arm["total"]))
            ec3.metric("Σ расходов", _fmt_brl(pub["total"] + arm["total"]))

            final_net = total_net - pub["total"] - arm["total"]
            st.dataframe(
                pd.DataFrame([
                    {"Статья": "Total NET (доставленные + возвращённые)", "R$": total_net},
                    {"Статья": f"(−) Publicidade (Mercado Ads, {len(pub['files_used'])} файлов)", "R$": -pub["total"]},
                    {"Статья": f"(−) Armazenagem (Full, {arm['days_in_period']} дней × {arm['skus_count']} SKU)", "R$": -arm["total"]},
                    {"Статья": "= NET после рекламы и хранения", "R$": final_net},
                ]),
                width="stretch",
                hide_index=True,
                column_config={"R$": _money_col()},
            )

            if pub["files_used"]:
                lines = "\n".join(
                    f"  • `{f['file_name']}` — {f['days_used']}/{f['total_days']} дней ({f['ratio']*100:.0f}%)"
                    for f in pub["files_used"]
                )
                st.caption(
                    f"📂 Файлы рекламы (пропорционально дням пересечения):\n{lines}"
                )
            else:
                st.info("ℹ️ Нет файлов publicidade в `_data/publicidade/` или `_data/{месяц}/ads_publicidade.*`.")
            if pub.get("uncovered_days", 0) > 0:
                st.warning(
                    f"⚠️ {pub['uncovered_days']} из {pub['total_days']} дней периода "
                    "не покрыты файлами рекламы. Реальная сумма больше показанной — "
                    "выгрузи дополнительный отчёт за эти дни из Mercado Ads."
                )
            if arm["source_file"]:
                st.caption(f"📂 Armazenagem источник: `{arm['source_file']}`")
            else:
                st.info("ℹ️ Нет файлов armazenagem в `_data/armazenagem/`.")

            st.divider()

    delivered = data["delivered"]
    returned = data["returned"]
    in_progress = data["in_progress"]
    total = data["total"]

    st.markdown(f"### 📦 Vendas ML — {project}")
    st.caption(f"Источник: `{data.get('source_file','')}`")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        f"✅ Доставлено ({delivered['count']})",
        _fmt_brl(delivered["net"]),
        help=f"{delivered['units']} ед.",
    )
    c2.metric(
        f"↩️ Возвращено ({returned['count']})",
        _fmt_brl(returned["net"]),
        help=f"{returned['units']} ед.",
    )
    c3.metric(
        f"⏳ В процессе ({in_progress['count']})",
        _fmt_brl(in_progress["net"]),
        help=f"{in_progress['units']} ед.",
    )

    total_count = total["count"] or 1
    rows = []
    for label, b in [
        ("✅ Доставлено", delivered),
        ("↩️ Возвращено", returned),
        ("⏳ В процессе", in_progress),
        ("ИТОГО", total),
    ]:
        rows.append({
            "Bucket": label,
            "Заказов": b["count"],
            "Единиц": b["units"],
            "Bruto R$": b["bruto"],
            "NET R$": b["net"],
            "% от total": f"{b['count'] / total_count * 100:.1f}%",
        })
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Bruto R$": _money_col("Bruto R$"),
            "NET R$": _money_col("NET R$"),
        },
    )

    # Reclamações: топ-причины возвратов из claims-CSV
    dev = get_devolucoes_by_project().get(project) or {}
    if dev.get("count"):
        with st.expander(f"↩️ Reclamações — {dev['count']} шт, R$ {dev['total']:,.2f}", expanded=False):
            # Топ артикулов по reclamações
            sku_dict = dev.get("by_sku", {}) or {}
            if sku_dict:
                st.markdown("**🔝 Топ артикулов по reclamações:**")
                rows_sku = sorted(
                    [
                        {
                            "SKU": v["sku"],
                            "Название": (v.get("title") or "")[:60],
                            "Reclamações": v["count"],
                            "Сумма R$": v["amount"],
                        }
                        for v in sku_dict.values()
                    ],
                    key=lambda r: -r["Reclamações"],
                )
                st.dataframe(
                    pd.DataFrame(rows_sku),
                    width="stretch",
                    hide_index=True,
                    column_config={"Сумма R$": _money_col("Сумма R$")},
                )

            motivos = dev.get("by_motivo", {}) or {}
            if motivos:
                rows_m = sorted(
                    [{"Мотив": m, "Кол-во": c} for m, c in motivos.items() if m and m != "?"],
                    key=lambda r: -r["Кол-во"],
                )
                if rows_m:
                    st.markdown("**Топ мотивов:**")
                    st.dataframe(pd.DataFrame(rows_m), width="stretch", hide_index=True)
                else:
                    st.caption("Мотивы недоступны в claims-CSV (поле пустое для статуса approved/closed).")
            statuses = dev.get("by_status", {}) or {}
            if statuses:
                st.markdown("**По статусам:**")
                st.dataframe(
                    pd.DataFrame([{"Статус": s, "Кол-во": c} for s, c in statuses.items()]),
                    width="stretch",
                    hide_index=True,
                )

    by_month = data.get("by_month") or []
    if by_month:
        with st.expander(f"📅 По месяцам ({len(by_month)} мес.)", expanded=True):
            st.dataframe(
                pd.DataFrame([
                    {
                        "Месяц": r["month"],
                        "Доставлено": r["delivered"],
                        "Доставлено R$": r["delivered_net"],
                        "Возвращено": r["returned"],
                        "В процессе": r["in_progress"],
                        "Всего": r["total"],
                        "Всего R$": r["total_net"],
                    }
                    for r in by_month
                ]),
                width="stretch",
                hide_index=True,
                column_config={
                    "Доставлено R$": _money_col("Доставлено R$"),
                    "Всего R$": _money_col("Всего R$"),
                },
            )

    # Orphan pacotes — общие для всей выгрузки, показываем во всех проектах
    orphans = _get_orphan_pacotes()
    if orphans:
        from reports import load_orphan_assignments, save_orphan_assignment
        manual = load_orphan_assignments()
        # Только реально orphan (не назначенные) + назначенные на этот проект
        unassigned = [o for o in orphans if o["order_id"] not in manual]
        assigned_here = [o for o in orphans if manual.get(o["order_id"]) == project]

        delivered_unassigned = [o for o in unassigned if o["bucket"] == "delivered"]
        total_unassigned = sum(o["total"] for o in delivered_unassigned)

        with st.expander(
            f"⚠️ Pacotes без SKU — {len(delivered_unassigned)} нераспределённых на R$ {total_unassigned:,.2f}",
            expanded=False,
        ):
            st.caption(
                "Multi-item заказы из ML где SKU не выгружен. Открой ссылку, "
                "посмотри что внутри, выбери проект и сохрани — заказ "
                "автоматически прибавится к нужному."
            )

            ecom_projects = ["ARTUR", "ORGANIZADORES", "JOOM"]

            with st.form(key=f"orphan_form_{project}", clear_on_submit=False):
                # Заголовок
                hcols = st.columns([2, 1, 2, 2, 1.5])
                hcols[0].markdown("**Order ID**")
                hcols[1].markdown("**R$**")
                hcols[2].markdown("**Дата**")
                hcols[3].markdown("**Comprador**")
                hcols[4].markdown("**Проект**")

                selections: dict = {}
                for o in orphans:
                    oid = o["order_id"]
                    current = manual.get(oid, "—")
                    cols = st.columns([2, 1, 2, 2, 1.5])
                    cols[0].markdown(
                        f"[`{oid}`](https://www.mercadolivre.com.br/vendas/{oid}/detalhe)"
                    )
                    cols[1].markdown(f"{o['total']:,.2f}")
                    cols[2].markdown(f"{o['data'][:20]}")
                    cols[3].markdown(f"{o['comprador'][:25]}")
                    options = ["—"] + ecom_projects
                    idx = options.index(current) if current in options else 0
                    selections[oid] = cols[4].selectbox(
                        "проект",
                        options,
                        index=idx,
                        key=f"orphan_sel_{oid}_{project}",
                        label_visibility="collapsed",
                    )

                if st.form_submit_button("💾 Сохранить все изменения"):
                    changed = 0
                    for oid, new_proj in selections.items():
                        old = manual.get(oid, "—")
                        if new_proj != old:
                            save_orphan_assignment(oid, new_proj if new_proj != "—" else None)
                            changed += 1
                    if changed:
                        st.success(f"Сохранено: {changed} изменений")
                        st.rerun()
                    else:
                        st.info("Нет изменений для сохранения")

            if assigned_here:
                st.markdown(
                    f"---\n**Уже назначено на {project}:** {len(assigned_here)} заказов на "
                    f"R$ {sum(o['total'] for o in assigned_here):,.2f} "
                    f"(они уже включены в `Доставлено` выше)."
                )

    by_sku = data.get("by_sku") or []
    if by_sku:
        with st.expander(f"📦 По товарам ({len(by_sku)} SKU)", expanded=False):
            sort_mode = st.radio(
                "Сортировка",
                ["По NET ↓", "По возвратам ↓"],
                horizontal=True,
                key=f"vml_sort_{project}",
            )
            sorted_sku = (
                sorted(by_sku, key=lambda r: -r["returned_units"])
                if sort_mode == "По возвратам ↓"
                else by_sku  # уже отсортирован по net в reports.py
            )
            st.dataframe(
                pd.DataFrame([
                    {
                        "SKU": r["sku"],
                        "Название": (r["title"] or "")[:60],
                        "Доставлено ед.": r["delivered_units"],
                        "Возвращено ед.": r["returned_units"],
                        "% возврата": (
                            f"{r['returned_units']/(r['delivered_units']+r['returned_units'])*100:.1f}%"
                            if (r['delivered_units']+r['returned_units']) else "—"
                        ),
                        "В процессе ед.": r["in_progress_units"],
                        "NET R$": r["net"],
                    }
                    for r in sorted_sku
                ]),
                width="stretch",
                hide_index=True,
                column_config={"NET R$": _money_col("NET R$")},
            )


def render_quality_tab(proj: dict, pnl: PnLReport, cf: CashFlowReport, bal: BalanceReport) -> None:
    issues: list[str] = []
    if bal.stock_units > 0 and float(bal.stock_value_brl or 0) <= 0:
        issues.append(
            "**Сток не оценён** — задайте цены в каталоге SKU (`_data/sku_catalog.json`) "
            "и/или `avg_cost_per_unit_brl` в проекте."
        )
    elif bal.stock_missing_units and bal.stock_missing_units > 0:
        issues.append(
            f"**Часть стока без цены** — {bal.stock_missing_units} шт. без строки в каталоге "
            f"и без средней себестоимости (см. вкладку SKU маппинг)."
        )
    if pnl.cogs is None:
        issues.append("**COGS = N/A** — нужны: средний себес единицы (BRL/шт) и кол-во проданных. Без этого Чистая прибыль не вычисляется.")
    if bal.outflow_mercadoria == 0:
        issues.append("**Mercadoria (товар) = 0** — не настроено в `baseline_overrides` или утверждённом CSV.")
    rental = proj.get("rental") or {}
    pending = [p for p in (rental.get("payments") or []) if p.get("status") == "pending"]
    for p in pending:
        issues.append(f"**Просроченная аренда**: {p.get('quarter', '')} — ${p.get('usd', 0)}")

    if issues:
        st.markdown("### ⚠️ Замечания по качеству данных")
        for it in issues:
            st.warning(it)
    else:
        st.success("Все ключевые проверки пройдены.")

    tasks = proj.get("tasks") or []
    if tasks:
        st.markdown("### 📌 TODO по проекту")
        st.dataframe(
            pd.DataFrame([
                {"Приоритет": t.get("priority", ""),
                 "Задача": t.get("title", ""),
                 "Комментарий": t.get("note", "")}
                for t in tasks
            ]),
            width="stretch",
            hide_index=True,
        )
