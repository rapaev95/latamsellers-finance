"""
LATAMSELLERS — Financial Admin Panel
Run: python -m streamlit run _admin/app.py
"""
import sys
from pathlib import Path

# Локальный config.py, а не одноимённый пакет из site-packages (иначе KeyError и пр.)
_admin_dir = str(Path(__file__).resolve().parent)
if _admin_dir in sys.path:
    sys.path.remove(_admin_dir)
sys.path.insert(0, _admin_dir)

import streamlit as st
import pandas as pd
import io
import html as html_escape
from datetime import datetime, date
from config import (
    BASE_DIR, DATA_DIR, PROJETOS_DIR, DATA_SOURCES, MONTHS,
    SKU_PREFIXES, ARTUR_MLBS_FALLBACK, get_project_by_sku, KNOWN_PASSWORDS,
    load_projects, save_projects, add_project, delete_project, get_compensation_mode,
    update_project,
    classify_transaction,
)

# Always reload projects fresh (they can change via UI)
PROJECTS = load_projects()
from i18n import current_lang, t
from unlocker import try_unlock
from auth import require_auth, get_current_user

st.set_page_config(
    page_title="LATAMSELLERS FINANCE",
    page_icon="💛",
    layout="wide",
)

# ── Auth gate ──
_auth_user = require_auth()
if _auth_user is None:
    st.stop()


def _classification_json_fingerprint() -> tuple[tuple[str, int], ...]:
    """Лёгкий отпечаток JSON классификаций для инвалидации кэша дашборда."""
    paths: list[tuple[str, int]] = []
    for month_d in MONTHS:
        for src_d in ("extrato_nubank", "extrato_c6_brl", "extrato_c6_usd", "extrato_mp"):
            jp = DATA_DIR / month_d / f"{src_d}_classifications.json"
            if jp.exists():
                try:
                    paths.append((str(jp.resolve()), jp.stat().st_mtime_ns))
                except OSError:
                    pass
    return tuple(sorted(paths))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_generate_opiu_from_vendas():
    from reports import generate_opiu_from_vendas

    return generate_opiu_from_vendas()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_dashboard_pending_classification(
    fp: tuple[tuple[str, int], ...],
    lang: str,
) -> list[dict]:
    import json as json_mod_dash

    from i18n import t as _t

    pending_files: list[dict] = []
    for month_d in MONTHS:
        for src_d in ["extrato_nubank", "extrato_c6_brl", "extrato_c6_usd", "extrato_mp"]:
            jp = DATA_DIR / month_d / f"{src_d}_classifications.json"
            if not jp.exists():
                continue
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    d = json_mod_dash.load(f)
                txs = d.get("transactions", [])
                splits = d.get("full_express_splits", {})

                def in_split_group(t_):
                    cat = t_.get("Категория", "")
                    label_lo = str(t_.get("Класс.", "")).lower()
                    return (
                        cat == "fulfillment"
                        or "fatura ml" in label_lo
                        or "retido" in label_lo
                        or "devolu" in label_lo
                        or "reclamaç" in label_lo
                    )

                unc = sum(
                    1 for t_ in txs if t_.get("Категория") == "uncategorized" and not in_split_group(t_)
                )
                no_proj = sum(
                    1
                    for t_ in txs
                    if (not t_.get("Проект") or t_.get("Проект") in ("❓", "—", ""))
                    and not in_split_group(t_)
                    and t_.get("Категория") != "uncategorized"
                )

                group_totals = {"fulfillment": 0, "fatura_ml": 0, "retido": 0, "devolucoes": 0}
                for t_ in txs:
                    cat = t_.get("Категория", "")
                    label_lo = str(t_.get("Класс.", "")).lower()
                    val_abs = abs(float(t_.get("Valor", 0) or 0))
                    if cat == "fulfillment":
                        group_totals["fulfillment"] += val_abs
                    elif "fatura ml" in label_lo:
                        group_totals["fatura_ml"] += val_abs
                    elif "retido" in label_lo:
                        group_totals["retido"] += val_abs
                    elif "devolu" in label_lo or "reclamaç" in label_lo:
                        group_totals["devolucoes"] += val_abs

                pending_groups = []
                for gk, gtotal in group_totals.items():
                    if gtotal == 0:
                        continue
                    grp_data = splits.get(gk, {})
                    if isinstance(grp_data, dict) and "split" in grp_data:
                        split_sum = sum(grp_data.get("split", {}).values())
                    else:
                        split_sum = 0
                    if abs(split_sum - gtotal) > 0.01:
                        pending_groups.append(gk)

                issues = []
                if unc > 0:
                    issues.append(_t("dash_issue_unc", lang).format(n=unc))
                if no_proj > 0:
                    issues.append(_t("dash_issue_no_proj", lang).format(n=no_proj))
                if pending_groups:
                    issues.append(_t("dash_issue_splits", lang).format(n=len(pending_groups)))

                if issues:
                    src_name = DATA_SOURCES.get(src_d, {}).get("name", src_d)
                    pending_files.append(
                        {
                            "month": month_d,
                            "src": src_d,
                            "name": src_name,
                            "issues": issues,
                        }
                    )
            except Exception:
                pass
    return pending_files


# ─────────────────────────────────────────────
# THEME & LANG STATE (read from query params to survive reload)
# ─────────────────────────────────────────────
_qp_early = st.query_params
if "theme" not in st.session_state:
    st.session_state.theme = _qp_early.get("theme", "night")
if "lang" not in st.session_state:
    st.session_state.lang = _qp_early.get("lang", "ru")
_IS_NIGHT = st.session_state.theme == "night"

# ─────────────────────────────────────────────
# GLOBAL THEME CSS (conditional night/day)
# ─────────────────────────────────────────────
if _IS_NIGHT:
    _bg = "#0b0e1a"; _bg2 = "#111526"; _bg3 = "#181d30"
    _border = "#1f2540"; _text = "#f0f2ff"; _text2 = "#a8b2d1"; _text3 = "#6272a4"
    _header_bg = "rgba(11,14,26,0.95)"
    _sidebar_bg = "#0b0e1a"; _sidebar_border = "#1f2540"
    _hover_bg = "#f8fafc00"  # transparent
    _tab_inactive = "#6272a4"
    _alert_bg = "rgba(245,158,11,0.1)"; _alert_border = "rgba(245,158,11,0.3)"; _alert_color = "#fbbf24"
    _tab_sel_bg = "rgba(255,213,0,0.10)"; _tab_sel_border = "#FFD500"; _tab_sel_color = "#FFD500"
    _nav_hover_bg = "rgba(255,213,0,0.06)"; _nav_sel_bg = "rgba(255,213,0,0.08)"; _nav_sel_color = "#FFD500"
    _brand_box = "#FFD500"; _brand_finance = "#FFD500"; _brand_sidebar_title = "#f0f2ff"
    _sb_select_hover_bd = "rgba(255,213,0,0.3)"
else:
    _bg = "#F4F6FA"; _bg2 = "#FFFFFF"; _bg3 = "#EEF1F8"
    _border = "#DDE2EF"; _text = "#0d1033"; _text2 = "#5a6385"; _text3 = "#586174"
    _header_bg = "rgba(244,246,250,0.95)"
    _sidebar_bg = "#FFFFFF"; _sidebar_border = "#DDE2EF"
    _hover_bg = "#f8fafc"
    _tab_inactive = "#586174"
    _alert_bg = "rgba(245,158,11,0.12)"; _alert_border = "rgba(217,119,6,0.42)"; _alert_color = "#9a3412"
    _tab_sel_bg = "rgba(230,184,0,0.18)"; _tab_sel_border = "#C9A000"; _tab_sel_color = "#5c4d00"
    _nav_hover_bg = "rgba(230,184,0,0.08)"; _nav_sel_bg = "rgba(230,184,0,0.12)"; _nav_sel_color = "#6b5600"
    _brand_box = "#E6B800"; _brand_finance = "#7c5f00"; _brand_sidebar_title = "#0d1033"
    _sb_select_hover_bd = "rgba(230,184,0,0.45)"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap');

/* ── Theme ── */
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {{
    background: {_bg} !important;
    color: {_text} !important;
}}
[data-testid="stHeader"] {{
    background: {_header_bg} !important;
    backdrop-filter: blur(8px);
}}

/* ── Шапка + dev toolbar (File change / Rerun): не перекрывать дашборд ── */
header.stAppHeader {{
    position: relative !important;
    z-index: 100002 !important;
    flex-shrink: 0 !important;
    width: 100% !important;
}}
[data-testid="stToolbar"] {{
    position: relative !important;
    inset: auto !important;
    width: 100% !important;
    flex-shrink: 0 !important;
    z-index: 100003 !important;
}}

.block-container {{
    padding-top: 1rem !important;
}}
/* Если тулбар остаётся поверх контента — доп. отступ (~60px) */
.stApp:has([data-testid="stToolbar"]) section.main .block-container,
.stApp:has([data-testid="stToolbar"]) .stMain .block-container {{
    padding-top: calc(1rem + 60px) !important;
}}

/* Text colors */
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 {{
    color: {_text} !important;
    font-family: 'Nunito Sans', sans-serif !important;
}}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] {{
    color: {_text2} !important;
}}
[data-testid="stMarkdownContainer"] strong {{
    color: {_text} !important;
}}

