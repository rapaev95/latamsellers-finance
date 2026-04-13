"""
Страница настроек правил автоклассификации банковских выписок (bank_transaction_rules.json).
Redesigned: custom HTML header/KPIs + editable st.data_editor table.
"""
import copy
import html as html_mod
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import (
    BANK_TRANSACTION_RULES_PATH,
    DEFAULT_TRANSACTION_RULES,
    load_transaction_rules,
    normalize_transaction_rules_list,
    save_transaction_rules,
)
from i18n import t


# ── CSS for header/KPI block ──
HEADER_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#09090b;--bg2:#18181b;--bg3:#27272a;--bg4:#3f3f46;
  --border:#27272a;--border2:#3f3f46;
  --yellow:#facc15;--ydim:rgba(250,204,21,0.06);--yborder:rgba(250,204,21,0.2);
  --text:#fafafa;--text2:#a1a1aa;--text3:#52525b;
  --green:#4ade80;--blue:#60a5fa;
  --radius:10px;
}
body{margin:0;padding:0;font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text)}
.root{padding:16px 4px 8px}

.hdr{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.hdr-icon{width:38px;height:38px;background:linear-gradient(135deg,var(--yellow),#f59e0b);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.hdr-left{flex:1}
.hdr-title{font-size:17px;font-weight:800;letter-spacing:-0.3px}
.hdr-sub{font-size:11px;color:var(--text2);margin-top:2px}
.hdr-sub code{font-family:'JetBrains Mono',monospace;font-size:10px;background:var(--bg3);padding:1px 5px;border-radius:4px;color:var(--text2)}

.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.kpi-y::before{background:var(--yellow)}.kpi-g::before{background:var(--green)}
.kpi-b::before{background:var(--blue)}.kpi-n::before{background:var(--text3)}
.kpi-lbl{font-size:9px;color:var(--text2);text-transform:uppercase;letter-spacing:.7px;font-weight:700;margin-bottom:4px}
.kpi-val{font-size:20px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}
.kpi-sub{font-size:10px;color:var(--text3);margin-top:3px;font-weight:500}

::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bg4);border-radius:3px}
"""


def _rules_to_df(rules: list) -> pd.DataFrame:
    rows = []
    for r in rules:
        rows.append({
            "keywords": ", ".join(r.get("keywords") or []),
            "category": r.get("category") or "",
            "project": (r.get("project") or "") if r.get("project") else "",
            "label": r.get("label") or "",
        })
    return pd.DataFrame(rows, columns=["keywords", "category", "project", "label"])


def _cell_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _df_to_rules(df: pd.DataFrame) -> list:
    rules = []
    for _, row in df.iterrows():
        rules.append({
            "keywords": _cell_str(row.get("keywords", "")),
            "category": _cell_str(row.get("category", "")),
            "project": _cell_str(row.get("project", "")),
            "label": _cell_str(row.get("label", "")),
        })
    return rules


def _render_header_html(total: int, n_cats: int, with_proj: int, without_proj: int, L: str) -> str:
    title = html_mod.escape(t('bank_rules_title', L).replace('🏦 ', ''))
    sub = html_mod.escape(t('bank_rules_intro', L))
    fname = BANK_TRANSACTION_RULES_PATH.name

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{HEADER_CSS}</style></head>
<body>
<div class="root">
  <div class="hdr">
    <div class="hdr-icon">📋</div>
    <div class="hdr-left">
      <div class="hdr-title">{title}</div>
      <div class="hdr-sub">{sub} · <code>{fname}</code></div>
    </div>
  </div>
  <div class="kpi-row">
    <div class="kpi kpi-y"><div class="kpi-lbl">{"Всего правил" if L == "ru" else "Total regras"}</div><div class="kpi-val" style="color:var(--yellow)">{total}</div><div class="kpi-sub">{"Авто-классификация" if L == "ru" else "Auto-classificação"}</div></div>
    <div class="kpi kpi-g"><div class="kpi-lbl">{"Категорий" if L == "ru" else "Categorias"}</div><div class="kpi-val" style="color:var(--green)">{n_cats}</div><div class="kpi-sub">{"Типов операций" if L == "ru" else "Tipos"}</div></div>
    <div class="kpi kpi-b"><div class="kpi-lbl">{"С проектом" if L == "ru" else "Com projeto"}</div><div class="kpi-val" style="color:var(--blue)">{with_proj}</div><div class="kpi-sub">{"Привязаны" if L == "ru" else "Vinculados"}</div></div>
    <div class="kpi kpi-n"><div class="kpi-lbl">{"Без проекта" if L == "ru" else "Sem projeto"}</div><div class="kpi-val" style="color:var(--text2)">{without_proj}</div><div class="kpi-sub">{"Общие" if L == "ru" else "Gerais"}</div></div>
  </div>
</div>
</body></html>"""


def render_bank_rules_page(L: str) -> None:
    # ── Load rules ──
    if "bank_rules_pending_df" in st.session_state:
        base_df = st.session_state.pop("bank_rules_pending_df")
    else:
        base_df = _rules_to_df(load_transaction_rules())

    # ── KPI data ──
    rules_raw = load_transaction_rules()
    total = len(rules_raw)
    cats = set(r.get("category", "") for r in rules_raw if r.get("category"))
    with_proj = sum(1 for r in rules_raw if r.get("project"))
    without_proj = total - with_proj

    # ── Render HTML header + KPIs ──
    header_html = _render_header_html(total, len(cats), with_proj, without_proj, L)
    components.html(header_html, height=210, scrolling=False)

    # ── Reupload note ──
    st.caption(t("bank_rules_reupload_note", L))

    # ── Editable table — the main interface ──
    edited = st.data_editor(
        base_df,
        column_config={
            "keywords": st.column_config.TextColumn(
                t("bank_rules_col_keywords", L),
                width="large",
                help=t("bank_rules_keywords_help", L),
            ),
            "category": st.column_config.TextColumn(
                t("bank_rules_col_category", L),
                width="medium",
            ),
            "project": st.column_config.TextColumn(
                t("bank_rules_col_project", L),
                width="small",
                help=t("bank_rules_project_empty", L),
            ),
            "label": st.column_config.TextColumn(
                t("bank_rules_col_label", L),
                width="large",
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="bank_rules_editor",
    )

    # ── Save / Export buttons ──
    row_save, row_dl = st.columns([1, 1])
    with row_save:
        if st.button(t("bank_rules_save", L), type="primary", key="bank_rules_save_btn"):
            try:
                rules = normalize_transaction_rules_list(_df_to_rules(edited))
                if not rules:
                    st.error(t("bank_rules_empty_error", L))
                else:
                    save_transaction_rules(rules)
                    st.success(t("bank_rules_saved", L))
                    st.rerun()
            except Exception as e:
                st.error(str(e))
    with row_dl:
        rules_for_export = normalize_transaction_rules_list(_df_to_rules(edited))
        export_payload = json.dumps(rules_for_export, indent=2, ensure_ascii=False)
        st.download_button(
            label=t("bank_rules_export", L),
            data=export_payload.encode("utf-8"),
            file_name="bank_transaction_rules.json",
            mime="application/json",
            key="bank_rules_download",
        )

    # ── Import ──
    st.divider()
    st.markdown(f"**{t('bank_rules_import', L)}**")
    st.caption(t("bank_rules_import_hint", L))
    up = st.file_uploader(
        t("bank_rules_file_label", L),
        type=["json"],
        key="bank_rules_file_uploader",
    )
    if st.button(t("bank_rules_import_btn", L), key="bank_rules_import_apply"):
        if up is None:
            st.warning(t("bank_rules_no_file", L))
        else:
            try:
                raw = up.getvalue()
                data = json.loads(raw.decode("utf-8"))
                if isinstance(data, dict) and isinstance(data.get("rules"), list):
                    data = data["rules"]
                if not isinstance(data, list):
                    raise ValueError("expected JSON array of rules")
                loaded = normalize_transaction_rules_list(data)
                if not loaded:
                    st.error(t("bank_rules_import_error", L))
                else:
                    st.session_state["bank_rules_pending_df"] = _rules_to_df(loaded)
                    st.success(t("bank_rules_import_applied", L))
                    st.rerun()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
                st.error(t("bank_rules_import_error", L))

    # ── Reset ──
    st.divider()
    with st.expander(t("bank_rules_reset", L)):
        st.caption(t("bank_rules_reset_help", L))
        if st.button(t("bank_rules_reset_confirm", L), type="secondary", key="bank_rules_reset_do"):
            save_transaction_rules(copy.deepcopy(DEFAULT_TRANSACTION_RULES))
            st.success(t("bank_rules_saved", L))
            st.rerun()