/* Tabs */
[data-testid="stTabs"] button {{
    background: transparent !important;
    border: 1px solid {_border} !important;
    border-radius: 5px !important;
    color: {_tab_inactive} !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    padding: 4px 12px !important;
    font-family: 'Nunito Sans', sans-serif !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
[data-testid="stTabs"] button[aria-selected="true"] {{
    background: rgba(255,213,0,0.10) !important;
    border-color: #FFD500 !important;
    color: #FFD500 !important;
}}
[data-testid="stTabs"] [role="tablist"] {{
    gap: 4px !important;
    border-bottom: none !important;
}}

/* Container borders */
[data-testid="stExpander"] {{
    background: {_bg2} !important;
    border: 1px solid {_border} !important;
    border-radius: 10px !important;
}}
[data-testid="stExpander"] summary {{
    color: {_text2} !important;
}}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {{
    color: {_text2} !important;
}}
div[data-testid="stVerticalBlock"] > div[style*="border"] {{
    background: {_bg2} !important;
    border-color: {_border} !important;
    border-radius: 10px !important;
}}

/* Warning/Info/Error boxes */
[data-testid="stAlert"] {{
    background: {_alert_bg} !important;
    border: 1px solid {_alert_border} !important;
    color: {_alert_color} !important;
    border-radius: 8px !important;
}}

/* Selectbox, inputs */
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stTextInput"] label,
[data-testid="stFileUploader"] label {{
    color: {_text2} !important;
}}

/* Dataframes */
[data-testid="stDataFrame"] {{
    background: {_bg2} !important;
    border-radius: 8px !important;
}}

/* Dividers */
hr, [data-testid="stHorizontalRule"] {{
    border-color: {_border} !important;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background: {_sidebar_bg} !important;
    border-right: 1px solid {_sidebar_border} !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding-top: 0.5rem !important;
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li {{
    color: {_text2} !important;
}}

/* ── Hide radio dot/circle ── */
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child,
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:has(svg),
[data-testid="stSidebar"] [role="radiogroup"] label svg,
[data-testid="stSidebar"] [role="radiogroup"] label [data-baseweb="radio"],
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:not(:has(p)) {{
    display: none !important;
    width: 0 !important; height: 0 !important; min-width: 0 !important;
    overflow: hidden !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] [data-testid="stMarkdownContainer"] {{
    color: inherit !important;
}}

/* ── Radio nav items ── */
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 0 !important; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
    background: transparent !important;
    border: none !important;
    border-left: 3px solid transparent !important;
    border-radius: 0 !important;
    padding: 9px 14px !important;
    margin: 0 !important;
    font-family: 'Nunito Sans', sans-serif !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: {_text2} !important;
    transition: all 0.15s !important;
    cursor: pointer !important;
    white-space: normal !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    line-height: 1.35 !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label p {{
    white-space: normal !important;
    word-wrap: break-word !important;
    margin: 0 !important;
    line-height: 1.35 !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
    color: {_text} !important;
    background: {_nav_hover_bg} !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    color: {_nav_sel_color} !important;
    background: {_nav_sel_bg} !important;
    border-left-color: {_tab_sel_border} !important;
}}

/* ── Hide radio widget label ── */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{ display: none !important; }}

/* ── Sidebar selectboxes (lang/theme) ── */
[data-testid="stSidebar"] [data-testid="stSelectbox"] {{ margin-bottom: -8px !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{
    background: {_bg3} !important;
    border: 1px solid {_border} !important;
    border-radius: 7px !important;
    min-height: 32px !important;
    padding: 2px 8px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    color: {_text2} !important;
    font-family: 'Nunito Sans', sans-serif !important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] > div:hover {{
    border-color: {_sb_select_hover_bd} !important;
}}

/* ── Sidebar helpers ── */
.sb-divider {{ height: 1px; background: {_border}; margin: 6px 14px; }}
.sb-group-label {{
    font-size: 8px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: {_text3}; padding: 10px 14px 4px;
    font-family: 'Nunito Sans', sans-serif;
}}

/* ── Responsive ── */
@media (max-width: 1024px) {{
    .block-container {{
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }}
}}
@media (max-width: 768px) {{
    [data-testid="column"] {{
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }}
    .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}
    [data-testid="stSidebar"] {{
        min-width: 220px !important;
        max-width: 220px !important;
    }}
    h1 {{ font-size: 1.5rem !important; }}
    h2 {{ font-size: 1.25rem !important; }}
    h3 {{ font-size: 1.1rem !important; }}
    h4 {{ font-size: 1rem !important; }}
}}
@media (max-width: 480px) {{
    .block-container {{
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }}
    [data-testid="stSidebar"] {{
        min-width: 180px !important;
        max-width: 180px !important;
    }}
}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# NexusBI SIDEBAR — Branding + Lang + Theme
# ─────────────────────────────────────────────

# Lang & theme already initialized above (THEME & LANG STATE block)

L = st.session_state.lang

# ── Brand Header ──
_user_display = _auth_user.get("name") or _auth_user.get("email", "")
st.sidebar.markdown(
    f'<div style="display:flex;align-items:center;gap:8px;padding:12px 0 4px">'
    f'<div style="width:28px;height:28px;background:{_brand_box};border-radius:7px;display:flex;'
    f'align-items:center;justify-content:center;font-size:12px;font-weight:800;color:#0b0e1a;'
    f'flex-shrink:0;font-family:DM Mono,monospace">LS</div>'
    f'<div style="font-size:12px;font-weight:800;color:{_brand_sidebar_title};line-height:1.2;'
    f'font-family:Nunito Sans,sans-serif">LATAMSELLERS<br>'
    f'<span style="font-size:9px;font-weight:600;color:{_brand_finance};letter-spacing:1px">FINANCE</span></div>'
    f'</div>'
    f'<div style="font-size:10px;color:#6272a4;padding:2px 0 8px">{_user_display}</div>',
    unsafe_allow_html=True,
)
if st.sidebar.button("Sair / Выйти", key="logout_btn", use_container_width=True):
    st.session_state.pop("auth_user", None)
    st.rerun()


# ── Functional lang & theme selectors (styled as small pills) ──
_lc1, _lc2 = st.sidebar.columns(2)
with _lc1:
    _lang_val = st.selectbox(
        "🌐", ["ru", "pt"],
        index=0 if st.session_state.lang == "ru" else 1,
        key="sb_lang_sel", label_visibility="collapsed",
        format_func=lambda x: "🇷🇺 RU" if x == "ru" else "🇧🇷 BR",
    )
    if _lang_val != st.session_state.lang:
        st.session_state.lang = _lang_val
        st.query_params["lang"] = _lang_val
        st.rerun()
with _lc2:
    _theme_val = st.selectbox(
        "🎨", ["night", "day"],
        index=0 if st.session_state.theme == "night" else 1,
        key="sb_theme_sel", label_visibility="collapsed",
        format_func=lambda x: t("theme_night", L) if x == "night" else t("theme_day", L),
    )
    if _theme_val != st.session_state.theme:
        st.session_state.theme = _theme_val
        st.query_params["theme"] = _theme_val
        st.rerun()

L = st.session_state.lang

# ── Sidebar divider ──
st.sidebar.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def extract_date_range(file_path: Path) -> tuple[str, str] | None:
    """Try to find the data date range inside a file (CSV/Excel)."""
    try:
        ext = file_path.suffix.lower()
        df = None
        if ext == ".csv":
            for skip in [0, 5, 8, 10]:
                for sep in [";", ",", "\t"]:
                    try:
                        df = pd.read_csv(file_path, sep=sep, skiprows=skip, encoding="utf-8")
                        if df is not None and len(df.columns) > 2:
                            break
                    except Exception:
                        continue
                if df is not None and len(df.columns) > 2:
                    break
        elif ext in (".xlsx", ".xls"):
            try:
                df = pd.read_excel(file_path)
            except Exception:
                return None
        else:
            return None

        if df is None or len(df) == 0:
            return None

        date_cols = [c for c in df.columns if any(k in str(c).lower() for k in
                     ["data", "date", "fecha", "lançamento", "lancamento", "created", "approved"])]
        if not date_cols:
            return None

        for col in date_cols:
            try:
                dates = pd.to_datetime(df[col], dayfirst=True, errors="coerce").dropna()
                if len(dates) > 0:
                    return (dates.min().strftime("%d/%m/%Y"), dates.max().strftime("%d/%m/%Y"))
            except Exception:
                continue
        return None
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def get_loaded_files(month: str) -> dict:
    month_dir = DATA_DIR / month
    result = {}
    if not month_dir.exists():
        for src_id in DATA_SOURCES:
            result[src_id] = None
        return result
    files_in_dir = list(month_dir.iterdir())
    for src_id, src in DATA_SOURCES.items():
        matched = [f for f in files_in_dir if f.name.startswith(src_id) and f.is_file()]
        if matched:
            newest = max(matched, key=lambda f: f.stat().st_mtime)
            date_range = extract_date_range(newest)
            result[src_id] = {
                "file": newest.name,
                "size": newest.stat().st_size,
                "date": datetime.fromtimestamp(newest.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "date_min": date_range[0] if date_range else None,
                "date_max": date_range[1] if date_range else None,
            }
        else:
            result[src_id] = None
    return result


def auto_detect_source(df: pd.DataFrame, filename: str) -> str | None:
    cols = set(c.strip().lower() for c in df.columns)
    fname = filename.lower()

    # Helper: check if any column CONTAINS the substring
    def has_col(substring):
        return any(substring in c for c in cols)

    if has_col("net_received_amount") or has_col("transaction_amount"):
        return "collection_mp"
    if has_col("# de anúncio") or has_col("# de anuncio"):
        return "vendas_ml"
    if has_col("investimento") and (has_col("acos") or has_col("roas")):
        return "ads_publicidade"
    if has_col("tarifa por unidade"):
        return "armazenagem_full"
    if has_col("amount_refunded") and has_col("shipment_status"):
        return "after_collection"
    if has_col("identificador") and has_col("descrição"):
        return "extrato_nubank"
    # Mercado Pago extrato (account_statement)
    if "release_date" in cols or "transaction_net_amount" in cols or "partial_balance" in cols:
        return "extrato_mp"
    if "initial_balance" in cols and "final_balance" in cols:
        return "extrato_mp"
    # C6 Bank CSV detection by columns
    if "data lançamento" in cols or "data lancamento" in cols:
        if any("r$" in c for c in cols):
            return "extrato_c6_brl"
        if any("us$" in c or "usd" in c for c in cols):
            return "extrato_c6_usd"
        return "extrato_c6_brl"

    if "collection" in fname:
        return "collection_mp"
    if "account_statement" in fname:
        return "extrato_mp"
    if "vendas" in fname and "mercado" in fname:
        return "vendas_ml"
    if "anuncios" in fname or "patrocinados" in fname:
        return "ads_publicidade"
    if "armazenamento" in fname or "armazenagem" in fname:
        return "armazenagem_full"
    if "stock_general" in fname or "stock_full" in fname or fname.startswith("stock"):
        return "stock_full"
    if "after_collection" in fname or "pos" in fname:
        return "after_collection"
    if "fatura" in fname or "faturamento" in fname:
        return "fatura_ml"
    if "extrato" in fname and "nubank" in fname:
        return "extrato_nubank"
    # C6 Bank — detect by filename patterns
    if "c6" in fname:
        if "usd" in fname or "global_usd" in fname or "conta_global_usd" in fname:
            return "extrato_c6_usd"
        if "brl" in fname or "global_brl" in fname or "conta_global_brl" in fname:
            return "extrato_c6_brl"
        if "data lançamento" in cols or "data lancamento" in cols:
            if "entrada(r$)" in cols:
                return "extrato_c6_brl"
            if "entrada(us$)" in cols or "entrada($)" in cols:
                return "extrato_c6_usd"
        if fname.startswith("01k") or "conta_global" in fname:
            return "extrato_c6_brl"
        return "extrato_c6_brl"

    # C6 export hash filename (01K...) — even without "c6" in name
    if fname.startswith("01k") and (fname.endswith(".csv") or fname.endswith(".pdf")):
        return "extrato_c6_brl"
    if "trafficstars" in fname or "traffic" in fname:
        return "trafficstars"
    if "bybit" in fname:
        return "bybit_history"
    # DAS Simples Nacional PDF
    if "pgdasd" in fname or "das-" in fname or ("das" in fname and "simples" in fname):
        return "das_simples"
    # NFS-e (Nota Fiscal de Serviço)
    if "nfs" in fname or "nfse" in fname or fname.startswith("nf "):
        return "nfse_shps"
    return None


def try_read_csv(file_bytes: bytes, nrows: int = 5) -> pd.DataFrame | None:
    """Try to read CSV with different separators."""
    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, nrows=nrows, encoding="utf-8")
            if len(df.columns) > 2:
                return df
        except Exception:
            continue
    return None


def preview_file(file_bytes: bytes, filename: str):
    """Show preview of first 5 rows."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            df = try_read_csv(file_bytes, nrows=5)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes), nrows=5)
        else:
            return
        if df is not None and len(df) > 0:
            st.markdown(f"**Preview** ({len(df.columns)} columns, {len(df)} rows):")
            st.dataframe(df, width="stretch", hide_index=True)
    except Exception:
        pass


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

def render_project_tasks(project_data: dict):
    """Render pending tasks for a project (data needed)."""
    _lg = current_lang()
    tasks = project_data.get("tasks", [])
    if not tasks:
        return
    pending = [task for task in tasks if not task.get("done")]
    if not pending:
        return

    st.markdown(f"#### 📝 {t('proj_tasks_title', _lg)}")
    for task in pending:
        prio = task.get("priority", "medium")
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(prio, "•")
        st.markdown(f"- {icon} **{task['title']}**")
        if task.get("note"):
            st.caption(f"   ↳ {task['note']}")


def render_live_updates_block(project_id: str, after_date: str | None = None):
    """Render live updates from classified bank statements for any project."""
    from reports import aggregate_classified_by_project

    _lg = current_lang()
    live_data = aggregate_classified_by_project(project_id, after_date=after_date)
    if live_data["inflows"] == 0 and live_data["outflows"] == 0 and not live_data["transactions"]:
        return  # nothing to show

    st.markdown(f"#### 🔄 {t('live_bank_updates', _lg)}")
    if after_date:
        st.caption(t("live_tx_after", _lg).format(d=after_date))

    new_in = live_data["inflows"]
    new_out = live_data["outflows"]
    net = new_in - new_out

    col1, col2, col3 = st.columns(3)
    col1.metric(t("metric_inflows", _lg), f"R$ {new_in:,.2f}")
    col2.metric(t("metric_outflows", _lg), f"R$ -{new_out:,.2f}")
    col3.metric(t("metric_net", _lg), f"R$ {net:,.2f}")

    if live_data["by_category"]:
        with st.expander(f"📊 {t('expander_by_category', _lg)}"):
            cat_rows = [{t("col_category_short", _lg): k, "R$": v} for k, v in sorted(live_data["by_category"].items(), key=lambda x: abs(x[1]), reverse=True)]
            st.dataframe(
                pd.DataFrame(cat_rows),
                width="stretch",
                hide_index=True,
                column_config={"R$": st.column_config.NumberColumn("R$", format="R$ %.2f")},
            )

    if live_data["transactions"]:
        with st.expander(t("expander_transactions_n", _lg).format(n=len(live_data["transactions"]))):
            tx_df = pd.DataFrame(live_data["transactions"])
            cols_show = [c for c in ["Data", "Valor", "Descrição", "Категория", "Класс."] if c in tx_df.columns]
            st.dataframe(tx_df[cols_show], width="stretch", hide_index=True)


def render_rental_section(project_data: dict):
    """Render rental info for any project that has rental config."""
    rental = project_data.get("rental")
    if not rental:
        return

    _lg = current_lang()
    rate = rental.get("rate_usd", 0)
    period = rental.get("period", "quarter")
    paid = rental.get("total_paid_usd", 0)
    pending = rental.get("total_pending_usd", 0)
    payments = rental.get("payments", [])

    _per = t("rental_period_quarter", _lg) if period == "quarter" else t("rental_period_month", _lg)
    st.markdown(
        f"#### {t('rental_company_title', _lg).replace('{rate}', str(rate)).replace('{period}', _per)}"
    )

    if payments:
        rows = []
        for i, p in enumerate(payments, 1):
            status_icon = "✅" if p.get("status") == "paid" else "🔴"
            rows.append(f"| {i} | {p.get('date', '—')} | ${p.get('usd', 0)} | {p.get('quarter', p.get('note', ''))} | {status_icon} {p.get('status', '')} |")

        st.markdown(t("rental_table_header", _lg) + "\n" + "\n".join(rows))

    # Show pending payments
    if pending > 0:
        st.markdown(f"\n🔴 **{t('rental_debt', _lg)}: ${pending}**")

    st.markdown(
        f"✅ **{t('rental_paid', _lg)}: ${paid}** | {t('rental_total', _lg)}: ${paid + pending}"
    )

    # Next due dates
    due_dates = rental.get("due_dates", [])
    from datetime import date
    today = date.today().isoformat()
    future = [d for d in due_dates if d > today]
    if future:
        st.markdown(f"**{t('rental_next_payments', _lg)}**")
        for d in future[:4]:
            st.markdown(f"- {d} → ${rate}")


# ── Navigation with group labels + badges ──
st.sidebar.markdown(
    f'<div class="sb-group-label">{t("sidebar_group_main", L)}</div>',
    unsafe_allow_html=True,
)
page_options = [
    t("page_dashboard", L),
    t("page_upload", L),
    t("page_classify", L),
    t("page_reports", L),
    t("page_bank_rules", L),
    t("page_sku", L),
    t("page_projects", L),
]
page = st.sidebar.radio(
    t("menu", L), page_options, label_visibility="collapsed",
)

# ── Inject divider "НАСТРОЙКИ" + badges via CSS ──
_cfg_label = t("sidebar_settings", L)
st.sidebar.markdown(f"""<style>
[data-testid="stSidebar"] [role="radiogroup"] > label {{
    position: relative !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] > label:nth-child(5) {{
    margin-top: 28px !important;
    border-top: 1px solid {_border} !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] > label:nth-child(5)::before {{
    content: '{_cfg_label}';
    position: absolute; left: 14px; top: -22px;
    font-size: 8px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: {_text3};
    font-family: 'Nunito Sans', sans-serif;
    pointer-events: none;
}}
</style>""", unsafe_allow_html=True)


def _nx_projects_page_css(
    bg: str, bg2: str, bg3: str, border: str, text: str, text2: str, text3: str,
    yellow: str, green: str, red: str, blue: str, purple: str, amber: str,
    ydim: str,
) -> str:
    return f"""
<style>
.nx-proj-root {{ font-family: 'Nunito Sans', sans-serif; margin-bottom: 8px; }}

/* ── Hero header ── */
.nx-proj-hero {{
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    margin-bottom: 6px; padding: 16px 18px; background: {bg2};
    border: 1px solid {border}; border-radius: 12px;
}}
.nx-proj-hero-icon {{
    width: 40px; height: 40px; background: {ydim};
    border: 1px solid rgba(255,213,0,0.22); border-radius: 10px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}}
.nx-proj-hero-icon svg {{ width: 22px; height: 22px; color: {yellow}; }}
.nx-proj-hero-titles {{ flex: 1; min-width: 200px; }}
.nx-proj-title {{ font-size: 1.45rem; font-weight: 800; color: {text}; margin: 0; line-height: 1.2; }}
.nx-proj-sub {{ font-size: 11px; font-weight: 600; color: {text2}; margin-top: 4px; }}
.nx-proj-divider {{
    height: 1px; margin: 14px 0 18px;
    background: linear-gradient(90deg, {yellow} 0%, rgba(255,213,0,0.15) 40%, transparent 100%);
}}

/* ── Stats bar ── */
.nx-stats-bar {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
.nx-stat-card {{
    background: {bg2}; border: 1px solid {border}; border-radius: 10px;
    padding: 14px 16px; position: relative; overflow: hidden;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.nx-stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
.nx-stat-card::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 10px 10px 0 0;
}}
.nx-stat-card:nth-child(1)::before {{ background: {yellow}; }}
.nx-stat-card:nth-child(2)::before {{ background: {blue}; }}
.nx-stat-card:nth-child(3)::before {{ background: {green}; }}
.nx-stat-card:nth-child(4)::before {{ background: {amber}; }}
.nx-stat-lbl {{ font-size: 8px; color: {text3}; text-transform: uppercase; letter-spacing: .8px; font-weight: 700; margin-bottom: 8px; }}
.nx-stat-val {{ font-size: 22px; font-weight: 800; font-family: 'DM Mono', monospace; line-height: 1; color: {text}; }}
.nx-stat-detail {{ font-size: 10px; color: {text2}; margin-top: 6px; }}
.nx-stat-dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

/* ── Section label ── */
.nx-proj-section {{
    display: flex; align-items: center; gap: 10px; margin: 18px 0 12px;
    font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: {text2};
}}
.nx-proj-section::after {{ content: ''; flex: 1; height: 1px; background: {border}; }}
.nx-sec-count {{
    background: {ydim}; border: 1px solid rgba(255,213,0,0.22);
    color: {yellow}; font-size: 9px; font-weight: 800; padding: 2px 8px;
    border-radius: 10px; font-family: 'DM Mono', monospace;
}}

/* ── Project card ── */
.nx-proj-card {{
    background: {bg2}; border: 1px solid {border}; border-radius: 10px;
    padding: 16px 18px; position: relative; overflow: hidden; margin-bottom: 10px;
    border-left: 3px solid {yellow};
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.nx-proj-card:hover {{ transform: translateY(-1px); box-shadow: 0 6px 24px rgba(0,0,0,0.25); }}

/* ── Card header row ── */
.nx-proj-card-header {{
    display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
}}
.nx-proj-dot {{
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}}
.nx-proj-pid {{
    font-size: 15px; font-weight: 800; letter-spacing: .3px; margin-right: 4px;
}}
.nx-proj-chips {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.nx-proj-chip {{
    display: inline-block; padding: 3px 10px; border-radius: 5px; font-size: 9px; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.5px;
}}
.nx-proj-chip-type-ecom {{ background: rgba(56,189,248,0.14); color: {blue}; border: 1px solid rgba(56,189,248,0.35); }}
.nx-proj-chip-type-services {{ background: rgba(167,139,250,0.12); color: {purple}; border: 1px solid rgba(167,139,250,0.3); }}
.nx-proj-chip-type-hybrid {{ background: {ydim}; color: {yellow}; border: 1px solid rgba(255,213,0,0.35); }}
.nx-proj-chip-type-default {{ background: {bg3}; color: {text2}; border: 1px solid {border}; }}
.nx-proj-chip-st-pending {{ background: rgba(245,158,11,0.12); color: {amber}; border: 1px solid rgba(245,158,11,0.35); }}
.nx-proj-chip-st-approved {{ background: rgba(34,211,165,0.12); color: {green}; border: 1px solid rgba(34,211,165,0.35); }}
.nx-proj-comp-pill {{
    font-size: 9px; font-weight: 600; font-family: 'DM Mono', monospace;
    padding: 3px 8px; border-radius: 4px; border: 1px solid; margin-left: auto;
}}
.nx-comp-rental {{ background: rgba(245,158,11,0.08); color: {amber}; border-color: rgba(245,158,11,0.2); }}
.nx-comp-ps {{ background: rgba(167,139,250,0.08); color: {purple}; border-color: rgba(167,139,250,0.2); }}

/* ── Timeline ── */
.nx-timeline {{ margin-bottom: 14px; }}
.nx-timeline-header {{
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;
}}
.nx-timeline-lbl {{
    font-size: 8px; color: {text3}; text-transform: uppercase; letter-spacing: .7px; font-weight: 700;
}}
.nx-timeline-pct {{ font-family: 'DM Mono', monospace; color: {yellow}; font-size: 10px; font-weight: 700; }}
.nx-timeline-track {{
    width: 100%; height: 5px; background: {bg3}; border-radius: 3px;
    position: relative; overflow: visible;
}}
.nx-timeline-fill {{ height: 100%; border-radius: 3px; }}
.nx-timeline-marker {{
    position: absolute; top: 50%; width: 11px; height: 11px;
    border-radius: 50%; background: {yellow};
    border: 2px solid {bg2}; transform: translate(-50%, -50%);
    box-shadow: 0 0 8px rgba(255,213,0,0.5); z-index: 2;
}}
.nx-timeline-dates {{
    display: flex; justify-content: space-between; margin-top: 5px;
    font-size: 9px; font-family: 'DM Mono', monospace; color: {text3};
}}

/* ── KPI row ── */
.nx-proj-kpi-row {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px; }}
.nx-proj-kpi {{
    background: {bg3}; border: 1px solid {border}; border-radius: 8px; padding: 10px 12px;
    transition: border-color 0.15s ease;
}}
.nx-proj-kpi:hover {{ border-color: rgba(255,255,255,0.08); }}
.nx-proj-kpi-lbl {{
    font-size: 8px; font-weight: 700; color: {text2}; text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 5px; display: flex; align-items: center; gap: 5px;
}}
.nx-proj-kpi-lbl svg {{ width: 10px; height: 10px; opacity: .5; }}
.nx-proj-kpi-val {{ font-size: 18px; font-weight: 800; font-family: 'DM Mono', monospace; color: {text}; line-height: 1.1; }}
.nx-proj-kpi-sub {{ font-size: 10px; color: {text3}; margin-top: 4px; font-family: 'DM Mono', monospace; }}

/* ── Detail list ── */
.nx-proj-dl {{ display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; font-size: 11px; max-width: 100%; }}
.nx-proj-dl dt {{ color: {text3}; font-weight: 700; text-transform: uppercase; font-size: 9px; letter-spacing: 0.5px; margin: 0; }}
.nx-proj-dl dd {{ color: {text2}; margin: 0; word-break: break-word; }}
.nx-proj-dl code {{ font-family: 'DM Mono', monospace; font-size: 10px; color: {text}; background: {bg3}; padding: 2px 6px; border-radius: 4px; }}

/* ── Tags ── */
.nx-proj-tags-section {{ margin-bottom: 8px; }}
.nx-proj-tags-label {{ font-size: 9px; color: {text3}; text-transform: uppercase; letter-spacing: .7px; font-weight: 700; margin-bottom: 6px; }}
.nx-proj-tag {{
    display: inline-block; background: {bg3}; border: 1px solid {border};
    border-radius: 5px; font-size: 9px; font-family: 'DM Mono', monospace;
    padding: 3px 8px; color: {text2}; margin: 0 4px 4px 0;
}}
.nx-proj-tag-blue {{ border-color: rgba(56,189,248,0.25); color: {blue}; }}

/* ── Banners ── */
.nx-proj-banner {{ border-radius: 8px; padding: 10px 12px; margin-top: 10px; font-size: 11px; font-weight: 600; }}
.nx-proj-banner-warn {{ background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); color: {amber}; }}
.nx-proj-banner-info {{ background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.2); color: {blue}; }}
.nx-proj-banner-err {{ background: rgba(255,87,87,0.1); border: 1px solid rgba(255,87,87,0.28); color: {red}; }}
.nx-proj-foot {{ font-size: 10px; color: {text3}; margin-top: 10px; font-weight: 600; }}
.nx-proj-caption {{ font-size: 11px; color: {text3}; margin-bottom: 10px; }}

/* ── Expander overrides ── */
div[data-testid="stExpander"] details > summary {{
    font-family: 'Nunito Sans', sans-serif !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    color: {text} !important;
}}
div[data-testid="stExpander"] form[data-testid="stForm"] {{
    background: {bg3} !important;
    border: 1px solid {border} !important;
    border-radius: 10px !important;
    padding: 14px 16px !important;
    margin-top: 10px !important;
}}
div[data-testid="stExpander"] form[data-testid="stForm"] button[kind="secondary"] {{
    border: 1px solid rgba(255,213,0,0.45) !important;
    color: {text2} !important;
    background: transparent !important;
}}
div[data-testid="stExpander"] form[data-testid="stForm"] button[kind="secondary"]:hover {{
    border-color: {yellow} !important;
    color: {yellow} !important;
    background: {ydim} !important;
}}

/* ── Edit mode header ── */
.nx-edit-header {{
    padding: 8px 0; margin-bottom: 8px;
    border-bottom: 1px solid rgba(255,213,0,0.1);
    display: flex; align-items: center; gap: 6px;
}}
.nx-edit-header-label {{
    font-size: 9px; font-weight: 800; color: {yellow};
    text-transform: uppercase; letter-spacing: .8px;
}}
</style>
"""


def _parse_project_date(val) -> date | None:
    """Дата из JSON (строка YYYY-MM-DD) или date для st.date_input."""
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _parse_report_period_bounds(s) -> tuple[date | None, date | None]:
    """Две даты из `report_period`: «YYYY-MM-DD / YYYY-MM-DD» или одна дата."""
    if not s or not str(s).strip():
        return None, None
    raw = str(s).strip()
    if "/" not in raw:
        d0 = _parse_project_date(raw)
        return d0, d0
    left, _, right = raw.partition("/")
    left, right = left.strip(), right.strip()
    d1 = _parse_project_date(left[:10] if len(left) >= 10 else left)
    d2 = _parse_project_date(right[:10] if len(right) >= 10 else right)
    return d1, d2


def _nx_proj_type_chip_class(raw_type: str) -> str:
    k = (raw_type or "").lower().strip()
    if k == "ecom":
        return "nx-proj-chip-type-ecom"
    if k == "services":
        return "nx-proj-chip-type-services"
    if k == "hybrid":
        return "nx-proj-chip-type-hybrid"
    return "nx-proj-chip-type-default"


def _nx_proj_status_chip_class(st: str) -> str:
    return "nx-proj-chip-st-approved" if (st or "").lower() == "approved" else "nx-proj-chip-st-pending"


def _nx_proj_summary_html(pid: str, pdata: dict, L: str) -> str:
    """Nexus-стиль карточка просмотра проекта (только безопасный HTML)."""
    from dashboard_charts import PROJECT_COLORS, C as _C
    proj_color = PROJECT_COLORS.get(pid, _C.get("yellow", "#FFD500"))

    ptype_raw = pdata.get("type") or "ecom"
    ptype = (ptype_raw or "—").upper()
    desc = html_escape.escape(str(pdata.get("description") or ""))
    status = str(pdata.get("status") or "pending")
    skus = pdata.get("sku_prefixes") or []
    mlbs = pdata.get("mlb_fallback") or []
    cmode = get_compensation_mode(pdata)
    rental = pdata.get("rental") if isinstance(pdata.get("rental"), dict) else None

    # ── Header row: dot + name + chips + comp pill ──
    chips = (
        f'<span class="nx-proj-chip {_nx_proj_type_chip_class(ptype_raw)}">{html_escape.escape(ptype)}</span>'
        f'<span class="nx-proj-chip {_nx_proj_status_chip_class(status)}">'
        f'{html_escape.escape(status)}</span>'
    )
    comp_pill = ""
    if cmode == "rental":
        rate = 0
        per = "month"
        if rental:
            rate = rental.get("rate_usd", 0) or 0
            per = rental.get("period") or "month"
        comp_pill = f'<span class="nx-proj-comp-pill nx-comp-rental">${rate:,.0f}/{html_escape.escape(str(per))}</span>'
    else:
        pct = pdata.get("profit_share_pct")
        comp_pill = f'<span class="nx-proj-comp-pill nx-comp-ps">{html_escape.escape(str(pct or 0))}%</span>'

    header_html = f"""
    <div class="nx-proj-card-header">
      <div class="nx-proj-dot" style="background:{proj_color};box-shadow:0 0 8px {proj_color}"></div>
      <span class="nx-proj-pid" style="color:{proj_color}">{html_escape.escape(pid)}</span>
      <div class="nx-proj-chips">{chips}</div>
      {comp_pill}
    </div>"""

    # ── Description ──
    desc_html = f'<div style="font-size:11px;color:{_C.get("text2","#a8b2d1")};margin-bottom:12px">{desc}</div>' if desc else ""

    # ── Timeline ──
    timeline_html = ""
    rp_a, rp_b = _parse_report_period_bounds(pdata.get("report_period"))
    nc_d = _parse_project_date(pdata.get("next_close"))
    t_from = rp_a
    t_to = nc_d or rp_b
    if t_from and t_to:
        today = date.today()
        total_days = (t_to - t_from).days or 1
        elapsed = (today - t_from).days
        pct = max(0, min(100, round(elapsed / total_days * 100)))
        timeline_html = f"""
    <div class="nx-timeline">
      <div class="nx-timeline-header">
        <span class="nx-timeline-lbl">{html_escape.escape(t("project_report_period_label", L) if t("project_report_period_label", L) else "Текущий период")}</span>
        <span class="nx-timeline-pct">{pct}%</span>
      </div>
      <div class="nx-timeline-track">
        <div class="nx-timeline-fill" style="width:{pct}%;background:{proj_color}"></div>
        <div class="nx-timeline-marker" style="left:{pct}%"></div>
      </div>
      <div class="nx-timeline-dates">
        <span>{html_escape.escape(t_from.isoformat())}</span>
        <span>{html_escape.escape(t_to.isoformat())}</span>
      </div>
    </div>"""

    # ── KPIs ──
    kpi_html = ""
    banner_html = ""

    if cmode == "rental":
        if rental:
            paid = rental.get("total_paid_usd", 0) or 0
            pending_usd = rental.get("total_pending_usd", 0) or 0
            rate = rental.get("rate_usd", 0) or 0
            per = html_escape.escape(str(rental.get("period") or "quarter"))
            npd_kpi = _parse_project_date(rental.get("next_payment_date"))
            pay_cell = ""
            if npd_kpi:
                pay_cell = f"""
  <div class="nx-proj-kpi">
    <div class="nx-proj-kpi-lbl">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      {html_escape.escape(t("rental_next_payment_date_label", L))}
    </div>
    <div class="nx-proj-kpi-val" style="font-size:15px">{html_escape.escape(npd_kpi.strftime("%d.%m.%Y"))}</div>
  </div>"""
            kpi_html = f"""
<div class="nx-proj-kpi-row">
  <div class="nx-proj-kpi">
    <div class="nx-proj-kpi-lbl">{html_escape.escape(t("compensation_rental_rates", L))}</div>
    <div class="nx-proj-kpi-val">${rate:,.0f}<span style="font-size:12px;font-weight:700">/{per}</span></div>
  </div>
  <div class="nx-proj-kpi">
    <div class="nx-proj-kpi-lbl">{html_escape.escape(t("compensation_rental_paid", L))}</div>
    <div class="nx-proj-kpi-val">${paid:,}</div>
  </div>
  <div class="nx-proj-kpi">
    <div class="nx-proj-kpi-lbl">{html_escape.escape(t("compensation_rental_pending", L))}</div>
    <div class="nx-proj-kpi-val">${pending_usd:,}</div>
  </div>{pay_cell}
</div>"""
        else:
            banner_html = (
                f'<div class="nx-proj-banner nx-proj-banner-info">'
                f'{html_escape.escape(t("compensation_rental_add_json", L))}</div>'
            )
    elif cmode == "profit_share":
        pct_val = pdata.get("profit_share_pct")
        legacy_fee = pdata.get("fixed_fee_usd")
        if pct_val is not None:
            kpi_html = f"""
<div class="nx-proj-kpi-row">
  <div class="nx-proj-kpi">
    <div class="nx-proj-kpi-lbl">{html_escape.escape(t("profit_share_pct_label", L))}</div>
    <div class="nx-proj-kpi-val">{html_escape.escape(str(pct_val))}%</div>
  </div>
</div>"""
            if rental:
                banner_html = (
                    f'<div class="nx-proj-banner nx-proj-banner-warn">'
                    f'{html_escape.escape(t("compensation_profit_share_but_rental_json", L))}</div>'
                )
            else:
                banner_html = (
                    f'<p class="nx-proj-foot">{html_escape.escape(t("compensation_profit_share_ok", L))}</p>'
                )
        elif legacy_fee is not None:
            banner_html = (
                f'<div class="nx-proj-banner nx-proj-banner-warn">'
                f'{html_escape.escape(t("compensation_legacy_usd_fee_note", L))}</div>'
            )
        else:
            banner_html = (
                f'<div class="nx-proj-banner nx-proj-banner-warn">'
                f'{html_escape.escape(t("compensation_profit_share_missing", L))}</div>'
            )

    # ── Meta KPIs (launch, period, last report, next close) ──
    meta_cells = []
    ld_show = _parse_project_date(pdata.get("launch_date"))
    if ld_show:
        meta_cells.append(
            f'<div class="nx-proj-kpi"><div class="nx-proj-kpi-lbl">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
            f' {html_escape.escape(t("project_launch_date_label", L))}</div>'
            f'<div class="nx-proj-kpi-val" style="font-size:14px">{html_escape.escape(ld_show.strftime("%d.%m.%Y"))}</div></div>'
        )
    if pdata.get("last_report"):
        meta_cells.append(
            f'<div class="nx-proj-kpi"><div class="nx-proj-kpi-lbl">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
            f' {html_escape.escape(t("project_last_report_label", L))}</div>'
            f'<div class="nx-proj-kpi-val" style="font-size:14px">{html_escape.escape(str(pdata["last_report"]))}</div></div>'
        )
    if pdata.get("next_close"):
        meta_cells.append(
            f'<div class="nx-proj-kpi"><div class="nx-proj-kpi-lbl">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
            f' {html_escape.escape(t("project_next_close_label", L))}</div>'
            f'<div class="nx-proj-kpi-val" style="font-size:14px">{html_escape.escape(str(pdata["next_close"]))}</div></div>'
        )
    meta_html = ""
    if meta_cells:
        meta_html = '<div class="nx-proj-kpi-row">' + "".join(meta_cells) + '</div>'

    # ── Tags (SKU + MLB) ──
    tags_html = ""
    if skus:
        sku_tags = "".join(f'<span class="nx-proj-tag">{html_escape.escape(s)}</span>' for s in skus)
        tags_html += f'<div class="nx-proj-tags-section"><div class="nx-proj-tags-label">SKU</div>{sku_tags}</div>'
    if mlbs:
        mlb_tags = "".join(f'<span class="nx-proj-tag nx-proj-tag-blue">{html_escape.escape(m)}</span>' for m in mlbs)
        tags_html += f'<div class="nx-proj-tags-section"><div class="nx-proj-tags-label">MLB</div>{mlb_tags}</div>'

    return f"""
<div class="nx-proj-card" style="border-left-color:{proj_color}">
  {header_html}
  {desc_html}
  {timeline_html}
  {kpi_html}
  {meta_html}
  {tags_html}
  {banner_html}
</div>
"""


# ─────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────

if page == t("page_dashboard", L):
    from dashboard_charts import (
        render_kpi_header, section_header, fmt_brl, fmt_number,
        chart_project_breakdown, chart_monthly_trend, chart_sales_bars,
        render_data_freshness_table, render_wallet_cards, render_expenses_table,
        render_banners, render_bank_cards,
    )
    from finance import compute_cashflow
    from reports import (
        calculate_trafficstars_fifo,
        get_armazenagem_by_period,
        get_collection_mp_credited_by_period,
    )

    # ── Pending classification warnings (кэш по отпечатку JSON) ──
    pending_files = _cached_dashboard_pending_classification(_classification_json_fingerprint(), L)

    # ══════════════════════════════════════════════
    # GENERATE DATA
    # ══════════════════════════════════════════════
    opiu = _cached_generate_opiu_from_vendas()
    ecom_projects = [pid for pid, p in PROJECTS.items() if p.get("type") == "ecom"]

    # ══════════════════════════════════════════════
    # AGGREGATE DATA (build_monthly_pnl_matrix — real monthly dates)
    # ══════════════════════════════════════════════
    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_pnl_matrix(project: str):
        from reports import build_monthly_pnl_matrix

        return build_monthly_pnl_matrix(project)

    all_months_set = set()
    pnl_matrices = {}
    project_net = {}
    monthly_rev = {}
    monthly_vendas_map = {}
    monthly_ads_map = {}

    for p in ecom_projects:
        mat = _cached_pnl_matrix(p)
        if not mat.get("months"):
            continue
        pnl_matrices[p] = mat
        all_months_set.update(mat["months"])

        net_row = next((r for r in mat["rows"]
                        if "NET" in r.get("label", "") and r.get("section") == "ВЫРУЧКА"), None)
        p_total_net = 0.0
        if net_row:
            monthly_rev[p] = {}
            for mk, v in net_row["values"].items():
                monthly_rev[p][mk] = v
                p_total_net += v
        if p_total_net > 0:
            project_net[p] = p_total_net

        vendas_row = next((r for r in mat["rows"]
                           if any(k in r.get("label", "").lower()
                                  for k in ("доставлено", "delivered", "vendas"))), None)
        if vendas_row:
            for mk, v in vendas_row["values"].items():
                monthly_vendas_map[mk] = monthly_vendas_map.get(mk, 0) + int(v)

        ads_row = next((r for r in mat["rows"]
                        if any(k in r.get("label", "").lower()
                               for k in ("рекламн", "publicidade", "ads"))), None)
        if ads_row:
            for mk, v in ads_row["values"].items():
                monthly_ads_map[mk] = monthly_ads_map.get(mk, 0) + int(v)

    months_sorted = sorted(all_months_set)

    if not monthly_vendas_map:
        for p in ecom_projects:
            if p in opiu:
                for mk, bm in opiu[p].get("by_month", {}).items():
                    monthly_vendas_map[mk] = monthly_vendas_map.get(mk, 0) + bm.get("vendas", 0)

    monthly_net_list = [sum(monthly_rev.get(p, {}).get(mk, 0) for p in ecom_projects) for mk in months_sorted]
    monthly_vendas_list = [monthly_vendas_map.get(mk, 0) for mk in months_sorted]
    monthly_rev_lists = {p: [monthly_rev[p].get(mk, 0) for mk in months_sorted] for p in monthly_rev}

    total_net = sum(project_net.values())
    total_vendas = sum(monthly_vendas_list)
    total_ads = sum(monthly_ads_map.values())
    if total_ads == 0:
        total_ads = sum(opiu.get(p, {}).get("ads_count", 0) for p in ecom_projects if p in opiu)
    ads_pct = ((total_ads / total_vendas) * 100) if total_vendas > 0 else 0
    # Строка P&L с «ads» может быть в R$ (расход), а не в шт. заказов — доля тогда бессмысленна
    if ads_pct > 100 or ads_pct < 0:
        total_ads_units = sum(
            opiu.get(p, {}).get("ads_count", 0) for p in ecom_projects if p in opiu
        )
        ads_pct = (
            (total_ads_units / total_vendas) * 100
            if total_vendas > 0 and total_ads_units >= 0
            else 0
        )

    has_data = total_net > 0 or total_vendas > 0
    best_month = "—"
    if monthly_net_list and max(monthly_net_list) > 0:
        best_month = months_sorted[monthly_net_list.index(max(monthly_net_list))]

    # ── NexusBI Branding Header ──
    from datetime import datetime as _dt_brand
    _month_names = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
    _now = _dt_brand.now()
    _cur_month_label = f"{_month_names.get(_now.month, '')} {_now.year}"
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
        f'<div style="display:flex;align-items:center;gap:10px">'
        f'<span style="background:{_brand_box};border-radius:7px;padding:5px 12px;font-size:13px;'
        f'font-weight:800;color:#0b0e1a;font-family:Nunito Sans,sans-serif">LATAMSELLERS</span>'
        f'<span style="font-size:10px;color:{_brand_finance};font-weight:700;letter-spacing:1px">FINANCE</span>'
        f'<span style="font-size:10px;color:{_text2};font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.8px">&middot; {_cur_month_label}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── NexusBI Banners ──
    if pending_files:
        _banners = []
        for pf in pending_files:
            _banners.append({
                "type": "yellow",
                "icon": "🟡",
                "text": f"<strong>{pf['month']}</strong> — {pf['name']}: {' · '.join(pf['issues'])}",
            })
        render_banners(_banners)

    # ══════════════════════════════════════════════════════════════
    # ROW 1: KPI Revenue | KPI Orders | Freshness  (3 columns)
    # ══════════════════════════════════════════════════════════════
    try:
        @st.cache_data(ttl=600, show_spinner=False)
        def _build_freshness():
            sources = ["vendas_ml", "extrato_nubank",
                       "extrato_c6_brl", "extrato_c6_usd", "extrato_mp",
                       "ads_publicidade", "armazenagem_full", "stock_full"]
            result = []
            now = datetime.now()
            special_dirs = {
                "ads_publicidade": DATA_DIR / "publicidade",
                "armazenagem_full": DATA_DIR / "armazenagem",
            }
            for src_id in sources:
                src_name = DATA_SOURCES.get(src_id, {}).get("name", src_id)
                latest_date = None
                latest_file_date = None
                found = False

                sp = special_dirs.get(src_id)
                if sp and sp.exists():
                    sp_files = sorted(sp.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if sp_files:
                        found = True
                        mod = datetime.fromtimestamp(sp_files[0].stat().st_mtime)
                        latest_file_date = mod.strftime("%d/%m/%Y")

                if not found:
                    for month in reversed(MONTHS):
                        loaded_m = get_loaded_files(month)
                        info = loaded_m.get(src_id)
                        if info:
                            found = True
                            if info.get("date_max"):
                                latest_date = info["date_max"]
                                break
                            elif not latest_file_date and info.get("date"):
                                latest_file_date = info["date"]
                            if latest_file_date:
                                break

                if latest_date:
                    try:
                        parsed = datetime.strptime(latest_date, "%d/%m/%Y")
                        days_old = (now - parsed).days
                    except Exception:
                        days_old = None
                    result.append({"name": src_name, "loaded": True,
                                   "date_max": latest_date, "days_old": days_old})
                elif found:
                    display_date = latest_file_date or "загружен"
                    days_old_f = None
                    if latest_file_date:
                        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                            try:
                                parsed_f = datetime.strptime(latest_file_date, fmt)
                                days_old_f = (now - parsed_f).days
                                break
                            except Exception:
                                pass
                    result.append({"name": src_name, "loaded": True,
                                   "date_max": display_date, "days_old": days_old_f})
                else:
                    result.append({"name": src_name, "loaded": False,
                                   "date_max": None, "days_old": None})
            return result

        freshness_data = _build_freshness()

        # ROW 1 — KPI+KPI в одном HTML iframe (два iframe ломались при F5), затем актуальность
        r1_kpis, r1_fresh = st.columns([2, 1])
        if has_data:
            with r1_kpis:
                render_kpi_header([
                    {"label": t("dash_net_revenue", L), "value": fmt_brl(total_net),
                     "sub": f"{t('dash_best_month', L)}: {best_month}",
                     "color": "yellow", "sparkline": monthly_net_list, "months": months_sorted},
                    {"label": t("dash_sales_count", L), "value": fmt_number(total_vendas),
                     "sub": f"{t('dash_ads_pct', L)}: {ads_pct:.0f}%",
                     "color": "blue", "sparkline": monthly_vendas_list, "months": months_sorted, "fmt": "number"},
                ])
            with r1_fresh:
                render_data_freshness_table(freshness_data, lang=L)
        else:
            st.info(t("dash_no_data", L))
    except Exception as e:
        st.error(f"Row 1 error: {e}")

    # ══════════════════════════════════════════════════════════════
    # Кошелёк по проектам + банки (сразу после KPI и актуальности данных)
    # ══════════════════════════════════════════════════════════════
    try:
        st.markdown(
            f'<hr style="border:none;border-top:1px solid {_border};margin:8px 0 4px;padding:0"/>',
            unsafe_allow_html=True,
        )
        section_header(t("dash_s3_wallet", L))

        from datetime import date as _date_type
        from finance import get_project_start_date
        today_d = _date_type.today()

        @st.cache_data(ttl=300, show_spinner=False)
        def _cached_cashflow(project: str, p_start: str, p_end: str):
            from datetime import date as _d
            return compute_cashflow(project, (_d.fromisoformat(p_start), _d.fromisoformat(p_end)))

        @st.cache_data(ttl=300, show_spinner=False)
        def _build_wallet(today_iso: str):
            from datetime import date as _d
            td = _d.fromisoformat(today_iso)
            wd = []
            for pid, pr in PROJECTS.items():
                bal = None
                ps = get_project_start_date(pid) or _d(2025, 9, 1)
                if pr.get("wallet_balance_brl") is not None:
                    bal = float(pr["wallet_balance_brl"])
                elif pr.get("type") == "ecom":
                    try:
                        cf = _cached_cashflow(pid, ps.isoformat(), td.isoformat())
                        bal = float(cf.closing_balance)
                    except Exception:
                        bal = 0.0
                if bal is not None:
                    wd.append({"name": pid, "balance": bal})
            return wd

        wallet_data = _build_wallet(today_d.isoformat())
        total_balance = sum(w["balance"] for w in wallet_data)

        render_wallet_cards(wallet_data, total_balance, lang=L)

        # ── Bank account balances (from latest extratos) ──
        @st.cache_data(ttl=300, show_spinner=False)
        def _get_bank_balances():
            """Extract latest balances from bank statement files."""
            balances = []

            # Find latest month with data (scan reverse)
            for m in reversed(MONTHS):
                mdir = DATA_DIR / m
                if not mdir.exists():
                    continue

                # Mercado Pago — FINAL_BALANCE from header row
                mp_path = mdir / "extrato_mp.csv"
                if mp_path.exists():
                    try:
                        df_mp = pd.read_csv(mp_path, sep=";", nrows=1, encoding="utf-8")
                        if "FINAL_BALANCE" in df_mp.columns:
                            fb = str(df_mp.iloc[0]["FINAL_BALANCE"]).replace(".", "").replace(",", ".")
                            balances.append({
                                "bank": "Mercado Pago",
                                "icon": "🟡",
                                "balance": float(fb),
                                "date": m,
                                "color": "#f59e0b",
                            })
                    except Exception:
                        pass

                # Nubank — compute balance from opening + all movements
                nu_path = mdir / "extrato_nubank.csv"
                if nu_path.exists():
                    try:
                        # Load all Nubank CSVs (legacy + monthly)
                        legacy_path = DATA_DIR.parent / "extrato bancario" / "NU_621252515_01JAN2025_10MAR2026.csv"
                        frames = []
                        if legacy_path.exists():
                            frames.append(pd.read_csv(legacy_path, sep=",", encoding="utf-8"))
                        frames.append(pd.read_csv(nu_path, sep=",", encoding="utf-8"))
                        df_all = pd.concat(frames).drop_duplicates(subset="Identificador")
                        opening = float(PROJECTS.get("COMPANY", {}).get("nubank_opening_balance", 0))
                        total_mov = df_all["Valor"].sum()
                        nu_balance = opening + total_mov
                        last_date = str(df_all["Data"].iloc[-1])[:10] if "Data" in df_all.columns else m
                        balances.append({
                            "bank": "Nubank PJ",
                            "icon": "🟣",
                            "balance": float(nu_balance),
                            "date": last_date,
                            "color": "#8b5cf6",
                        })
                    except Exception:
                        pass

                # C6 BRL — last row "Saldo do Dia(R$)"
                c6_path = mdir / "extrato_c6_brl.csv"
                if c6_path.exists():
                    try:
                        df_c6 = pd.read_csv(c6_path, sep=",", skiprows=8, encoding="utf-8")
                        saldo_col = [c for c in df_c6.columns if "saldo" in c.lower()]
                        if saldo_col:
                            last_saldo = df_c6[saldo_col[0]].dropna().iloc[-1]
                            try:
                                bal_c6 = float(str(last_saldo).replace(".", "").replace(",", "."))
                            except ValueError:
                                bal_c6 = float(last_saldo)
                            last_date_c6 = str(df_c6.iloc[-1].get(df_c6.columns[0], ""))[:10]
                            balances.append({
                                "bank": "C6 Bank BRL",
                                "icon": "🔵",
                                "balance": bal_c6,
                                "date": last_date_c6,
                                "color": "#3b82f6",
                            })
                    except Exception:
                        pass

                # C6 USD — parse from PDF (Saldo do dia)
                c6_usd_path = mdir / "extrato_c6_usd.pdf"
                if c6_usd_path.exists():
                    try:
                        import pdfplumber
                        import re as _re
                        with pdfplumber.open(c6_usd_path) as _pdf:
                            text = _pdf.pages[0].extract_text() if _pdf.pages else ""
                        m_usd = _re.search(r'Saldo do dia.*?US\$\s*([\d.,]+)', text)
                        if m_usd:
                            usd_str = m_usd.group(1).replace(".", "").replace(",", ".")
                            usd_bal = float(usd_str)
                            d_match = _re.search(r'Saldo do dia.*?(\d{1,2} de \w+ de \d{4})', text)
                            usd_date = d_match.group(1) if d_match else m
                            # FIFO BRL value
                            fifo_brl = None
                            fifo_rate = None
                            try:
                                fifo = calculate_trafficstars_fifo()
                                if fifo and fifo.get("brl_value_in_stock", 0) > 0:
                                    fifo_brl = fifo["brl_value_in_stock"]
                                    fifo_rate = fifo_brl / fifo["usd_in_stock"] if fifo["usd_in_stock"] > 0 else 0
                            except Exception:
                                pass
                            balances.append({
                                "bank": "C6 Bank USD",
                                "icon": "💵",
                                "balance": usd_bal,
                                "date": usd_date,
                                "color": "#059669",
                                "currency": "USD",
                                "fifo_brl": fifo_brl,
                                "fifo_rate": fifo_rate,
                            })
                    except Exception:
                        pass

                # Nubank Crédito — credit card statement if available
                for nu_cr_name in ["fatura_nubank.csv", "extrato_nubank_credito.csv"]:
                    nu_credit_path = mdir / nu_cr_name
                    if nu_credit_path.exists():
                        try:
                            df_nc = pd.read_csv(nu_credit_path, sep=",", encoding="utf-8")
                            val_col = [c for c in df_nc.columns if "valor" in c.lower() or "amount" in c.lower()]
                            if val_col:
                                total_fatura = df_nc[val_col[0]].sum()
                                balances.append({
                                    "bank": "Nubank Crédito",
                                    "icon": "💳",
                                    "balance": -abs(float(total_fatura)),
                                    "date": m,
                                    "color": "#dc2626",
                                })
                                break
                        except Exception:
                            pass

                if balances:
                    break  # Found data in this month, stop

            return balances

        bank_balances = _get_bank_balances()
        if bank_balances:
            section_header(t("dash_banks", L))
            render_bank_cards(bank_balances)

    except Exception as e:
        st.error(f"Section 3 error: {e}")

    # ══════════════════════════════════════════════════════════════
    # ROW 2: Маржа и расходы (full width)
    # ══════════════════════════════════════════════════════════════
    try:
        if has_data:
            _margin_data = {}
            for p_id, mat in pnl_matrices.items():
                rev_row = next((r for r in mat["rows"]
                                if "NET" in r.get("label", "") and r.get("section") == "ВЫРУЧКА"), None)
                exp_rows = [r for r in mat["rows"] if r.get("section") == "РАСХОДЫ"]
                profit_row = next((r for r in mat["rows"]
                                   if "операционная прибыль" in r.get("label", "").lower()
                                   or r.get("is_total")), None)
                if rev_row:
                    rev_total = sum(rev_row["values"].values())
                    exp_total = abs(sum(
                        sum(r["values"].values()) for r in exp_rows
                    )) if exp_rows else 0
                    profit = sum(profit_row["values"].values()) if profit_row else (rev_total - exp_total)
                    if rev_total > 0:
                        _margin_data[p_id] = {"rev": rev_total, "exp": exp_total, "profit": profit}

            if _margin_data:
                import plotly.graph_objects as _go_margin
                _m_names = list(_margin_data.keys())
                _m_rev = [_margin_data[n]["rev"] for n in _m_names]
                _m_exp = [_margin_data[n]["exp"] for n in _m_names]
                _m_profit = [_margin_data[n]["profit"] for n in _m_names]

                st.divider()
                section_header(t("dash_margin_expenses", L))
                _fig_m = _go_margin.Figure()
                _fig_m.add_trace(_go_margin.Bar(x=_m_names, y=_m_rev, name=t("chart_revenue", L),
                                                 marker=dict(color="rgba(255,213,0,0.7)", cornerradius=3)))
                _fig_m.add_trace(_go_margin.Bar(x=_m_names, y=_m_exp, name=t("chart_expenses", L),
                                                 marker=dict(color="rgba(255,87,87,0.6)", cornerradius=3)))
                _fig_m.add_trace(_go_margin.Bar(x=_m_names, y=_m_profit, name=t("chart_profit", L),
                                                 marker=dict(color="rgba(52,211,153,0.7)", cornerradius=3)))
                from dashboard_charts import _layout as _dc_layout
                _fig_m.update_layout(**_dc_layout(
                    height=300, barmode="group",
                    xaxis=dict(showgrid=False, type="category",
                               tickfont=dict(color="#f0f2ff", size=11, family="Nunito Sans")),
                    yaxis=dict(tickformat=",.0f",
                               tickfont=dict(color="rgba(168,178,209,0.85)", size=9)),
                    legend=dict(font=dict(color="#a8b2d1", size=10)),
                ))
                st.plotly_chart(_fig_m, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.error(f"Row 2 error: {e}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 4: ОЖИДАЕМЫЕ РАСХОДЫ И АРЕНДА
    # ══════════════════════════════════════════════════════════════
    try:
        st.divider()

        import calendar as cal_mod
        from datetime import date as _date_mod
        today_iso = _date_mod.today().isoformat()

        @st.cache_data(ttl=300, show_spinner=False)
        def _cached_opiu_estonia():
            from reports import generate_opiu_estonia
            return generate_opiu_estonia()

        expenses_list = []

        # USD→BRL rate for rental conversion
        _usd_brl_rate = 5.64
        try:
            _fifo_r = calculate_trafficstars_fifo()
            if _fifo_r and _fifo_r.get("usd_in_stock", 0) > 0:
                _usd_brl_rate = _fifo_r["brl_value_in_stock"] / _fifo_r["usd_in_stock"]
        except Exception:
            pass

        rental_income = []
        for proj_id, proj in PROJECTS.items():
            rental = proj.get("rental")
            if rental:
                for payment in rental.get("payments", []):
                    if payment.get("status") == "pending":
                        usd_amt = payment.get("usd", 0)
                        brl_amt = usd_amt * _usd_brl_rate
                        brl_fmt = f"{brl_amt:,.0f}".replace(",", ".")
                        rental_income.append({
                            "project": proj_id,
                            "category": t("dash_rental", L),
                            "amount": usd_amt,
                            "currency": "USD",
                            "brl_equivalent": brl_amt,
                            "next_date": payment.get("date", ""),
                            "note": f"{payment.get('quarter', '')} @ {_usd_brl_rate:.2f}",
                        })

            for exp in (proj.get("manual_expenses") or []):
                exp_date = exp.get("date", "")
                if exp_date >= today_iso:
                    expenses_list.append({
                        "project": proj_id,
                        "category": t("dash_manual_expenses", L),
                        "amount": abs(exp.get("valor", 0)),
                        "currency": "BRL",
                        "next_date": exp_date,
                        "note": exp.get("note", ""),
                    })

            if proj.get("type") == "ecom" and proj_id in opiu:
                proj_months = sorted(opiu[proj_id].get("by_month", {}).keys())
                for mk in reversed(proj_months):
                    try:
                        y, mo = int(mk[:4]), int(mk[5:7])
                        last_day = cal_mod.monthrange(y, mo)[1]
                        arm = get_armazenagem_by_period(proj_id, _date_mod(y, mo, 1), _date_mod(y, mo, last_day))
                        arm_val = float(arm.get("total", 0) or 0)
                        if arm_val > 0:
                            expenses_list.append({
                                "project": proj_id,
                                "category": t("dash_storage_costs", L),
                                "amount": arm_val,
                                "currency": "BRL",
                                "next_date": None,
                                "note": f"~{mk}",
                            })
                            break
                    except Exception:
                        pass

        # DAS pending payments (from Estonia opiu + ecom estimates)
        try:
            opiu_est = _cached_opiu_estonia()
            for dp in opiu_est.get("das_pending", []):
                if dp.get("status") in ("estimated", "pending"):
                    # DAS vencimento is ~20th of next month
                    mk = dp.get("month", "")
                    if mk:
                        y, mo = int(mk[:4]), int(mk[5:7])
                        next_mo = mo + 1 if mo < 12 else 1
                        next_y = y if mo < 12 else y + 1
                        due = f"{next_y}-{next_mo:02d}-20"
                    else:
                        due = None
                    expenses_list.append({
                        "project": "ESTONIA",
                        "category": t("dash_das_tax", L),
                        "amount": dp.get("value", 0),
                        "currency": "BRL",
                        "next_date": due,
                        "note": mk,
                    })
        except Exception:
            pass

        # Recurring monthly company expenses (current month only)
        cur_y, cur_m = _date_mod.today().year, _date_mod.today().month
        due_date = f"{cur_y}-{cur_m:02d}-10"
        for cat, amt in [("Contador", 500), ("ERP", 350), ("Armazenamento", 450), ("Fatura cartao", 920.50)]:
            expenses_list.append({
                "project": "EMPRESA",
                "category": cat,
                "amount": amt,
                "currency": "BRL",
                "next_date": due_date,
                "note": "mensal",
            })

        expenses_list.sort(key=lambda e: e.get("next_date") or "9999-12-31")

        # 30-day window for totals
        from datetime import timedelta as _td
        _cutoff_30 = (_date_mod.today() + _td(days=30)).isoformat()

        def _within_30d(e):
            d = e.get("next_date")
            if not d:
                return True  # no date = include
            return d <= _cutoff_30

        # ── Build income list ──
        income_list = []
        try:
            if not opiu_est:
                opiu_est = _cached_opiu_estonia()
            pnl_months = opiu_est.get("pnl_by_month", [])
            for pm in pnl_months:
                if pm.get("das_status") in ("estimated", "pending"):
                    profit = pm.get("profit", 0)
                    if profit > 0:
                        income_list.append({
                            "project": "ESTONIA",
                            "category": "Lucro NFS-e (comissao - DAS)",
                            "amount": profit,
                            "currency": "BRL",
                            "next_date": None,
                            "note": pm.get("month", ""),
                        })
        except Exception:
            pass
        for ri in rental_income:
            income_list.append(ri)

        # ── NexusBI side-by-side layout (expenses | income) ──
        col_exp, col_inc = st.columns(2)
        with col_exp:
            section_header(t("dash_s4_expenses", L))
            if expenses_list:
                render_expenses_table(expenses_list)
                exp_30 = [e for e in expenses_list if _within_30d(e)]
                total_exp_brl = sum(
                    e["amount"] * (_usd_brl_rate if e.get("currency") == "USD" else 1)
                    for e in exp_30
                )
                total_exp_fmt = f"{total_exp_brl:,.0f}".replace(",", ".")
                st.markdown(
                    f'<div style="text-align:right;padding:6px 12px;font-size:12px;font-weight:700;'
                    f'color:#ff5757;font-family:DM Mono,monospace">'
                    f'Итого (30 дней): R$ {total_exp_fmt}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("—")

        with col_inc:
            section_header(t('dash_expected_income', L))
            if income_list:
                render_expenses_table(income_list)
                inc_30 = [e for e in income_list if _within_30d(e)]
                total_inc_brl = sum(
                    e["amount"] * (_usd_brl_rate if e.get("currency") == "USD" else 1)
                    for e in inc_30
                )
                total_inc_fmt = f"{total_inc_brl:,.0f}".replace(",", ".")
                st.markdown(
                    f'<div style="text-align:right;padding:6px 12px;font-size:12px;font-weight:700;'
                    f'color:#22d3a5;font-family:DM Mono,monospace">'
                    f'{t("dash_mp_30d_total", L)}: R$ {total_inc_fmt}</div>',
                    unsafe_allow_html=True,
                )

    except Exception as e:
        st.error(f"Section 4 error: {e}")

    # ══════════════════════════════════════════════
    # PROJECT STATUS (collapsible)
    # ══════════════════════════════════════════════
    st.divider()
    with st.expander(t("projects", L)):
        displayable = {k: v for k, v in PROJECTS.items() if v.get("type")}
        if displayable:
            proj_cols = st.columns(len(displayable))
            for i, (proj_id, proj) in enumerate(displayable.items()):
                with proj_cols[i]:
                    rental = proj.get("rental")
                    rental_info = ""
                    if rental:
                        pending_r = rental.get("total_pending_usd", 0)
                        if pending_r > 0:
                            rental_info = f"\n\n🔴 ${pending_r} USD"
                        else:
                            rental_info = "\n\n✅ Aluguel ok"
                    if proj.get("status") == "approved":
                        st.success(f"**{proj_id}**\n\n{proj['type'].upper()}\n\n✅ {proj.get('last_report', '')}{rental_info}")
                    else:
                        st.warning(f"**{proj_id}**\n\n{proj['type'].upper()}\n\n⏳ {t('pending', L)}{rental_info}")

    # ══════════════════════════════════════════════
    # DATA MATRIX (collapsible)
    # ══════════════════════════════════════════════
    with st.expander(t("data_matrix", L)):
        ecom_sources = {k: v for k, v in DATA_SOURCES.items() if v["type"] in ("ecom", "all")}
        svc_sources = {k: v for k, v in DATA_SOURCES.items() if v["type"] in ("services", "all")}

        st.markdown(f"**{t('ecom_title', L)}**")
        header = [t("source_col", L)] + MONTHS
        rows = []
        for src_id, src in ecom_sources.items():
            row = [src["name"]]
            for month in MONTHS:
                loaded = get_loaded_files(month)
                row.append("🟢" if loaded.get(src_id) else "🔴")
            rows.append(row)
        st.dataframe(pd.DataFrame(rows, columns=header), hide_index=True)

        st.markdown(f"**{t('services_title', L)}**")
        rows_svc = []
        for src_id, src in svc_sources.items():
            row = [src["name"]]
            for month in MONTHS:
                loaded = get_loaded_files(month)
                row.append("🟢" if loaded.get(src_id) else "🔴")
            rows_svc.append(row)
        st.dataframe(pd.DataFrame(rows_svc, columns=header), hide_index=True)


# ─────────────────────────────────────────────
# PAGE: UPLOAD (redesigned — upload_clean_final style)
# ─────────────────────────────────────────────

elif page == t("page_upload", L):
    from upload_page import render_upload_page
    render_upload_page(L)



# ─────────────────────────────────────────────
# PAGE: REPORTS
# ─────────────────────────────────────────────

elif page == t("page_reports", L):
    from reports import (
        calculate_trafficstars_fifo,
        generate_balance_estonia,
        generate_dds_estonia,
        generate_opiu_estonia,
        parse_c6_brl,
        parse_c6_usd,
    )

    st.title(t("reports_title", L))

    sel_project = st.selectbox(t("project", L) + ":", list(PROJECTS.keys()))
    proj = PROJECTS[sel_project]
    st.markdown(f"**{t('type_label', L)}:** {proj['type'].upper()} | **{t('description', L)}:** {proj['description']}")

    if proj.get("status") == "approved":
        st.success(f"{t('report_approved', L)} {proj.get('last_report', 'N/A')}")
        report_dir = PROJETOS_DIR / sel_project
        if report_dir.exists():
            files = sorted(report_dir.iterdir())
            if files:
                with st.expander(t("approved_files", L)):
                    for f in files:
                        st.markdown(f"- `{f.name}` ({f.stat().st_size:,} bytes)")

    st.divider()

    # ──────────────── ECOM PROJECTS (refactored) ────────────────
    if proj["type"] == "ecom":
        from datetime import date as _date, datetime as _dt
        from finance import compute_pnl, compute_cashflow, compute_balance, get_baseline_date, get_project_start_date
        from report_views import render_pnl_tab, render_cashflow_tab, render_balance_tab, render_quality_tab, render_vendas_ml_tab

        baseline = get_baseline_date(sel_project)
        project_start = get_project_start_date(sel_project)

        # ── Auto-detect period from loaded vendas data ──
        from reports import load_vendas_ml_report
        import re as _re_period
        _pt_months = {
            "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
            "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
            "outubro": 10, "novembro": 11, "dezembro": 12,
        }
        def _parse_pt_date(s):
            g = _re_period.search(r"(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})", str(s))
            if not g:
                return None
            mn = _pt_months.get(g.group(2).lower())
            if not mn:
                return None
            try:
                return _date(int(g.group(3)), mn, int(g.group(1)))
            except (ValueError, TypeError):
                return None

        _vendas_df = load_vendas_ml_report()
        _vendas_dates = []
        _vendas_file = ""
        if _vendas_df is not None and not _vendas_df.empty:
            _vendas_file = _vendas_df.attrs.get("__source_file", "")
            for _, _vr in _vendas_df.iterrows():
                _vd = _parse_pt_date(_vr.get("Data da venda"))
                if _vd is not None:
                    _vendas_dates.append(_vd)

        if _vendas_dates:
            period_from = min(_vendas_dates)
            period_to = max(_vendas_dates)
            # Show info about covered period
            _loaded_months = sorted({d.strftime("%Y-%m") for d in _vendas_dates})
            st.info(t("report_vendas_period", L).format(
                d1=period_from.strftime('%d.%m.%Y'), d2=period_to.strftime('%d.%m.%Y'),
                f=_vendas_file, m=', '.join(_loaded_months),
            ))
        else:
            period_from = project_start or _date(2025, 9, 1)
            period_to = _date.today()
            st.warning(t("report_no_vendas", L))

        try:
            pnl = compute_pnl(sel_project, (period_from, period_to))
            cf = compute_cashflow(sel_project, (period_from, period_to))
            bal = compute_balance(sel_project, period_to)
        except Exception as e:
            st.error(f"{t('report_calc_error', L)}: {e}")
            st.caption(f"DEBUG: DATA_DIR={DATA_DIR}, exists={DATA_DIR.exists()}, contents={list(DATA_DIR.iterdir()) if DATA_DIR.exists() else 'N/A'}")
            st.stop()

        tab_pnl, tab_cf, tab_bs = st.tabs([
            t("report_tab_opiu_short", L),
            t("report_tab_dds_short", L),
            t("report_tab_balance_short", L),
        ])
        with tab_pnl:
            render_pnl_tab(pnl)
        with tab_cf:
            render_cashflow_tab(cf)
        with tab_bs:
            render_balance_tab(bal)

    # ──────────────── SERVICES: ESTONIA ────────────────
    elif sel_project == "ESTONIA":
        opiu_est = generate_opiu_estonia()
        dds_est = generate_dds_estonia()
        bal_est = generate_balance_estonia()

        tab_opiu, tab_dds, tab_balance = st.tabs([
            t("tab_opiu", L), t("tab_dds", L), t("tab_balance", L)
        ])

        with tab_opiu:
            st.markdown(f"### ESTONIA — {t('period', L)} (OPiU)")

            def fmt_e(v):
                return f"R$ {v:,.0f}".replace(",", ".")

            st.markdown("#### Наш доход от проекта")
            opiu_md = f"""
| | Valor |
|---|---|
| Инвойсы (общий оборот) | {fmt_e(opiu_est['total_gross'])} |
| | |
| **НАША ВЫРУЧКА (BRL):** | |
| Комиссия (% = ставка налога) | {fmt_e(opiu_est['our_commission'])} |
| (-) DAS Simples Nacional | -{fmt_e(opiu_est['our_das'])} |
| **= Прибыль BRL** | **{fmt_e(opiu_est['our_profit_brl'])}** |
| | |
| **АРЕНДА (USD) — $700/квартал:** | |
"""
            st.markdown(opiu_md)

            # Rental detail table
            rental_md = """
#### Аренда компании ($700/квартал = 2× $350)

| # | Дата | USD | Квартал | Статус |
|---|---|---|---|---|
| 1 | 09/04/2025 | $350 | Q1 Abr-Jun/25 | ✅ pago |
| 2 | 17/07/2025 | $350 | Q1 Abr-Jun/25 | ✅ pago |
| 3 | 19/08/2025 | $350 | Q2 Jul-Set/25 | ✅ pago |
| 4 | 29/10/2025 | $350 | Q2 Jul-Set/25 | ✅ pago |
| 5 | 10/11/2025 | $350 | Q3 Out-Dez/25 | ✅ pago |
| 6 | 14/01/2026 | $350 | Q3 Out-Dez/25 | ✅ pago |
| 7 | 09/02/2026 | $350 | Q4 Jan-Mar/26 | ✅ pago |
| 8 | — | $350 | Q4 Jan-Mar/26 | 🔴 PENDENTE |
| | | **$2.450** | **pago** | **deve $350** |

#### Календарь следующих платежей

| Квартал | Период | Valor | Vencimento | Parcelas |
|---|---|---|---|---|
| Q4 (остаток) | Jan-Mar/26 | $350 | Mar/2026 | 1× $350 |
| Q5 | Abr-Jun/26 | $700 | Abr/2026 | 2× $350 |
| Q6 | Jul-Set/26 | $700 | Jul/2026 | 2× $350 |
| Q7 | Out-Dez/26 | $700 | Out/2026 | 2× $350 |
| Q8 | Jan-Mar/27 | $700 | Jan/2027 | 2× $350 |
| | **Total prox 4Q** | **$2.800** | | 8× $350 |
| | **+ pendente** | **$3.150** | | 9× $350 |
"""
            st.markdown(rental_md)

            bracket_md = f"""
---
**Прогрессивная шкала (комиссия = ставка налога):**
- До R$ 180k → **15,50%**
- R$ 180-360k → **16,75%**
- R$ 360-720k → **18,75%** ← текущая ({fmt_e(opiu_est['cumulative_gross'])})
- R$ 720k-1.8M → **19,75%** ← следующая
"""
            st.markdown(bracket_md)

            st.markdown(f"#### 📊 P&L mensal — comissões e impostos")

            pnl_rows = []
            for item in opiu_est["pnl_by_month"]:
                if item["invoice_gross"] == 0 and item["das"] == 0:
                    continue
                # Status icon
                if item["has_pdf"]:
                    doc_status = "✅ PDF"
                elif item["das_status"] == "paid":
                    doc_status = "💰 Pago"
                elif item["das_status"] == "estimated":
                    doc_status = "⏳ Estimado"
                else:
                    doc_status = "—"

                pnl_rows.append({
                    "Mês": item["month"],
                    "Inv qtd": item["invoice_count"],
                    "Bruto inv": item["invoice_gross"],
                    "Comissão": item["commission"],
                    "Imposto": item["das"],
                    "Doc": doc_status,
                    "Lucro": item["profit"],
                })

            df_pnl = pd.DataFrame(pnl_rows)
            st.dataframe(
                df_pnl,
                width="stretch",
                hide_index=True,
                column_config={
                    "Bruto inv": st.column_config.NumberColumn("Bruto inv", format="R$ %.2f"),
                    "Comissão": st.column_config.NumberColumn("Comissão", format="R$ %.2f"),
                    "Imposto": st.column_config.NumberColumn("Imposto", format="R$ %.2f"),
                    "Lucro": st.column_config.NumberColumn("Lucro", format="R$ %.2f"),
                },
            )

            # Totais
            total_inv = df_pnl["Bruto inv"].sum()
            total_com = df_pnl["Comissão"].sum()
            total_das = df_pnl["Imposto"].sum()
            total_lucro = df_pnl["Lucro"].sum()

            pdf_count = sum(1 for r in pnl_rows if "PDF" in r["Doc"])
            pending_count = sum(1 for r in pnl_rows if "Estimado" in r["Doc"])

            st.markdown(f"""
| | R$ |
|---|---|
| **Total bruto invoices** | {fmt_e(total_inv)} |
| **Total comissão (nossa receita)** | **{fmt_e(total_com)}** |
| **Total imposto (parte Estonia)** | -{fmt_e(total_das)} |
| **= Lucro líquido** | **{fmt_e(total_lucro)}** |
            """)
            st.caption(f"📋 DAS confirmados (PDF): **{pdf_count}** | DAS estimados: **{pending_count}**")

            if pending_count > 0:
                st.info(t("up_das_hint", L))


        with tab_dds:
            st.markdown(f"### {t('dds_title', L)} — ESTONIA")
            flow_cur, flow_fut = st.tabs([t('flow_current', L), t('flow_future', L)])
            with flow_cur:
                st.code("SHPS -> Nubank PJ (BRL) -> C6 PJ (BRL) -> USD -> TrafficStars", language=None)
            with flow_fut:
                st.code("SHPS -> C6 PJ (BRL) -> USD -> TrafficStars", language=None)
                st.caption(t("flow_future_note", L))

            st.divider()

            def fmt_d(v):
                return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            # === ENTRADAS — todas as invoices ===
            st.markdown("#### 📥 ENTRADAS — Invoices SHPS (Estonia)")
            invoice_lines = [
                {"date": "2025-07-07", "gross": 1537.41, "rate": "15,5%", "tax": 238.30},
                {"date": "2025-07-09", "gross": 27867.27, "rate": "15,5%", "tax": 4319.47},
                {"date": "2025-08-08", "gross": 85244.97, "rate": "15,5%", "tax": 13212.97},
                {"date": "2025-09-03", "gross": 64373.03, "rate": "15,5%", "tax": 9977.82},
                {"date": "2025-10-02", "gross": 11676.91, "rate": "16,75%", "tax": 1955.88},
                {"date": "2025-11-05", "gross": 977.32, "rate": "15,5%", "tax": 151.48},
                {"date": "2025-11-05", "gross": 2218.41, "rate": "16,75%", "tax": 371.58},
                {"date": "2025-12-02", "gross": 118857.00, "rate": "16,75%", "tax": 19908.55},
                {"date": "2026-01-14", "gross": 47247.68, "rate": "16,75%", "tax": 7913.99},
                {"date": "2026-01-14", "gross": 133472.52, "rate": "18,75%", "tax": 25026.10},
                {"date": "2026-02-02", "gross": 91744.81, "rate": "18,75%", "tax": 17202.15},
                {"date": "2026-03-03", "gross": 101482.12, "rate": "18,75%", "tax": 19027.90},
            ]
            entradas_rows = []
            for i, inv in enumerate(invoice_lines, 1):
                y, m, d = inv["date"].split("-")
                entradas_rows.append({
                    "#": i,
                    "Data": pd.Timestamp(year=int(y), month=int(m), day=int(d)),
                    "Bruto": inv["gross"],
                    "Faixa": inv["rate"],
                    "Imposto": inv["tax"],
                    "Líquido": inv["gross"] - inv["tax"],
                })
            df_ent = pd.DataFrame(entradas_rows)
            st.dataframe(
                df_ent,
                width="stretch",
                hide_index=True,
                column_config={
                    "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "Bruto": st.column_config.NumberColumn("Bruto", format="R$ %.2f"),
                    "Imposto": st.column_config.NumberColumn("Imposto", format="R$ %.2f"),
                    "Líquido": st.column_config.NumberColumn("Líquido", format="R$ %.2f"),
                },
            )
            total_bruto = df_ent["Bruto"].sum()
            total_imp = df_ent["Imposto"].sum()
            st.markdown(f"**Bruto: {fmt_d(total_bruto)}** | **Imposto: -{fmt_d(total_imp)}** | **Líquido: {fmt_d(total_bruto - total_imp)}**")

            # Download Entradas
            csv_ent = df_ent.copy()
            csv_ent["Data"] = csv_ent["Data"].dt.strftime("%d/%m/%Y")
            ent_bytes = csv_ent.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="⬇️ Скачать CSV (Entradas)",
                data=ent_bytes,
                file_name=f"entradas_estonia_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime="text/csv",
                key="download_entradas",
            )

            # === SAIDAS — todas as transferencias ===
            st.divider()
            st.markdown("#### 📤 SAIDAS — Valores enviados para Estonia")
            transfers_rows = []

            # 1. Direct transfers (CALIZA, Bybit, Credit Nubank TS) — non-C6-Cambio
            for tr in dds_est.get("transfers", []):
                if tr["canal"] == "C6 Cambio":
                    continue  # skip — replaced by TrafficStars FIFO debits
                d, m, y = tr["date"].split("/")
                year = 2000 + int(y) if len(y) == 2 else int(y)
                real_date = pd.Timestamp(year=year, month=int(m), day=int(d))
                transfers_rows.append({
                    "Data": real_date,
                    "USD": tr["usd"] if tr["usd"] else None,
                    "Курс": tr["vet"] if tr["vet"] else None,
                    "Canal": tr["canal"],
                    "BRL": tr["brl"],
                    "Fonte": "Aprovado",
                })

            # 2. TrafficStars debits with FIFO BRL cost (replaces C6 Cambio rows)
            fifo = calculate_trafficstars_fifo()
            if fifo:
                for ts_item in fifo["ts_payments"]:
                    transfers_rows.append({
                        "Data": ts_item["date"],
                        "USD": ts_item["usd"],
                        "Курс": ts_item["rate"],
                        "Canal": "TrafficStars (FIFO)",
                        "BRL": ts_item["brl"],
                        "Fonte": "C6 USD",
                    })

            if transfers_rows:
                df_tr = pd.DataFrame(transfers_rows)
                df_tr = df_tr.sort_values("Data").reset_index(drop=True)
                df_tr.insert(0, "#", range(1, len(df_tr) + 1))
                st.dataframe(
                    df_tr,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "USD": st.column_config.NumberColumn("USD", format="$%.2f"),
                        "Курс": st.column_config.NumberColumn("Курс", format="%.4f"),
                        "BRL": st.column_config.NumberColumn("BRL", format="R$ %.2f"),
                    },
                )

                total_brl = df_tr["BRL"].sum()
                caliza_brl = sum(t["BRL"] for t in transfers_rows if "CALIZA" in t["Canal"])
                bybit_brl = sum(t["BRL"] for t in transfers_rows if "Bybit" in t["Canal"])
                ts_brl = sum(t["BRL"] for t in transfers_rows if "TrafficStars" in t["Canal"])
                cred_brl = sum(t["BRL"] for t in transfers_rows if "Cred" in t["Canal"])

                st.markdown(f"""
| Canal | R$ |
|---|---|
| CALIZA-Nubank (AdvertMedia) | {fmt_d(caliza_brl)} |
| Bybit (USDT) | {fmt_d(bybit_brl)} |
| TrafficStars (FIFO) | {fmt_d(ts_brl)} |
| Cred.Nubank TS | {fmt_d(cred_brl)} |
| **TOTAL ENVIADO** | **{fmt_d(total_brl)}** |
                """)
                st.caption("* TrafficStars расходы пересчитаны по FIFO курсу покупки USD")

                # Download as CSV
                csv_export = df_tr.copy()
                csv_export["Data"] = csv_export["Data"].dt.strftime("%d/%m/%Y")
                csv_bytes = csv_export.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    label="⬇️ Скачать CSV (Saidas)",
                    data=csv_bytes,
                    file_name=f"saidas_estonia_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv",
                )

                # Verification block
                with st.expander("🔍 Сверка с выпиской"):
                    st.markdown("**Проверка 1: TrafficStars total**")
                    fifo_check = calculate_trafficstars_fifo()
                    if fifo_check:
                        c6_usd_check = parse_c6_usd()
                        ts_usd_total = fifo_check["total_ts_usd"]
                        ts_brl_total = fifo_check["total_ts_brl"]

                        st.markdown(f"- FIFO рассчитал: **${ts_usd_total:,.2f}** = **{fmt_d(ts_brl_total)}**")
                        if c6_usd_check:
                            extrato_ts = c6_usd_check["trafficstars_usd"]
                            extrato_total_saidas = c6_usd_check["total_saidas_usd"]
                            extrato_total_entradas = c6_usd_check["total_entradas_usd"]
                            extrato_saldo = c6_usd_check["saldo_usd"]

                            diff = abs(ts_usd_total - extrato_ts)
                            status_icon = "✅" if diff < 0.01 else "⚠️"
                            st.markdown(f"- C6 USD выписка показывает TrafficStars: **${extrato_ts:,.2f}** {status_icon}")

                            st.markdown("**Проверка 2: C6 USD PDF totals**")
                            st.markdown(f"- Total entradas (PDF header): **${extrato_total_entradas:,.2f}**")
                            st.markdown(f"- Total saídas (PDF header): **${extrato_total_saidas:,.2f}**")
                            st.markdown(f"- Saldo final: **${extrato_saldo:,.2f}**")
                            check_calc = extrato_total_entradas - extrato_total_saidas
                            st.markdown(f"- Math check: ${extrato_total_entradas:,.2f} - ${extrato_total_saidas:,.2f} = ${check_calc:,.2f}")

                    st.markdown("**Проверка 3: CALIZA + Bybit + Cred TS (валидация)**")
                    st.markdown(f"- CALIZA-Nubank: {fmt_d(caliza_brl)} (2 операции)")
                    st.markdown(f"- Bybit USDT: {fmt_d(bybit_brl)} (2 операции)")
                    st.markdown(f"- Cred.Nubank TS: {fmt_d(cred_brl)} (2 операции)")

                    st.markdown("**Источники:**")
                    st.markdown("- Утверждённый отчёт: `projetos/ESTONIA/Balanco_Estonia_19_03_2026.csv`")
                    st.markdown("- C6 USD live: `_data/2026-04/extrato_c6_usd.pdf`")
                    st.markdown("- C6 BRL live: `_data/2026-04/extrato_c6_brl.csv`")

            # C6 BRL live data (if loaded)
            st.divider()
            c6_data = parse_c6_brl()
            if c6_data:
                st.markdown(f"#### C6 Bank BRL (dados carregados: {c6_data['date_min']} — {c6_data['date_max']})")

                c6_col1, c6_col2 = st.columns(2)
                with c6_col1:
                    st.markdown(f"""
| C6 BRL | R$ |
|---|---|
| PIX entrada (Nubank→C6) | {fmt_d(c6_data['pix_entrada'])} |
| Câmbio (BRL→USD) | -{fmt_d(c6_data['cambio_usd'])} |
| Compras cartão | -{fmt_d(c6_data['compras_cartao'])} |
| Seguro + outros | -{fmt_d(c6_data['seguro'] + c6_data['outros_saida'])} |
| **Saldo C6 BRL** | **{fmt_d(c6_data['saldo_final'])}** |
                    """)
                with c6_col2:
                    st.markdown(f"""
| Resumo | |
|---|---|
| Total entrada | {fmt_d(c6_data['total_entrada'])} |
| Total saída | -{fmt_d(c6_data['total_saida'])} |
| Convertido USD | {fmt_d(c6_data['cambio_usd'])} ({c6_data['cambio_usd']/c6_data['total_entrada']*100:.1f}%) |
| Ficou em BRL | {fmt_d(c6_data['brl_kept'])} |
| Linhas | {c6_data['rows']} |
                    """)

                # Daily flow table
                with st.expander("Fluxo diário Nubank→C6→USD"):
                    daily_rows = []
                    for date in sorted(c6_data["by_date"].keys()):
                        d = c6_data["by_date"][date]
                        if d["pix_in"] > 0 or d["cambio_out"] > 0:
                            daily_rows.append({
                                "Data": date,
                                "PIX entrada": d["pix_in"],
                                "Câmbio →USD": d["cambio_out"],
                            })
                    if daily_rows:
                        st.dataframe(pd.DataFrame(daily_rows), width="stretch", hide_index=True)

            # C6 USD data (from PDF)
            c6_usd = parse_c6_usd()
            if c6_usd:
                st.divider()
                st.markdown(f"#### C6 Bank USD (Fev-Abr/2026)")

                usd_col1, usd_col2 = st.columns(2)
                with usd_col1:
                    st.markdown(f"""
| C6 USD | US$ |
|---|---|
| Entradas (BRL→USD) | ${c6_usd['transf_entrada_usd']:,.2f} |
| (-) TrafficStars | -${c6_usd['trafficstars_usd']:,.2f} |
| (-) Outros | -${c6_usd['outros_debitos_usd']:,.2f} |
| **Saldo USD** | **${c6_usd['saldo_usd']:,.2f}** |
                    """)
                with usd_col2:
                    st.markdown(f"""
| Resumo | |
|---|---|
| Pagamentos TrafficStars | {len([t for t in c6_usd['transactions'] if 'TrafficStars' in t['desc']])} |
| Total TrafficStars | ${c6_usd['trafficstars_usd']:,.2f} |
| Entradas (transf) | {len([t for t in c6_usd['transactions'] if t['type'] == 'entrada'])} |
| Total entradas | ${c6_usd['transf_entrada_usd']:,.2f} |
                    """)

                with st.expander("Transações USD (TrafficStars + entradas)"):
                    tx_rows = []
                    for tx in c6_usd["transactions"]:
                        tx_rows.append({
                            "Data": tx["date"],
                            "Tipo": tx["desc"],
                            "US$": tx["amount"],
                        })
                    if tx_rows:
                        st.dataframe(pd.DataFrame(tx_rows), width="stretch", hide_index=True)

                # FIFO TrafficStars table
                fifo = calculate_trafficstars_fifo()
                if fifo:
                    st.markdown("#### TrafficStars (BRL по FIFO)")
                    st.caption("Каждая оплата TrafficStars пересчитана по реальному курсу покупки USD (FIFO — старые покупки списываются первыми)")

                    fifo_rows = []
                    for ts_item in fifo["ts_payments"]:
                        fifo_rows.append({
                            "Data": ts_item["date"],
                            "USD": ts_item["usd"],
                            "Курс (FIFO)": ts_item["rate"],
                            "BRL": ts_item["brl"],
                        })
                    df_fifo = pd.DataFrame(fifo_rows)
                    st.dataframe(
                        df_fifo,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                            "USD": st.column_config.NumberColumn("USD", format="$%.2f"),
                            "Курс (FIFO)": st.column_config.NumberColumn("Курс", format="%.4f"),
                            "BRL": st.column_config.NumberColumn("BRL", format="R$ %.2f"),
                        },
                    )

                    avg_rate = fifo["total_ts_brl"] / fifo["total_ts_usd"] if fifo["total_ts_usd"] > 0 else 0
                    st.markdown(f"""
| | |
|---|---|
| **Total TrafficStars** | **${fifo['total_ts_usd']:,.2f} = {fmt_d(fifo['total_ts_brl'])}** |
| Курс средний | {avg_rate:.4f} |
| | |
| **USD в наличии (estoque)** | **${fifo['usd_in_stock']:,.2f} = {fmt_d(fifo['brl_value_in_stock'])}** |
                    """)

        with tab_balance:
            st.markdown(f"### {t('balance_title', L)} — ESTONIA")

            def fmt_b(v):
                return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            # Approved balance
            st.markdown("#### Balanço aprovado (19/03/2026)")
            bal_md = f"""
| | R$ |
|---|---|
| Saldo inicial | {fmt_b(bal_est['saldo_inicial'])} |
| (+) Bruto recebido (10 invoices) | {fmt_b(bal_est['total_gross'])} |
| (-) Taxa impostos (15,5/16,75/18,75%) | -{fmt_b(bal_est['total_tax'])} |
| = Líquido recebido | {fmt_b(bal_est['total_net_client'])} |
| (-) Total enviado até 19/03 | -{fmt_b(bal_est['total_enviado_approved'])} |
| **= DÉBITO em 19/03** | **{fmt_b(bal_est['debito_approved'])}** |
"""
            st.markdown(bal_md)

            # Balance with clear math — USD reserve is OUR asset, not Estonia debt
            if bal_est.get("has_live_data"):
                liquido_total = bal_est['saldo_inicial'] + bal_est['total_net_client']
                usd_brl = bal_est['brl_value_in_stock']
                # Real debt = received - already sent (USD reserve will be sent later)
                debt = liquido_total - bal_est['total_real_enviado']

                st.markdown("#### Balanço com Estonia")
                st.markdown(f"""
| | R$ |
|---|---|
| **RECEBIDO da Estonia** (líquido + saldo inicial) | **{fmt_b(liquido_total)}** |
| (-) Já enviado (CALIZA + Bybit + Cred TS + TrafficStars FIFO) | -{fmt_b(bal_est['total_real_enviado'])} |
| **= AINDA DEVEMOS A ESTONIA** | **{fmt_b(debt)}** |
                """)

                st.markdown("#### Reserva nas nossas contas (já é nosso, vai cobrir débito futuro)")
                st.markdown(f"""
| | |
|---|---|
| USD em C6 (FIFO valorizado) | ${bal_est['usd_in_stock']:,.2f} = {fmt_b(usd_brl)} |
                """)

                if debt > 100:
                    st.warning(f"### 💰 Devemos a Estonia: **{fmt_b(debt)}** (será coberto pela reserva USD em estoque)")
                elif debt < -100:
                    st.info(f"### 📊 Já enviamos {fmt_b(abs(debt))} a mais que o líquido recebido — diferença coberta por outras fontes (saldo inicial, comissão, etc.)")
                else:
                    st.success(f"### ✅ Quitado (~{fmt_b(debt)})")
            else:
                st.caption("Загрузите extrato C6 (BRL + USD) для расчёта.")

            st.divider()
            st.markdown("#### 💼 Nosso lucro do projeto")
            st.caption(f"Período inv: **{opiu_est['invoices_period']}** | DAS pago: **{opiu_est['das_period_paid']}** | DAS pendente: **{opiu_est['das_period_pending']}** ⚠️")

            st.markdown(f"""
| | R$ |
|---|---|
| Comissão (10 invoices, todo período) | {fmt_b(bal_est['our_commission'])} |
| (-) DAS pago (Jul/25 — Jan/26) | -{fmt_b(opiu_est['our_das_paid'])} |
| (-) DAS estimado (Fev+Mar/26) ⏳ | -{fmt_b(opiu_est['our_das_estimated'])} |
| **(-) Total DAS** | **-{fmt_b(opiu_est['our_das'])}** |
| **= Lucro projetado (com DAS estimado)** | **{fmt_b(opiu_est['our_profit_brl'])}** |
| | |
| *Lucro caixa atual (sem DAS pendente)* | *{fmt_b(opiu_est['our_profit_brl_paid_only'])}* |
            """)
            st.caption("⚠️ DAS Fev/Mar 2026 рассчитан по средней ставке от уже оплаченных периодов. Точные данные ждём от бухгалтера.")

            st.markdown(f"""
**Aluguel (USD, отдельно):**
- Pago: ${bal_est['our_rental_paid_usd']:,} ✅
- Devido: ${bal_est['our_rental_pending_usd']:,} ⏳
            """)


    # ──────────────── SERVICES: GANZA ────────────────
    elif sel_project == "GANZA":
        tab_opiu, tab_dds, tab_balance = st.tabs([
            t("tab_opiu", L), t("tab_dds", L), t("tab_balance", L)
        ])
        with tab_opiu:
            st.markdown(f"### GANZA — {t('period', L)}")
            st.info(t("no_data_load", L))
        with tab_dds:
            st.markdown(f"### {t('dds_title', L)} — GANZA")
            st.code("Nubank → C6 BRL (PIX) → C6 USD (Câmbio) → TrafficStars (USD)", language=None)

            c6_ganza = parse_c6_brl()
            c6_usd_g = parse_c6_usd()

            if c6_ganza or c6_usd_g:
                def fmt_g(v):
                    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                if c6_ganza:
                    st.markdown(f"#### C6 BRL ({c6_ganza['date_min']} — {c6_ganza['date_max']})")
                    st.markdown(f"""
| | R$ |
|---|---|
| PIX de Nubank (GANZA) | {fmt_g(c6_ganza['pix_entrada'])} |
| → Convertido em USD | {fmt_g(c6_ganza['cambio_usd'])} |
| Saldo C6 BRL | {fmt_g(c6_ganza['saldo_final'])} |
                    """)

                if c6_usd_g:
                    st.markdown("#### C6 USD → TrafficStars")
                    st.markdown(f"""
| | US$ |
|---|---|
| Entradas (BRL→USD) | ${c6_usd_g['transf_entrada_usd']:,.2f} |
| (-) TrafficStars | -${c6_usd_g['trafficstars_usd']:,.2f} |
| **Saldo USD** | **${c6_usd_g['saldo_usd']:,.2f}** |
| | |
| Pagamentos TS | {len([t for t in c6_usd_g['transactions'] if 'TrafficStars' in t['desc']])}x |
                    """)

                # Calculate effective exchange rate
                if c6_ganza and c6_usd_g and c6_usd_g['transf_entrada_usd'] > 0:
                    avg_rate = c6_ganza['cambio_usd'] / c6_usd_g['transf_entrada_usd']
                    st.metric("Câmbio médio BRL/USD", f"R$ {avg_rate:.4f}")
            else:
                st.info(t("no_data_load", L))

        with tab_balance:
            st.markdown(f"### {t('balance_title', L)} — GANZA")
            c6_bal = parse_c6_brl()
            c6_usd_bal = parse_c6_usd()
            if c6_bal or c6_usd_bal:
                def fmt_gb(v):
                    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.markdown(f"""
| Conta | Saldo |
|---|---|
| C6 BRL | {fmt_gb(c6_bal['saldo_final']) if c6_bal else '—'} |
| C6 USD | {'$' + f"{c6_usd_bal['saldo_usd']:,.2f}" if c6_usd_bal else '—'} |
| | |
| Total BRL convertido | {fmt_gb(c6_bal['cambio_usd']) if c6_bal else '—'} |
| Total USD gasto (TS) | {'$' + f"{c6_usd_bal['trafficstars_usd']:,.2f}" if c6_usd_bal else '—'} |
                """)
            else:
                st.info(t("no_data_load", L))


# ─────────────────────────────────────────────
# PAGE: BANK STATEMENT RULES
# ─────────────────────────────────────────────

elif page == t("page_bank_rules", L):
    from bank_rules_page import render_bank_rules_page

    render_bank_rules_page(L)


# ─────────────────────────────────────────────
# PAGE: SKU MAPPING
# ─────────────────────────────────────────────

elif page == t("page_sku", L):
    from html import escape as html_escape

    from reports import load_sku_titles_from_vendas, load_stock_full

    from dashboard_charts import (
        render_sku_page_top,
        sku_page_streamlit_markdown,
        render_sku_warn_callout,
        render_sku_test_badge,
    )

    st.markdown(sku_page_streamlit_markdown(), unsafe_allow_html=True)

    render_sku_page_top(
        t("sku_title", L),
        t("sku_page_subtitle", L),
        SKU_PREFIXES,
        list(ARTUR_MLBS_FALLBACK),
        {
            "section_mapping": t("current_mapping", L),
            "mlb_fallback": t("mlb_fallback", L),
            "total_label": t("total_label", L),
            "show_all": t("sku_show_all_mlb_ids", L),
        },
    )

    from sku_catalog import load_catalog, save_catalog, normalize_sku, assess_stock_for_project

    # ── Helper: scan unclassified SKUs ──
    def _scan_unclassified_skus():
        vendas_files = list(DATA_DIR.rglob("vendas_ml*.csv"))
        if not vendas_files:
            legacy = BASE_DIR.parent / "vendas"
            vendas_files = sorted(legacy.glob("20260325*.csv"))
        if not vendas_files:
            return None
        latest = vendas_files[-1]
        try:
            df = pd.read_csv(latest, sep=";", skiprows=5, encoding="utf-8")
            unclassified = []
            for _, row in df.iterrows():
                sku = str(row.get("SKU", "")).strip()
                mlb = str(row.get("# de anúncio", "")).strip()
                proj = get_project_by_sku(sku, mlb)
                if proj == "NAO_CLASSIFICADO" and (sku or mlb):
                    unclassified.append({
                        "SKU": sku, "MLB": mlb,
                        "Titulo": str(row.get("Título do anúncio", ""))[:50],
                    })
            if unclassified:
                return pd.DataFrame(unclassified).drop_duplicates()
            return pd.DataFrame()
        except Exception:
            return None

    # ── Helper: render catalog editor for a project ──
    def _render_sku_catalog_for_project(filt_project, tab_key):
        raw_cat = load_catalog()
        cat_rows = []
        for it in raw_cat:
            cat_rows.append({
                "sku": str(it.get("sku", "")),
                "supplier_type": (it.get("supplier_type") or "local").lower(),
                "unit_cost_brl": it.get("unit_cost_brl"),
                "note": str(it.get("note", "") or ""),
            })
        df_cat = pd.DataFrame(cat_rows)
        if df_cat.empty:
            df_cat = pd.DataFrame(columns=["sku", "supplier_type", "unit_cost_brl", "note"])
        df_cat["supplier_type"] = df_cat["supplier_type"].apply(
            lambda x: x if x in ("import", "local") else "local"
        )
        df_cat["__proj"] = df_cat["sku"].apply(lambda s: get_project_by_sku(str(s).strip(), ""))

        filt_all = filt_project is None
        proj_col = t("sku_col_project", L)

        if filt_project:
            stock_block = load_stock_full().get(filt_project, {}) or {}
            by_st = dict(stock_block.get("by_sku") or {})
            st_titles = dict(stock_block.get("sku_titles") or {})
            cat_map = {}
            for _, r in df_cat.iterrows():
                if r["__proj"] != filt_project:
                    continue
                nk = normalize_sku(str(r["sku"]))
                if nk:
                    note_val = r["note"]
                    if pd.isna(note_val):
                        note_val = ""
                    cat_map[nk] = {
                        "sku": str(r["sku"]).strip(),
                        "supplier_type": r["supplier_type"],
                        "unit_cost_brl": r["unit_cost_brl"],
                        "note": str(note_val),
                    }
            vd_titles = load_sku_titles_from_vendas()
            merged_rows = []
            seen_nk = set()
            for sku, qty in sorted(by_st.items(), key=lambda x: str(x[0])):
                nk = normalize_sku(str(sku))
                seen_nk.add(nk)
                tit = (
                    vd_titles.get(nk)
                    or vd_titles.get(str(sku).strip().upper())
                    or st_titles.get(sku)
                    or st_titles.get(str(sku).strip())
                    or ""
                )
                tit = (tit or "").strip()
                if nk in cat_map:
                    c = cat_map[nk]
                    merged_rows.append({
                        "sku": c["sku"],
                        "title": tit,
                        "qty_stock": int(qty),
                        "supplier_type": c["supplier_type"],
                        "unit_cost_brl": c["unit_cost_brl"],
                        "note": c["note"],
                    })
                else:
                    merged_rows.append({
                        "sku": str(sku).strip(),
                        "title": tit,
                        "qty_stock": int(qty),
                        "supplier_type": "local",
                        "unit_cost_brl": None,
                        "note": "",
                    })
            for nk, c in cat_map.items():
                if nk not in seen_nk:
                    merged_rows.append({
                        "sku": c["sku"],
                        "title": "",
                        "qty_stock": 0,
                        "supplier_type": c["supplier_type"],
                        "unit_cost_brl": c["unit_cost_brl"],
                        "note": c["note"],
                    })
            df_show = pd.DataFrame(merged_rows)
            if df_show.empty:
                df_show = pd.DataFrame(columns=[
                    "sku", "title", "qty_stock", "supplier_type", "unit_cost_brl", "note",
                ])
        else:
            df_show = df_cat.copy()
            df_show["title"] = ""
            df_show["qty_stock"] = 0

        keys_before = set()
        for s in df_show["sku"].tolist():
            k = normalize_sku(str(s))
            if k:
                keys_before.add(k)

        base_cols = ["sku", "title", "qty_stock", "supplier_type", "unit_cost_brl", "note"]
        if filt_all:
            disp = df_show[[c for c in base_cols + ["__proj"] if c in df_show.columns]].copy()
            if "__proj" in disp.columns:
                disp = disp.rename(columns={"__proj": proj_col})
        else:
            disp = df_show[base_cols].copy() if not df_show.empty else pd.DataFrame(columns=base_cols)

        col_cfg = {
            "sku": st.column_config.TextColumn(t("sku_col_sku", L), required=True),
            "title": st.column_config.TextColumn(t("sku_col_title", L), disabled=True, width="large"),
            "qty_stock": st.column_config.NumberColumn(
                t("sku_col_qty", L), disabled=True, format="%d", min_value=0,
            ),
            "supplier_type": st.column_config.SelectboxColumn(
                t("sku_col_supplier", L), options=["import", "local"], required=True,
            ),
            "unit_cost_brl": st.column_config.NumberColumn(
                t("sku_col_cost", L), min_value=0.0, format="%.2f",
            ),
            "note": st.column_config.TextColumn(t("sku_col_note", L)),
        }
        if filt_all:
            col_cfg[proj_col] = st.column_config.TextColumn(proj_col, disabled=True)

        edited_df = st.data_editor(
            disp,
            column_config=col_cfg,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key=f"sku_catalog_editor_{tab_key}",
        )

        bcol1, bcol2 = st.columns(2)
        with bcol1:
            do_save = st.button(t("sku_save_catalog", L), key=f"sku_save_{tab_key}")
        with bcol2:
            do_stock = st.button(
                t("sku_add_from_stock", L), key=f"sku_stock_{tab_key}",
            ) if filt_project else False

        # ── Save handler ──
        if do_save:
            keys_after = set()
            for s in edited_df["sku"].tolist():
                k = normalize_sku(str(s))
                if k:
                    keys_after.add(k)

            def _row_to_item(row) -> dict:
                cost = row.get("unit_cost_brl")
                try:
                    cost_f = float(cost) if cost is not None and str(cost) != "" and not pd.isna(cost) else None
                except (TypeError, ValueError):
                    cost_f = None
                if cost_f is not None and cost_f <= 0:
                    cost_f = None
                stp = str(row.get("supplier_type") or "local").lower()
                if stp not in ("import", "local"):
                    stp = "local"
                return {
                    "sku": str(row.get("sku", "")).strip(),
                    "supplier_type": stp,
                    "unit_cost_brl": cost_f,
                    "note": str(row.get("note", "") or ""),
                }

            if filt_all:
                new_items = []
                for _, row in edited_df.iterrows():
                    it = _row_to_item(row)
                    if normalize_sku(it["sku"]):
                        new_items.append(it)
                ok = save_catalog(new_items)
            else:
                full_map = {}
                for it in load_catalog():
                    nk = normalize_sku(str(it.get("sku", "")))
                    if nk:
                        full_map[nk] = {
                            "sku": str(it.get("sku", "")).strip(),
                            "supplier_type": it.get("supplier_type") or "local",
                            "unit_cost_brl": it.get("unit_cost_brl"),
                            "note": str(it.get("note", "") or ""),
                        }
                for _, row in edited_df.iterrows():
                    it = _row_to_item(row)
                    nk = normalize_sku(it["sku"])
                    if nk:
                        full_map[nk] = it
                removed = keys_before - keys_after
                for k in removed:
                    rec = full_map.get(k)
                    if rec and get_project_by_sku(str(rec.get("sku", "")), "") == filt_project:
                        del full_map[k]
                ok = save_catalog(list(full_map.values()))
            if ok:
                st.success(t("sku_saved_ok", L))
                st.rerun()
            else:
                st.error(t("sku_saved_fail", L))

        # ── Stock import handler ──
        if do_stock and filt_project:
            st_map = (load_stock_full().get(filt_project, {}) or {}).get("by_sku") or {}
            if not st_map:
                st.info(t("sku_no_stock", L))
            else:
                full_map = {}
                for it in load_catalog():
                    nk = normalize_sku(str(it.get("sku", "")))
                    if nk:
                        full_map[nk] = {
                            "sku": str(it.get("sku", "")).strip(),
                            "supplier_type": it.get("supplier_type") or "local",
                            "unit_cost_brl": it.get("unit_cost_brl"),
                            "note": str(it.get("note", "") or ""),
                        }
                added = 0
                for sku in st_map:
                    nk = normalize_sku(str(sku))
                    if nk and nk not in full_map:
                        full_map[nk] = {
                            "sku": str(sku).strip(),
                            "supplier_type": "local",
                            "unit_cost_brl": None,
                            "note": "",
                        }
                        added += 1
                if added:
                    if save_catalog(list(full_map.values())):
                        st.success(f"+{added} SKU")
                        st.rerun()
                    else:
                        st.error(t("sku_saved_fail", L))
                else:
                    st.info(t("sku_stock_all_in_catalog", L))

        # ── Stock assessment ──
        if filt_project:
            pmeta = PROJECTS.get(filt_project, {}) or {}
            ast = assess_stock_for_project(
                filt_project,
                (load_stock_full().get(filt_project, {}) or {}).get("by_sku"),
                int(pmeta.get("stock_units_external", 0) or 0),
                pmeta.get("avg_cost_per_unit_brl"),
            )
            if ast.get("missing_units", 0) > 0:
                sks = ast.get("missing_skus") or []
                tail = ", ".join(sks[:25]) + ("…" if len(sks) > 25 else "")
                _wmsg = (
                    f"{t('sku_missing_cost_warn', L)} {ast['missing_units']} "
                    f"{t('total_label', L)}. SKU: {tail}"
                )
                render_sku_warn_callout(_wmsg, fallback_h=min(420, 100 + len(_wmsg) // 4))

    # ── Build tab list: Обзор + per-project (only those with SKU prefixes) + Все SKU ──
    _all_proj_ids = sorted(
        pid for pid, p in PROJECTS.items()
        if p.get("sku_prefixes")  # only projects that have SKU prefixes
    )
    _tab_names = ["📋 Обзор"] + [f"📦 {pid}" for pid in _all_proj_ids] + ["🗂 Все SKU"]
    _sku_tabs = st.tabs(_tab_names)

    # ════════════════════════════════════════════
    # TAB: ОБЗОР (main) — unclassified + test
    # ════════════════════════════════════════════
    with _sku_tabs[0]:
        # ── Unclassified SKUs (auto-scan) ──
        st.markdown(
            f'<div class="sku-section-title">{html_escape(t("check_unclassified", L))}</div>',
            unsafe_allow_html=True,
        )
        _unc_result = _scan_unclassified_skus()
        if _unc_result is None:
            st.info(t("no_vendas", L))
        elif _unc_result.empty:
            render_sku_test_badge(True, t("all_classified", L), fallback_h=56)
        else:
            render_sku_warn_callout(
                f"{t('found_unclassified', L)}: {len(_unc_result)}",
                fallback_h=72,
            )
            st.dataframe(_unc_result, width="stretch", hide_index=True)

        # ── Test classification ──
        st.markdown('<hr class="sku-divider" />', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sku-section-title">{html_escape(t("test_classification", L))}</div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            test_sku = st.text_input(t("sku_label", L), key="sku_test_sku")
            test_mlb = st.text_input(t("mlb_label", L), key="sku_test_mlb")
        if test_sku or test_mlb:
            result = get_project_by_sku(test_sku, test_mlb)
            if result == "NAO_CLASSIFICADO":
                render_sku_test_badge(
                    False,
                    f"{test_sku} / {test_mlb} → {t('not_classified', L)}",
                    fallback_h=64,
                )
            else:
                render_sku_test_badge(
                    True,
                    f"{test_sku} / {test_mlb} → {result}",
                    fallback_h=64,
                )

    # ════════════════════════════════════════════
    # TABs: per-project SKU catalogs
    # ════════════════════════════════════════════
    for _pi, _proj_id in enumerate(_all_proj_ids):
        with _sku_tabs[1 + _pi]:
            _pd = PROJECTS.get(_proj_id, {})
            _ptype = (_pd.get("type") or "—").upper()
            _pdesc = _pd.get("description") or ""
            _ppfx = _pd.get("sku_prefixes") or []
            st.caption(f"**{_proj_id}** · {_ptype} · {_pdesc}")
            if _ppfx:
                st.markdown(
                    f"SKU-префиксы: `{'`, `'.join(_ppfx)}`",
                )
            _render_sku_catalog_for_project(_proj_id, f"proj_{_proj_id}")

    # ════════════════════════════════════════════
    # TAB: Все SKU (full catalog, no filter)
    # ════════════════════════════════════════════
    with _sku_tabs[-1]:
        st.caption(t("sku_catalog_hint", L))
        _render_sku_catalog_for_project(None, "all")


# ─────────────────────────────────────────────
# PAGE: TRANSACTION CLASSIFICATION
# ─────────────────────────────────────────────

elif page == t("page_classify", L):
    import json as json_mod

    # ── NexusBI CSS for classification page ──
    st.markdown("""
    <style>
    .tx-header {
        display: flex; align-items: baseline; justify-content: space-between;
        margin-bottom: 14px; flex-wrap: wrap; gap: 6px;
    }
    .tx-header h1 {
        color: #f0f2ff !important; margin: 0; font-size: 15px; font-weight: 800;
        font-family: 'Nunito Sans', sans-serif;
    }
    .tx-header p { color: #a8b2d1; margin: 0; font-size: 10px; font-weight: 600; }

    .tx-kpi-row {
        display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; margin-bottom: 12px;
    }
    .tx-kpi-card {
        background: #111526; border: 1px solid #1f2540; border-radius: 9px;
        padding: 10px 13px; position: relative; overflow: hidden; text-align: left;
    }
    .tx-kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:2px; }
    .tx-kpi-card.total::before { background: #6272a4; }
    .tx-kpi-card.income::before { background: #22d3a5; }
    .tx-kpi-card.expense::before { background: #ff5757; }
    .tx-kpi-card.pending::before { background: #f59e0b; }
    .tx-kpi-value { font-size: 19px; font-weight: 800; font-family:'DM Mono',monospace; line-height:1; }
    .tx-kpi-label { font-size: 9px; color: #a8b2d1; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700; margin-bottom: 4px; }
    .tx-kpi-sub { font-size: 9px; color: #6272a4; margin-top: 3px; }

    .tx-table-container {
        background: #111526; border: 1px solid #1f2540;
        border-radius: 10px; overflow: hidden; margin-bottom: 10px;
    }
    .tx-table { width: 100%; border-collapse: collapse; font-size: 11px; }
    .tx-table thead th {
        background: #181d30; padding: 8px 10px; text-align: left;
        font-size: 8px; font-weight: 700; color: #6272a4;
        text-transform: uppercase; letter-spacing: 0.8px;
        border-bottom: 1px solid #1f2540; white-space: nowrap;
    }
    .tx-table tbody tr {
        border-bottom: 1px solid rgba(31,37,64,0.5);
        transition: background 0.15s;
    }
    .tx-table tbody tr:hover { background: rgba(255,213,0,0.06); }
    .tx-table tbody tr:last-child { border-bottom: none; }
    .tx-table tbody td {
        padding: 8px 10px; font-size: 11px;
        color: #f0f2ff; vertical-align: middle;
    }

    .tx-indicator {
        width: 32px; height: 32px; border-radius: 8px;
        display: inline-flex; align-items: center;
        justify-content: center; font-size: 1rem;
    }
    .tx-indicator.income { background: rgba(34,211,165,0.15); }
    .tx-indicator.expense { background: rgba(255,87,87,0.15); }
    .tx-indicator.transfer { background: rgba(56,189,248,0.15); }
    .tx-indicator.tax { background: rgba(245,158,11,0.15); }
    .tx-indicator.refund { background: rgba(167,139,250,0.15); }

    .tx-amount { font-weight: 700; font-family: 'DM Mono', monospace; font-size: 11px; }
    .tx-amount.positive { color: #22d3a5; }
    .tx-amount.negative { color: #ff5757; }

    .tx-status {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .tx-status.classified { background: rgba(34,211,165,0.12); color: #22d3a5; }
    .tx-status.unclassified { background: rgba(255,87,87,0.12); color: #ff5757; }
    .tx-status.partial { background: rgba(245,158,11,0.12); color: #f59e0b; }

    .tx-project-badge {
        display: inline-block; padding: 2px 7px; border-radius: 4px;
        font-size: 9px; font-weight: 800; white-space: nowrap;
    }
    .tx-project-badge.artur { background: rgba(56,189,248,0.15); color: #38bdf8; }
    .tx-project-badge.organizadores { background: rgba(52,211,153,0.12); color: #34d399; }
    .tx-project-badge.joom { background: rgba(167,139,250,0.12); color: #a78bfa; }
    .tx-project-badge.ganza { background: rgba(255,213,0,0.1); color: #FFD500; }
    .tx-project-badge.estonia { background: rgba(245,158,11,0.1); color: #f59e0b; }
    .tx-project-badge.none { background: #181d30; color: #6272a4; }

    .tx-category-label { font-size: 11px; color: #a8b2d1; }

    .tx-source-tab {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.3rem 0.7rem; border-radius: 6px;
        font-weight: 700; font-size: 10px; cursor: pointer;
        transition: all 0.2s; border: 1px solid #1f2540;
        font-family: 'Nunito Sans', sans-serif;
    }
    .tx-source-tab.nubank { background: rgba(167,139,250,0.1); color: #a78bfa; border-color: rgba(167,139,250,0.25); }
    .tx-source-tab.c6 { background: rgba(56,189,248,0.1); color: #38bdf8; border-color: rgba(56,189,248,0.25); }
    .tx-source-tab.mp { background: rgba(255,213,0,0.08); color: #FFD500; border-color: rgba(255,213,0,0.2); }

    .tx-month-pill {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 9px; font-weight: 600; background: #181d30;
        color: #6272a4; margin: 0 2px; font-family: 'DM Mono', monospace;
    }
    .tx-month-pill.active {
        background: rgba(255,213,0,0.1); color: #FFD500;
        border: 1px solid rgba(255,213,0,0.25);
    }

    /* ── Responsive ── */
    @media (max-width: 768px) {
        .tx-header h1 { font-size: 13px; }
        .tx-kpi-row { grid-template-columns: repeat(2,1fr); }
        .tx-kpi-card { padding: 8px; }
        .tx-kpi-value { font-size: 16px; }
        .tx-table-container { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .tx-table { min-width: 600px; }
        .tx-table thead th { padding: 6px 5px; font-size: 7px; }
        .tx-table tbody td { padding: 6px 5px; font-size: 10px; }
        .tx-indicator { width: 26px; height: 26px; font-size: 0.85rem; }
        .tx-project-badge { font-size: 8px; padding: 1px 4px; }
    }
    @media (max-width: 480px) {
        .tx-kpi-row { grid-template-columns: 1fr 1fr; }
        .tx-kpi-value { font-size: 14px; }
    }
    </style>
    """, unsafe_allow_html=True)

    # Find all classification JSON files
    class_files = []
    for month in MONTHS:
        for src in ["extrato_nubank", "extrato_c6_brl", "extrato_c6_usd", "extrato_mp"]:
            json_path = DATA_DIR / month / f"{src}_classifications.json"
            csv_path = DATA_DIR / month / f"{src}.csv"
            if json_path.exists() or csv_path.exists():
                class_files.append({
                    "month": month,
                    "source": src,
                    "csv_path": csv_path,
                    "json_path": json_path,
                    "has_csv": csv_path.exists(),
                    "has_json": json_path.exists(),
                })

    # ── Header with real transaction dates ──
    def _parse_tx_dates(cfiles):
        """Extract min/max transaction dates from classification JSONs."""
        import json as _jm
        all_dates = []
        per_source = {}
        for cf in cfiles:
            if not cf["json_path"].exists():
                continue
            try:
                with open(cf["json_path"], "r", encoding="utf-8") as _f:
                    data = _jm.load(_f)
                for tx in data.get("transactions", []):
                    d = str(tx.get("Data", "")).strip()
                    if not d:
                        continue
                    parsed = None
                    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                        try:
                            parsed = datetime.strptime(d[:10], fmt)
                            break
                        except ValueError:
                            continue
                    if parsed:
                        all_dates.append(parsed)
                        per_source.setdefault(cf["source"], []).append(parsed)
            except Exception:
                continue
        return all_dates, per_source

    tx_all_dates, tx_per_source = _parse_tx_dates(class_files)

    src_icons_hdr = {
        "extrato_nubank": "🟣 Nubank",
        "extrato_c6_brl": "🔵 C6 BRL",
        "extrato_c6_usd": "💵 C6 USD",
        "extrato_mp": "🟡 Mercado Pago",
    }

    if class_files and tx_all_dates:
        d_min = min(tx_all_dates).strftime("%d/%m/%Y")
        d_max = max(tx_all_dates).strftime("%d/%m/%Y")

        src_details = []
        for src in sorted(tx_per_source.keys()):
            dates = tx_per_source[src]
            s_min = min(dates).strftime("%d/%m")
            s_max = max(dates).strftime("%d/%m/%Y")
            icon = src_icons_hdr.get(src, src)
            src_details.append(f"{icon}: {s_min} – {s_max}")
        src_detail_str = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(src_details)

        st.markdown(f"""
        <div class="tx-header">
            <h1>{t("classif_title", L)}</h1>
            <p>{t("classif_header_range", L).format(d_min=d_min, d_max=d_max, n_files=len(class_files), src=src_detail_str)}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="tx-header">
            <h1>{t("classif_title", L)}</h1>
            <p>{t("classif_header_default", L)}</p>
        </div>
        """, unsafe_allow_html=True)

    if not class_files:
        st.info(t("classif_no_bank_files", L))
    else:
        # ── Load all transactions for global stats & filtering ──
        all_txs = []
        file_meta = {}
        pending_files = []
        for cf in class_files:
            src_icon = {
                "extrato_nubank": "🟣",
                "extrato_c6_brl": "🔵",
                "extrato_c6_usd": "💵",
                "extrato_mp": "🟡",
            }.get(cf["source"], "📄")
            cf["icon"] = src_icon

            if not cf["has_json"]:
                pending_files.append({**cf, "issue": t("classif_issue_not_classified", L)})
                continue
            try:
                with open(cf["json_path"], "r", encoding="utf-8") as f:
                    data = json_mod.load(f)
            except Exception:
                continue

            txs = data.get("transactions", [])
            splits = data.get("full_express_splits", {})
            fkey = f"{cf['month']}_{cf['source']}"
            file_meta[fkey] = {"cf": cf, "data": data, "splits": splits}

            for tx in txs:
                tx["_month"] = cf["month"]
                tx["_source"] = cf["source"]
                tx["_fkey"] = fkey
                tx["_icon"] = src_icon
            all_txs.extend(txs)

            # Check for pending issues
            def in_split(t_):
                cat = t_.get("Категория", "")
                label_lo = str(t_.get("Класс.", "")).lower()
                return (cat == "fulfillment" or "fatura ml" in label_lo
                        or "retido" in label_lo or "devolu" in label_lo or "reclamaç" in label_lo)

            unc = sum(1 for t_ in txs if t_.get("Категория") == "uncategorized" and not in_split(t_))
            no_proj = sum(1 for t_ in txs
                          if (not t_.get("Проект") or t_.get("Проект") in ("❓", "—", ""))
                          and not in_split(t_) and t_.get("Категория") != "uncategorized")

            group_totals = {"fulfillment": 0, "fatura_ml": 0, "retido": 0, "devolucoes": 0}
            for t_ in txs:
                cat = t_.get("Категория", "")
                label_lo = str(t_.get("Класс.", "")).lower()
                try:
                    val_abs = abs(float(t_.get("Valor", 0) or 0))
                except (ValueError, TypeError):
                    val_abs = 0
                if cat == "fulfillment":
                    group_totals["fulfillment"] += val_abs
                elif "fatura ml" in label_lo:
                    group_totals["fatura_ml"] += val_abs
                elif "retido" in label_lo:
                    group_totals["retido"] += val_abs
                elif "devolu" in label_lo or "reclamaç" in label_lo:
                    group_totals["devolucoes"] += val_abs

            pending_groups = []
            for gk, gtotal in group_totals.items():
                if gtotal == 0:
                    continue
                grp_data = splits.get(gk, {})
                if isinstance(grp_data, dict) and "split" in grp_data:
                    split_sum = sum(grp_data.get("split", {}).values())
                else:
                    split_sum = 0
                if abs(split_sum - gtotal) > 0.01:
                    pending_groups.append(gk)

            issues = []
            if unc > 0:
                issues.append(t("classif_issue_unc", L).format(n=unc))
            if no_proj > 0:
                issues.append(t("classif_issue_no_proj", L).format(n=no_proj))
            if pending_groups:
                grp_names = {
                    "fulfillment": t("classif_group_fulfillment", L),
                    "fatura_ml": t("classif_group_fatura_ml", L),
                    "retido": t("classif_group_retido", L),
                    "devolucoes": t("classif_group_devolucoes", L),
                }
                issues.append(t("classif_issue_splits", L).format(names=", ".join(grp_names[g] for g in pending_groups)))
            if issues:
                pending_files.append({**cf, "issue": " · ".join(issues), "data": data})

        # ── KPI cards ──
        total_count = len(all_txs)
        total_income = sum(float(t.get("Valor", 0) or 0) for t in all_txs if float(t.get("Valor", 0) or 0) > 0)
        total_expense = sum(float(t.get("Valor", 0) or 0) for t in all_txs if float(t.get("Valor", 0) or 0) < 0)
        total_unclassified = sum(1 for t in all_txs if t.get("Категория") == "uncategorized")

        def _kpi_brl(v):
            s = f"{abs(v):,.0f}"
            return s.replace(",", ".")

        st.markdown(f"""
        <div class="tx-kpi-row">
            <div class="tx-kpi-card total">
                <div class="tx-kpi-label">{t("classif_kpi_tx", L)}</div>
                <div class="tx-kpi-value" style="color:#f0f2ff">{total_count}</div>
                <div class="tx-kpi-sub">{len(class_files)} {t("classif_kpi_sources", L)}</div>
            </div>
            <div class="tx-kpi-card income">
                <div class="tx-kpi-label">{t("classif_kpi_income", L)}</div>
                <div class="tx-kpi-value" style="color:#22d3a5">+R$ {_kpi_brl(total_income)}</div>
            </div>
            <div class="tx-kpi-card expense">
                <div class="tx-kpi-label">{t("classif_kpi_expense", L)}</div>
                <div class="tx-kpi-value" style="color:#ff5757">&minus;R$ {_kpi_brl(total_expense)}</div>
            </div>
            <div class="tx-kpi-card pending">
                <div class="tx-kpi-label">{t("classif_kpi_unclassified", L)}</div>
                <div class="tx-kpi-value" style="color:#f59e0b">{total_unclassified}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Pending warnings ──
        if pending_files:
            st.error(t("classif_pending_header", L).format(n=len(pending_files)))
            for pf in pending_files:
                st.markdown(f"- {pf['icon']} **{pf['month']}** — {DATA_SOURCES.get(pf['source'], {}).get('name', pf['source'])}: {pf['issue']}")

        # ── Filters row ──
        _fall = t("classif_all", L)
        _fstat_class = t("classif_status_classified", L)
        _fstat_uncat = t("classif_status_no_category", L)
        _fstat_nop = t("classif_status_no_project", L)
        filter_cols = st.columns([2, 1, 1, 1])
        with filter_cols[0]:
            search_q = st.text_input(
                t("classif_search", L), placeholder=t("classif_search_ph", L), label_visibility="collapsed")
        with filter_cols[1]:
            available_months = sorted(set(cf["month"] for cf in class_files), reverse=True)
            sel_month = st.selectbox(t("classif_period", L), [_fall] + available_months, label_visibility="collapsed")
        with filter_cols[2]:
            src_labels = {
                "extrato_nubank": "🟣 Nubank",
                "extrato_c6_brl": "🔵 C6 BRL",
                "extrato_c6_usd": "💵 C6 USD",
                "extrato_mp": "🟡 Mercado Pago",
            }
            available_sources = sorted(set(cf["source"] for cf in class_files))
            sel_source = st.selectbox(
                t("classif_source", L),
                [_fall] + [src_labels.get(s, s) for s in available_sources],
                label_visibility="collapsed",
            )
        with filter_cols[3]:
            status_filter = st.selectbox(
                t("classif_status", L),
                [_fall, _fstat_class, _fstat_uncat, _fstat_nop],
                label_visibility="collapsed",
            )

        # ── Apply filters ──
        filtered_txs = all_txs.copy()
        if sel_month != _fall:
            filtered_txs = [t for t in filtered_txs if t["_month"] == sel_month]
        if sel_source != _fall:
            # Map display name back to source key
            src_key_map = {v: k for k, v in src_labels.items()}
            src_key = src_key_map.get(sel_source, sel_source)
            filtered_txs = [t for t in filtered_txs if t["_source"] == src_key]
        if status_filter == _fstat_class:
            filtered_txs = [t for t in filtered_txs if t.get("Категория") != "uncategorized"]
        elif status_filter == _fstat_uncat:
            filtered_txs = [t for t in filtered_txs if t.get("Категория") == "uncategorized"]
        elif status_filter == _fstat_nop:
            filtered_txs = [t for t in filtered_txs if not t.get("Проект") or t.get("Проект") in ("❓", "—", "")]
        if search_q:
            sq = search_q.lower()
            filtered_txs = [t for t in filtered_txs if
                            sq in str(t.get("Descrição", "")).lower() or
                            sq in str(t.get("Класс.", "")).lower() or
                            sq in str(t.get("Проект", "")).lower() or
                            sq in str(t.get("Категория", "")).lower()]

        st.caption(t("classif_shown", L).format(n=len(filtered_txs), total=total_count))

        # ── Build HTML table ──
        def _cat_indicator(cat, val=0):
            """Return colored indicator based on category AND actual value direction."""
            cat_icons = {
                "income": "↓", "expense": "↑", "internal_transfer": "⇄",
                "fx": "💱", "tax": "📋", "refund": "↩", "supplier": "📦",
                "fulfillment": "🚚", "shipping": "📮", "ads": "📣",
                "dividends": "💎", "personal": "👤", "accounting": "🧾",
                "bank_fee": "🏦", "utilities": "💡", "software": "💻",
                "uncategorized": "❓",
            }
            icon = cat_icons.get(cat, "•")
            # Color by actual money direction
            try:
                v = float(val or 0)
            except (ValueError, TypeError):
                v = 0
            if cat == "internal_transfer" or cat == "fx":
                cls = "transfer"
            elif cat == "uncategorized":
                cls = "refund"
            elif v > 0:
                cls = "income"
            else:
                cls = "expense"
            return f'<span class="tx-indicator {cls}">{icon}</span>'

        def _project_badge(proj):
            if not proj or proj in ("❓", "—", "", None):
                return '<span class="tx-project-badge none">—</span>'
            cls = proj.lower().replace(" ", "")
            return f'<span class="tx-project-badge {cls}">{proj}</span>'

        def _status_badge(cat, proj=""):
            if cat == "uncategorized":
                return f'<span class="tx-status unclassified">{html_escape.escape(t("classif_kpi_unclassified", L))}</span>'
            if not proj or proj in ("❓", "—", ""):
                return f'<span class="tx-status partial">{html_escape.escape(t("classif_status_no_project", L))}</span>'
            return f'<span class="tx-status classified">{html_escape.escape(t("classif_badge_ok", L))}</span>'

        def _fmt_brl_html(v):
            """Format number as BRL: 1.234,56"""
            s = f"{abs(v):,.2f}"
            # swap , and . for BRL: 1,234.56 → 1.234,56
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
            return s

        def _amount_html(val):
            try:
                v = float(val or 0)
            except (ValueError, TypeError):
                return "—"
            cls = "positive" if v > 0 else "negative"
            sign = "+" if v > 0 else "-"
            return f'<span class="tx-amount {cls}">{sign}R$ {_fmt_brl_html(v)}</span>'

        # Paginate
        PAGE_SIZE = 50
        total_pages = max(1, (len(filtered_txs) + PAGE_SIZE - 1) // PAGE_SIZE)
        if "tx_page" not in st.session_state:
            st.session_state.tx_page = 0
        if st.session_state.tx_page >= total_pages:
            st.session_state.tx_page = 0

        page_start = st.session_state.tx_page * PAGE_SIZE
        page_txs = filtered_txs[page_start:page_start + PAGE_SIZE]

        # Render table via st.components.v1.html for reliable HTML rendering
        import html as html_mod
        import streamlit.components.v1 as components

        rows_html_parts = []
        for tx in page_txs:
            cat = tx.get("Категория", "uncategorized")
            val = tx.get("Valor", 0)
            desc_raw = html_mod.escape(str(tx.get("Descrição", ""))[:55])
            proj = str(tx.get("Проект", ""))
            date_val = html_mod.escape(str(tx.get("Data", ""))[:16])
            label = html_mod.escape(str(tx.get("Класс.", ""))[:45])
            source_icon = tx.get("_icon", "")
            month = tx.get("_month", "")

            desc_show = desc_raw if desc_raw and desc_raw != "nan" else label

            rows_html_parts.append(
                f"<tr>"
                f"<td>{_cat_indicator(cat, val)}</td>"
                f"<td><span class='tx-month-pill'>{month}</span> {source_icon}</td>"
                f"<td><div style='font-size:11px;font-weight:600;color:#f0f2ff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px'>{desc_show}</div><div style='font-size:9px;color:#6272a4;font-family:DM Mono,monospace'>{date_val}</div></td>"
                f"<td class='tx-category-label'>{label}</td>"
                f"<td>{_amount_html(val)}</td>"
                f"<td>{_project_badge(proj)}</td>"
                f"<td>{_status_badge(cat, proj)}</td>"
                f"</tr>"
            )

        rows_joined = "\n".join(rows_html_parts)
        table_height = min(80 + len(page_txs) * 62, 3200)

        _th_src = t("classif_source", L)
        _th_desc = t("description", L)
        _th_class = t("classif_th_class", L)
        _th_amt = t("classif_th_amount", L)
        _th_proj = t("project", L)
        _th_stat = t("classif_status", L)

        components.html(f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap');
            body {{ margin:0; padding:0; font-family:'Nunito Sans',sans-serif; background:#0b0e1a; color:#f0f2ff; }}
            .tx-table-container {{
                background:#111526; border:1px solid #1f2540;
                border-radius:10px; overflow:hidden;
            }}
            .tx-table {{ width:100%; border-collapse:collapse; font-size:11px; }}
            .tx-table thead th {{
                background:#181d30; padding:8px 10px; text-align:left;
                font-size:8px; font-weight:700; color:#6272a4;
                text-transform:uppercase; letter-spacing:0.8px;
                border-bottom:1px solid #1f2540; position:sticky; top:0; z-index:1;
                white-space:nowrap;
            }}
            .tx-table tbody tr {{ border-bottom:1px solid rgba(31,37,64,0.5); transition:background 0.15s; }}
            .tx-table tbody tr:hover {{ background:rgba(255,213,0,0.06); }}
            .tx-table tbody tr:last-child {{ border-bottom:none; }}
            .tx-table tbody td {{ padding:8px 10px; font-size:11px; color:#f0f2ff; vertical-align:middle; }}
            .tx-indicator {{
                width:32px; height:32px; border-radius:8px;
                display:inline-flex; align-items:center; justify-content:center; font-size:1rem;
            }}
            .tx-indicator.income {{ background:rgba(34,211,165,0.15); }}
            .tx-indicator.expense {{ background:rgba(255,87,87,0.15); }}
            .tx-indicator.transfer {{ background:rgba(56,189,248,0.15); }}
            .tx-indicator.tax {{ background:rgba(245,158,11,0.15); }}
            .tx-indicator.refund {{ background:rgba(167,139,250,0.15); }}
            .tx-amount {{ font-weight:700; font-family:'DM Mono',monospace; font-size:11px; }}
            .tx-amount.positive {{ color:#22d3a5; }}
            .tx-amount.negative {{ color:#ff5757; }}
            .tx-status {{
                display:inline-block; padding:2px 8px; border-radius:4px;
                font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px;
            }}
            .tx-status.classified {{ background:rgba(34,211,165,0.12); color:#22d3a5; }}
            .tx-status.unclassified {{ background:rgba(255,87,87,0.12); color:#ff5757; }}
            .tx-status.partial {{ background:rgba(245,158,11,0.12); color:#f59e0b; }}
            .tx-project-badge {{
                display:inline-block; padding:2px 7px; border-radius:4px;
                font-size:9px; font-weight:800; white-space:nowrap;
            }}
            .tx-project-badge.artur {{ background:rgba(56,189,248,0.15); color:#38bdf8; }}
            .tx-project-badge.organizadores {{ background:rgba(52,211,153,0.12); color:#34d399; }}
            .tx-project-badge.joom {{ background:rgba(167,139,250,0.12); color:#a78bfa; }}
            .tx-project-badge.ganza {{ background:rgba(255,213,0,0.1); color:#FFD500; }}
            .tx-project-badge.estonia {{ background:rgba(245,158,11,0.1); color:#f59e0b; }}
            .tx-project-badge.none {{ background:#181d30; color:#6272a4; }}
            .tx-month-pill {{
                display:inline-block; padding:2px 8px; border-radius:4px;
                font-size:9px; font-weight:600; background:#181d30;
                color:#6272a4; font-family:'DM Mono',monospace;
            }}
            .tx-category-label {{ font-size:11px; color:#a8b2d1; }}

            @media (max-width: 768px) {{
                .tx-table-container {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
                .tx-table {{ min-width:600px; }}
                .tx-table thead th {{ padding:6px 5px; font-size:7px; }}
                .tx-table tbody td {{ padding:6px 5px; font-size:10px; }}
                .tx-indicator {{ width:26px; height:26px; font-size:0.85rem; }}
                .tx-project-badge {{ font-size:8px; padding:1px 4px; }}
            }}
        </style>
        <div class="tx-table-container">
            <table class="tx-table">
                <thead>
                    <tr>
                        <th style="width:46px"></th>
                        <th>{html_mod.escape(_th_src)}</th>
                        <th>{html_mod.escape(_th_desc)}</th>
                        <th>{html_mod.escape(_th_class)}</th>
                        <th>{html_mod.escape(_th_amt)}</th>
                        <th>{html_mod.escape(_th_proj)}</th>
                        <th>{html_mod.escape(_th_stat)}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_joined}
                </tbody>
            </table>
        </div>
        """, height=table_height, scrolling=True)

        # Pagination controls
        if total_pages > 1:
            pc1, pc2, pc3 = st.columns([1, 2, 1])
            with pc1:
                if st.button(t("classif_pg_prev", L), disabled=st.session_state.tx_page == 0, key="tx_prev"):
                    st.session_state.tx_page -= 1
                    st.rerun()
            with pc2:
                st.markdown(
                    "<div style='text-align:center;padding-top:0.5rem;color:#6272a4;font-size:10px;font-family:DM Mono,monospace'>"
                    f"{html_escape.escape(t('classif_pg_info', L).format(cur=st.session_state.tx_page + 1, total=total_pages))}"
                    "</div>",
                    unsafe_allow_html=True,
                )
            with pc3:
                if st.button(t("classif_btn_next", L), disabled=st.session_state.tx_page >= total_pages - 1, key="tx_next"):
                    st.session_state.tx_page += 1
                    st.rerun()

        # ═══════════════════════════════════════════
        # EDITING SECTION (per file, as before)
        # ═══════════════════════════════════════════
        st.divider()
        st.markdown(f"### {t('classif_edit_header', L)}")

        for cf in class_files:
            month = cf["month"]
            src = cf["source"]
            label = DATA_SOURCES.get(src, {}).get("name", src)
            fkey = f"{month}_{src}"

            with st.expander(f"{cf.get('icon', '📄')} **{month}** — {label}", expanded=False):
                if not cf["has_json"]:
                    st.warning(t("classif_no_json", L))
                    continue

                meta = file_meta.get(fkey)
                if not meta:
                    continue

                data = meta["data"]
                txs = data.get("transactions", [])
                splits = meta["splits"]

                if not txs:
                    st.info(t("up_no_tx", L))
                    continue

                df_existing = pd.DataFrame(txs)

                # Status metrics
                uncategorized = df_existing[df_existing["Категория"] == "uncategorized"]
                col1, col2, col3 = st.columns(3)
                col1.metric("Всего", len(df_existing))
                col2.metric("Класс.", len(df_existing) - len(uncategorized))
                col3.metric("Некласс.", len(uncategorized))

                # Editable table
                project_options = list(load_projects().keys()) + ["—"]
                category_options = [
                    "internal_transfer", "income", "expense", "supplier", "fulfillment",
                    "shipping", "ads", "tax", "accounting", "salary", "freelancer",
                    "rent", "utilities", "software", "bank_fee", "fx", "loan",
                    "investment", "refund", "dividends", "personal", "uncategorized",
                ]

                edited = st.data_editor(
                    df_existing,
                    width="stretch",
                    hide_index=True,
                    num_rows="fixed",
                    column_config={
                        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Категория": st.column_config.SelectboxColumn("Категория", options=category_options, required=True),
                        "Проект": st.column_config.SelectboxColumn("Проект", options=project_options, required=False),
                    },
                    key=f"persistent_class_{month}_{src}",
                )

                # Grouped splits (Full Express / Fatura ML / Retido / Devoluções)
                ecom_projects = [pid for pid, p in load_projects().items() if p.get("type") in ("ecom", "hybrid")]

                def split_group_p(row):
                    cat = row.get("Категория", "")
                    label_lo = str(row.get("Класс.", "")).lower()
                    if cat == "fulfillment":
                        return "fulfillment"
                    if "fatura ml" in label_lo:
                        return "fatura_ml"
                    if "retido" in label_lo:
                        return "retido"
                    if "devolu" in label_lo or "reclamaç" in label_lo:
                        return "devolucoes"
                    return None

                edited_grp_p = edited.copy()
                edited_grp_p["__group"] = edited_grp_p.apply(split_group_p, axis=1)
                groups_df_p = edited_grp_p[edited_grp_p["__group"].notna()]

                tx_splits_persist = {}
                if len(groups_df_p) > 0:
                    st.markdown("##### Разделение между проектами")
                    group_labels_p = {
                        "fulfillment": "📦 Full Express / Fulfillment",
                        "fatura_ml": "📋 Fatura ML",
                        "retido": "🔒 Dinheiro retido ML",
                        "devolucoes": "↩️ Devoluções e Reclamações ML",
                    }

                    for group_key in ["fulfillment", "fatura_ml", "retido", "devolucoes"]:
                        grp = groups_df_p[groups_df_p["__group"] == group_key]
                        if len(grp) == 0:
                            continue
                        title = group_labels_p[group_key]
                        total_abs = float(grp["Valor"].abs().sum())
                        existing = splits.get(group_key, {}) if isinstance(splits.get(group_key), dict) else {}
                        existing_split = existing.get("split", {}) if "split" in existing else existing

                        with st.expander(f"{title} — **R$ {total_abs:,.2f}** ({len(grp)} операций)", expanded=True):
                            cols = st.columns(len(ecom_projects))
                            sv = {}
                            for i, proj in enumerate(ecom_projects):
                                with cols[i]:
                                    v = st.number_input(
                                        proj,
                                        min_value=0.0,
                                        value=float(existing_split.get(proj, 0)),
                                        step=0.01,
                                        format="%.2f",
                                        key=f"persist_grp_{month}_{src}_{group_key}_{proj}",
                                    )
                                    sv[proj] = v
                            total = sum(sv.values())
                            if abs(total - total_abs) < 0.01:
                                st.success(t("up_split_done", L).format(v=f"{total:,.2f}"))
                            elif total == 0:
                                st.info(t("up_split_not", L).format(v=f"{total_abs:,.2f}"))
                            else:
                                st.warning(t("up_split_remain", L).format(v=f"{total_abs - total:,.2f}"))
                            tx_splits_persist[group_key] = {
                                "total": total_abs,
                                "split": sv,
                                "qtd": len(grp),
                            }

                # Save button
                if st.button("💾 Сохранить изменения", key=f"save_persist_{month}_{src}"):
                    new_data = {
                        **data,
                        "transactions": edited.to_dict("records"),
                        "full_express_splits": tx_splits_persist,
                    }
                    with open(cf["json_path"], "w", encoding="utf-8") as f:
                        json_mod.dump(new_data, f, indent=2, ensure_ascii=False, default=str)
                    st.success(t("up_saved_file", L).format(f=cf['json_path'].name))
                    st.rerun()


# ─────────────────────────────────────────────
# PAGE: PROJECT MANAGEMENT
# ─────────────────────────────────────────────

elif page == t("page_projects", L):
    # ── Inject NexusBI projects CSS ──
    st.markdown(_nx_projects_page_css(
        bg=_bg, bg2=_bg2, bg3=_bg3, border=_border, text=_text, text2=_text2, text3=_text3,
        yellow="#FFD500", green="#22d3a5", red="#ff5757", blue="#38bdf8",
        purple="#a78bfa", amber="#f59e0b", ydim="rgba(255,213,0,0.10)",
    ), unsafe_allow_html=True)

    projects_now = load_projects()

    # ── Hero header ──
    st.markdown(f"""
<div class="nx-proj-root">
  <div class="nx-proj-hero">
    <div class="nx-proj-hero-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
    </div>
    <div class="nx-proj-hero-titles">
      <div class="nx-proj-title">{html_escape.escape(t("projects_title", L))}</div>
      <div class="nx-proj-sub">{html_escape.escape(t("existing_projects", L))} · NexusBI</div>
    </div>
  </div>
  <div class="nx-proj-divider"></div>
</div>
""", unsafe_allow_html=True)

    # ── Stats bar ──
    _total_proj = len(projects_now)
    _by_type = {"ecom": 0, "services": 0, "hybrid": 0}
    _by_status = {"approved": 0, "pending": 0}
    _rental_sum_monthly = 0
    for _pid, _pd in projects_now.items():
        _pt = (_pd.get("type") or "ecom").lower()
        _by_type[_pt] = _by_type.get(_pt, 0) + 1
        _ps = (_pd.get("status") or "pending").lower()
        _by_status[_ps] = _by_status.get(_ps, 0) + 1
        _r = _pd.get("rental") if isinstance(_pd.get("rental"), dict) else None
        if _r and get_compensation_mode(_pd) == "rental":
            _rate = _r.get("rate_usd") or 0
            _per = (_r.get("period") or "month").lower()
            if _per == "quarter":
                _rental_sum_monthly += _rate / 3
            elif _per == "year":
                _rental_sum_monthly += _rate / 12
            else:
                _rental_sum_monthly += _rate
    st.markdown(f"""
<div class="nx-proj-root">
  <div class="nx-stats-bar">
    <div class="nx-stat-card">
      <div class="nx-stat-lbl">Всего проектов</div>
      <div class="nx-stat-val">{_total_proj}</div>
      <div class="nx-stat-detail">активных</div>
    </div>
    <div class="nx-stat-card">
      <div class="nx-stat-lbl">По типу</div>
      <div class="nx-stat-val" style="font-size:14px;margin-top:4px">
        <span class="nx-stat-dot" style="background:#38bdf8"></span>{_by_type.get("ecom",0)}
        <span class="nx-stat-dot" style="background:#a78bfa;margin-left:8px"></span>{_by_type.get("services",0)}
        <span class="nx-stat-dot" style="background:#f59e0b;margin-left:8px"></span>{_by_type.get("hybrid",0)}
      </div>
      <div class="nx-stat-detail">
        <span class="nx-stat-dot" style="background:#38bdf8"></span>ecom ·
        <span class="nx-stat-dot" style="background:#a78bfa"></span>services ·
        <span class="nx-stat-dot" style="background:#f59e0b"></span>hybrid
      </div>
    </div>
    <div class="nx-stat-card">
      <div class="nx-stat-lbl">По статусу</div>
      <div class="nx-stat-val" style="font-size:16px;margin-top:2px">
        <span class="nx-stat-dot" style="background:#22d3a5"></span>{_by_status.get("approved",0)}
        <span class="nx-stat-dot" style="background:#ff5757;margin-left:12px"></span>{_by_status.get("pending",0)}
      </div>
      <div class="nx-stat-detail">
        <span class="nx-stat-dot" style="background:#22d3a5"></span>approved ·
        <span class="nx-stat-dot" style="background:#ff5757"></span>pending
      </div>
    </div>
    <div class="nx-stat-card">
      <div class="nx-stat-lbl">Rental-доход</div>
      <div class="nx-stat-val">${_rental_sum_monthly:,.0f}</div>
      <div class="nx-stat-detail">в месяц (суммарно)</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Search / filter ──
    _fc1, _fc2 = st.columns([3, 1])
    with _fc1:
        _proj_search = st.text_input(
            "🔍",
            placeholder=t("projects_title", L),
            label_visibility="collapsed",
            key="proj_search_q",
        )
    with _fc2:
        _proj_type_filter = st.selectbox(
            t("project_type_sel", L),
            ["all", "ecom", "services", "hybrid"],
            format_func=lambda x: "Все типы" if x == "all" else x.upper(),
            label_visibility="collapsed",
            key="proj_type_filter",
        )

    # ── Section label ──
    _filtered_projects = {}
    _sq = (_proj_search or "").strip().lower()
    for _fpid, _fpd in projects_now.items():
        if _proj_type_filter != "all" and (_fpd.get("type") or "ecom").lower() != _proj_type_filter:
            continue
        if _sq and _sq not in _fpid.lower() and _sq not in (_fpd.get("description") or "").lower():
            continue
        _filtered_projects[_fpid] = _fpd

    st.markdown(
        f'<div class="nx-proj-root"><div class="nx-proj-section">'
        f'{html_escape.escape(t("existing_projects", L))} '
        f'<span class="nx-sec-count">{len(_filtered_projects)}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    if not _filtered_projects:
        st.info(t("up_no_projects", L))

    for pid, pdata in _filtered_projects.items():
        ptype = (pdata.get("type") or "—").upper()
        edit_key = f"edit_proj_{pid}"
        with st.expander(f"**{pid}** — {ptype} | {pdata.get('description', '')}"):
            if st.session_state.get(edit_key):
                st.markdown(
                    f'<div class="nx-edit-header">'
                    f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                    f'stroke-width="2.5" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 '
                    f'2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 '
                    f'9.5-9.5z"/></svg>'
                    f'<span class="nx-edit-header-label">{html_escape.escape(t("edit_project_section", L))} · {html_escape.escape(pid)}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                rental_d = pdata.get("rental") if isinstance(pdata.get("rental"), dict) else {}
                types_opts = ["ecom", "services", "hybrid"]
                cur_type = pdata.get("type") or "ecom"
                ti = types_opts.index(cur_type) if cur_type in types_opts else 0
                stat_opts = ["pending", "approved"]
                cur_st = pdata.get("status") or "pending"
                si = stat_opts.index(cur_st) if cur_st in stat_opts else 0
                comp_opts = ["profit_share", "rental"]
                eff_mode = get_compensation_mode(pdata)
                cmode_idx = comp_opts.index(eff_mode) if eff_mode in comp_opts else 0
                ps_raw = pdata.get("profit_share_pct")
                try:
                    pct0 = float(ps_raw) if ps_raw is not None else 0.0
                except (TypeError, ValueError):
                    pct0 = 0.0
                rate0 = float(rental_d.get("rate_usd") or 0)
                per0 = rental_d.get("period") or "quarter"
                peri = 0 if per0 == "quarter" else 1

                # Вне формы: иначе Streamlit не перерисует условные поля до Submit
                st.selectbox(
                    t("compensation_mode_label", L),
                    options=comp_opts,
                    index=cmode_idx,
                    format_func=lambda k: t(f"compensation_mode_{k}", L),
                    key=f"ef_mode_{pid}",
                )
                curr_comp = st.session_state.get(f"ef_mode_{pid}", eff_mode)
                if curr_comp not in comp_opts:
                    curr_comp = eff_mode

                with st.form(f"proj_edit_form_{pid}"):
                    ef_type = st.selectbox(
                        t("project_type_sel", L), types_opts, index=ti, key=f"ef_type_{pid}",
                    )
                    ef_desc = st.text_input(
                        t("project_desc", L), value=pdata.get("description") or "", key=f"ef_desc_{pid}",
                    )
                    ef_stat = st.selectbox(
                        t("project_status_label", L), stat_opts, index=si, key=f"ef_stat_{pid}",
                    )
                    no_launch = st.checkbox(
                        t("project_launch_date_none", L),
                        value=_parse_project_date(pdata.get("launch_date")) is None,
                        key=f"ef_no_launch_{pid}",
                    )
                    if not no_launch:
                        st.date_input(
                            t("project_launch_date_label", L),
                            value=_parse_project_date(pdata.get("launch_date")) or date.today(),
                            format="DD/MM/YYYY",
                            key=f"ef_launch_{pid}",
                            help=t("project_launch_date_help", L),
                        )
                    ef_sku = st.text_input(
                        t("project_skus", L),
                        value=", ".join(pdata.get("sku_prefixes") or []),
                        key=f"ef_sku_{pid}",
                    )
                    rp_a, rp_b = _parse_report_period_bounds(pdata.get("report_period"))
                    no_rp = st.checkbox(
                        t("project_report_period_none", L),
                        value=rp_a is None and rp_b is None,
                        key=f"ef_no_rp_{pid}",
                    )
                    if not no_rp:
                        c_rp1, c_rp2 = st.columns(2)
                        with c_rp1:
                            st.date_input(
                                t("project_report_period_from", L),
                                value=rp_a or date.today(),
                                format="DD/MM/YYYY",
                                key=f"ef_rp_start_{pid}",
                            )
                        with c_rp2:
                            st.date_input(
                                t("project_report_period_to", L),
                                value=rp_b or rp_a or date.today(),
                                format="DD/MM/YYYY",
                                key=f"ef_rp_end_{pid}",
                            )
                    lr_d = _parse_project_date(pdata.get("last_report"))
                    no_lr = st.checkbox(
                        t("project_last_report_none", L),
                        value=lr_d is None,
                        key=f"ef_no_lr_{pid}",
                    )
                    if not no_lr:
                        st.date_input(
                            t("project_last_report_label", L),
                            value=lr_d or date.today(),
                            format="DD/MM/YYYY",
                            key=f"ef_lr_{pid}",
                        )
                    nc_d = _parse_project_date(pdata.get("next_close"))
                    no_nc = st.checkbox(
                        t("project_next_close_none", L),
                        value=nc_d is None,
                        key=f"ef_no_nc_{pid}",
                    )
                    if not no_nc:
                        st.date_input(
                            t("project_next_close_label", L),
                            value=nc_d or date.today(),
                            format="DD/MM/YYYY",
                            key=f"ef_nc_{pid}",
                        )
                    if curr_comp == "profit_share":
                        st.number_input(
                            t("profit_share_pct_label", L),
                            min_value=0.0,
                            max_value=100.0,
                            value=min(100.0, max(0.0, pct0)),
                            step=0.5,
                            help=t("profit_share_pct_help", L),
                            key=f"ef_pct_{pid}",
                        )
                    elif curr_comp == "rental":
                        st.number_input(
                            t("rental_rate_label", L),
                            min_value=0.0,
                            value=rate0,
                            step=50.0,
                            key=f"ef_rr_{pid}",
                        )
                        st.selectbox(
                            t("rental_period_label", L),
                            ["quarter", "month"],
                            index=peri,
                            key=f"ef_rper_{pid}",
                        )
                        st.text_input(
                            t("rental_note_label", L),
                            value=str(rental_d.get("note") or ""),
                            key=f"ef_rnote_{pid}",
                        )
                        no_rentpay = st.checkbox(
                            t("rental_next_payment_date_none", L),
                            value=_parse_project_date(rental_d.get("next_payment_date")) is None,
                            key=f"ef_no_rentpay_{pid}",
                        )
                        if not no_rentpay:
                            st.date_input(
                                t("rental_next_payment_date_label", L),
                                value=_parse_project_date(rental_d.get("next_payment_date")) or date.today(),
                                format="DD/MM/YYYY",
                                key=f"ef_rentpay_{pid}",
                                help=t("rental_next_payment_date_help", L),
                            )
                        st.caption(t("rental_payments_json_hint", L))
                    ef_mlb = st.text_area(
                        t("project_mlb_field_label", L),
                        value=", ".join(pdata.get("mlb_fallback") or []),
                        height=80,
                        key=f"ef_mlb_{pid}",
                        help=t("project_mlb_edit_hint", L),
                    )
                    col_sv, col_cn = st.columns(2)
                    with col_sv:
                        submitted_save = st.form_submit_button(t("btn_save_changes", L), type="primary")
                    with col_cn:
                        submitted_cancel = st.form_submit_button(t("btn_cancel", L))

                if submitted_save:
                    ss = st.session_state
                    smode = ss.get(f"ef_mode_{pid}", "profit_share")
                    if smode not in ("rental", "profit_share"):
                        smode = "profit_share"
                    fld = {
                        "type": ss.get(f"ef_type_{pid}", "ecom"),
                        "description": str(ss.get(f"ef_desc_{pid}", "")).strip(),
                        "status": ss.get(f"ef_stat_{pid}", "pending"),
                        "sku_prefixes": str(ss.get(f"ef_sku_{pid}", "")),
                        "compensation_mode": smode,
                    }
                    if ss.get(f"ef_no_rp_{pid}"):
                        fld["report_period"] = None
                    else:
                        r1 = ss.get(f"ef_rp_start_{pid}")
                        r2 = ss.get(f"ef_rp_end_{pid}")
                        if r1 and r2:
                            fld["report_period"] = (
                                f"{r1.isoformat()} / {r2.isoformat()}"
                                if r1 <= r2
                                else f"{r2.isoformat()} / {r1.isoformat()}"
                            )
                        elif r1 or r2:
                            x = r1 or r2
                            fld["report_period"] = f"{x.isoformat()} / {x.isoformat()}"
                        else:
                            fld["report_period"] = None
                    if ss.get(f"ef_no_lr_{pid}"):
                        fld["last_report"] = None
                    else:
                        lv = ss.get(f"ef_lr_{pid}")
                        fld["last_report"] = lv.isoformat() if lv else None
                    if ss.get(f"ef_no_nc_{pid}"):
                        fld["next_close"] = None
                    else:
                        nv = ss.get(f"ef_nc_{pid}")
                        fld["next_close"] = nv.isoformat() if nv else None
                    if ss.get(f"ef_no_launch_{pid}"):
                        fld["launch_date"] = None
                    else:
                        ldv = ss.get(f"ef_launch_{pid}")
                        fld["launch_date"] = ldv.isoformat() if ldv else None
                    if smode == "profit_share":
                        fld["profit_share_pct"] = float(ss.get(f"ef_pct_{pid}", pct0))
                    else:
                        fld["profit_share_pct"] = None
                    mlb_txt = str(ss.get(f"ef_mlb_{pid}", "")).strip()
                    if mlb_txt:
                        fld["mlb_fallback"] = mlb_txt
                    rpatch = None
                    if smode == "rental":
                        rpatch = {
                            "rate_usd": float(ss.get(f"ef_rr_{pid}", rate0)),
                            "period": ss.get(f"ef_rper_{pid}", per0 if per0 in ("month", "quarter") else "quarter"),
                            "note": str(ss.get(f"ef_rnote_{pid}", "")).strip() or None,
                        }
                        if f"ef_no_rentpay_{pid}" in ss:
                            if ss.get(f"ef_no_rentpay_{pid}"):
                                rpatch["next_payment_date"] = None
                            else:
                                rpd = ss.get(f"ef_rentpay_{pid}")
                                rpatch["next_payment_date"] = rpd.isoformat() if rpd else None
                    update_project(pid, fld, rpatch)
                    del st.session_state[edit_key]
                    st.success(t("project_saved", L))
                    st.rerun()
                if submitted_cancel:
                    del st.session_state[edit_key]
                    st.rerun()
            else:
                col_info, col_act = st.columns([4, 1])
                with col_info:
                    _card_html = _nx_proj_summary_html(pid, pdata, L)
                    _card_css = _nx_projects_page_css(
                        bg=_bg, bg2=_bg2, bg3=_bg3, border=_border,
                        text=_text, text2=_text2, text3=_text3,
                        yellow="#FFD500", green="#22d3a5", red="#ff5757",
                        blue="#38bdf8", purple="#a78bfa", amber="#f59e0b",
                        ydim="rgba(255,213,0,0.10)",
                    )
                    import streamlit.components.v1 as _comp
                    _comp.html(
                        f"<html><head>{_card_css}<style>body{{margin:0;padding:0;background:transparent;font-family:'Nunito Sans',sans-serif}}</style></head>"
                        f"<body>{_card_html}</body></html>",
                        height=380, scrolling=True,
                    )
                with col_act:
                    if st.button(t("btn_edit", L), key=f"ed_{pid}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if st.button(t("btn_delete", L), key=f"del_{pid}", type="secondary"):
                        st.session_state[f"confirm_delete_{pid}"] = True

            # Confirm delete
            if st.session_state.get(f"confirm_delete_{pid}"):
                st.warning(f"{t('confirm_delete', L)}: **{pid}**")
                st.caption(t("delete_warning", L))
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button(f"✅ {t('btn_delete', L)} {pid}", key=f"confirm_yes_{pid}", type="primary"):
                        delete_project(pid)
                        del st.session_state[f"confirm_delete_{pid}"]
                        st.success(f"{t('project_deleted', L)} **{pid}**")
                        st.rerun()
                with col_no:
                    if st.button("❌ Cancel", key=f"confirm_no_{pid}"):
                        del st.session_state[f"confirm_delete_{pid}"]
                        st.rerun()

    st.markdown(
        f'<div class="nx-proj-root"><div class="nx-proj-section">{html_escape.escape(t("add_project", L))}</div></div>',
        unsafe_allow_html=True,
    )

    add_comp_opts = ["profit_share", "rental"]
    with st.container(border=True):
        st.selectbox(
            t("compensation_mode_label", L),
            options=add_comp_opts,
            index=0,
            format_func=lambda k: t(f"compensation_mode_{k}", L),
            help=t("compensation_mode_help", L),
            key="add_project_comp_mode",
        )
        add_curr = st.session_state.get("add_project_comp_mode", "profit_share")
        if add_curr not in add_comp_opts:
            add_curr = "profit_share"

        with st.form("add_project_form"):
            new_name = st.text_input(t("project_name", L), placeholder="NOVO_PROJETO")
            new_type = st.selectbox(t("project_type_sel", L), ["ecom", "services", "hybrid"])
            new_desc = st.text_input(t("project_desc", L), placeholder="Descricao do projeto")
            new_skus = st.text_input(t("project_skus", L), placeholder="SKU1, SKU2, SKU3")
            st.date_input(
                t("project_launch_date_label", L),
                value=date.today(),
                format="DD/MM/YYYY",
                key="add_launch_date",
                help=t("project_launch_date_help", L),
            )
            add_no_rp = st.checkbox(
                t("project_report_period_none", L), value=True, key="add_no_rp",
            )
            if not add_no_rp:
                ac1, ac2 = st.columns(2)
                with ac1:
                    st.date_input(
                        t("project_report_period_from", L),
                        value=date.today(),
                        format="DD/MM/YYYY",
                        key="add_rp_start",
                    )
                with ac2:
                    st.date_input(
                        t("project_report_period_to", L),
                        value=date.today(),
                        format="DD/MM/YYYY",
                        key="add_rp_end",
                    )
            add_no_lr = st.checkbox(
                t("project_last_report_none", L), value=True, key="add_no_lr",
            )
            if not add_no_lr:
                st.date_input(
                    t("project_last_report_label", L),
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key="add_lr",
                )
            add_no_nc = st.checkbox(
                t("project_next_close_none", L), value=True, key="add_no_nc",
            )
            if not add_no_nc:
                st.date_input(
                    t("project_next_close_label", L),
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key="add_nc",
                )
            if add_curr == "profit_share":
                st.number_input(
                    t("profit_share_pct_label", L),
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=0.5,
                    help=t("profit_share_pct_help", L),
                    key="add_profit_pct",
                )
            elif add_curr == "rental":
                st.number_input(
                    t("rental_rate_label", L),
                    min_value=0.0,
                    value=0.0,
                    step=50.0,
                    key="add_rental_rate",
                )
                st.selectbox(
                    t("rental_period_label", L),
                    ["quarter", "month"],
                    index=0,
                    key="add_rental_period",
                )
                st.text_input(
                    t("rental_note_label", L),
                    value="",
                    key="add_rental_note",
                )
                add_no_rentpay = st.checkbox(
                    t("rental_next_payment_date_none", L),
                    value=True,
                    key="add_no_rentpay",
                )
                if not add_no_rentpay:
                    st.date_input(
                        t("rental_next_payment_date_label", L),
                        value=date.today(),
                        format="DD/MM/YYYY",
                        key="add_rentpay_date",
                        help=t("rental_next_payment_date_help", L),
                    )
                st.caption(t("rental_payments_json_hint", L))

            submitted = st.form_submit_button(t("btn_add", L))
            if submitted:
                comp_mode = st.session_state.get("add_project_comp_mode", "profit_share")
                if comp_mode not in add_comp_opts:
                    comp_mode = "profit_share"
                clean_name = new_name.strip().upper().replace(" ", "_")
                if not clean_name:
                    st.error("Nome vazio!")
                elif clean_name in projects_now:
                    st.error(f"Projeto **{clean_name}** ja existe!")
                else:
                    sku_list = [s.strip() for s in new_skus.split(",") if s.strip()] if new_skus else []
                    pct_arg = None
                    if comp_mode == "profit_share":
                        pct_arg = float(st.session_state.get("add_profit_pct", 0.0))
                    add_ld = st.session_state.get("add_launch_date")
                    add_project(
                        clean_name,
                        new_type,
                        new_desc,
                        sku_list,
                        compensation_mode=comp_mode,
                        profit_share_pct=pct_arg,
                        launch_date=add_ld,
                    )
                    extra_dates: dict = {}
                    if not st.session_state.get("add_no_rp", True):
                        ar1 = st.session_state.get("add_rp_start")
                        ar2 = st.session_state.get("add_rp_end")
                        if ar1 and ar2:
                            extra_dates["report_period"] = (
                                f"{ar1.isoformat()} / {ar2.isoformat()}"
                                if ar1 <= ar2
                                else f"{ar2.isoformat()} / {ar1.isoformat()}"
                            )
                        elif ar1 or ar2:
                            ax = ar1 or ar2
                            extra_dates["report_period"] = f"{ax.isoformat()} / {ax.isoformat()}"
                    if not st.session_state.get("add_no_lr", True):
                        alr = st.session_state.get("add_lr")
                        if alr:
                            extra_dates["last_report"] = alr.isoformat()
                    if not st.session_state.get("add_no_nc", True):
                        anc = st.session_state.get("add_nc")
                        if anc:
                            extra_dates["next_close"] = anc.isoformat()
                    if comp_mode == "rental":
                        rent_patch = {
                            "rate_usd": float(st.session_state.get("add_rental_rate", 0.0)),
                            "period": st.session_state.get("add_rental_period", "quarter"),
                            "note": str(st.session_state.get("add_rental_note", "")).strip() or None,
                        }
                        if not st.session_state.get("add_no_rentpay", True):
                            rdd = st.session_state.get("add_rentpay_date")
                            rent_patch["next_payment_date"] = rdd.isoformat() if rdd else None
                        update_project(clean_name, extra_dates, rent_patch)
                    elif extra_dates:
                        update_project(clean_name, extra_dates, None)
                    st.success(f"{t('project_added', L)} **{clean_name}**")
                    st.rerun()

