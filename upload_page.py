"""
Upload page — redesigned UI matching upload_clean_final.html mockup.
All backend logic preserved from original app.py inline implementation.
"""
import html
import hashlib
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    DATA_DIR, DATA_SOURCES, MONTHS, KNOWN_PASSWORDS,
    classify_transaction, load_projects, save_projects,
    get_project_by_sku,
)
from i18n import t
from unlocker import try_unlock

# ─────────────────────────────────────────────
# CSS — based on upload_clean_final.html mockup
# + Streamlit widget overrides
# ─────────────────────────────────────────────

UPLOAD_CSS = """
<style>
/* ── Scope: upload page container width ── */
.upload-root .block-container { max-width: 580px !important; margin: 0 auto !important; }

/* ── Header ── */
.up-hdr{display:flex;align-items:baseline;gap:10px;margin-bottom:22px}
.up-hdr-title{font-size:15px;font-weight:800;color:#f0f2ff;font-family:'Nunito Sans',sans-serif}
.up-hdr-sub{font-size:10px;color:#8892b0;font-weight:600;font-family:'Nunito Sans',sans-serif}

/* ── Field labels (месяц — как в макете, строчные) ── */
.up-field-label{font-size:9px;color:#8892b0;text-transform:none;letter-spacing:.2px;font-weight:600;margin-bottom:6px;font-family:'Nunito Sans',sans-serif}

/* ── Текст поверх дропзоны (рендерится после виджета, margin-top отрицательный) ── */
.up-drop-ghost-float{margin-top:-248px;margin-bottom:14px;height:178px;position:relative;z-index:5;pointer-events:none}
.up-drop-ghost-inner{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding-top:8px;gap:10px}
.up-drop-folder{font-size:36px;line-height:1;opacity:.92}
.up-drop-t1{font-size:15px;font-weight:700;color:#f0f2ff;font-family:'Nunito Sans',sans-serif;text-align:center;padding:0 24px;line-height:1.4;max-width:520px}
.up-drop-t2{font-size:11px;font-weight:600;color:#8892b0;font-family:'Nunito Sans',sans-serif}

/* ── Result row (ok / file info) ── */
.up-res-ok{display:flex;align-items:center;gap:8px;padding:10px 14px;background:rgba(34,211,165,0.07);border:1px solid rgba(34,211,165,0.2);border-radius:8px;margin-bottom:12px}
.up-res-ok.amber{background:rgba(245,158,11,0.05);border-color:rgba(245,158,11,0.25)}
.up-res-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.up-res-name{font-size:12px;font-weight:700;color:#f0f2ff;flex:1;font-family:'Nunito Sans',sans-serif}
.up-res-meta{font-size:10px;color:#8892b0;font-family:'DM Mono',monospace}

/* ── Warning block ── */
.up-warn-block{background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.18);border-radius:8px;overflow:hidden;margin-bottom:12px}
.up-warn-hdr{display:flex;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid rgba(245,158,11,0.12)}
.up-warn-lbl{font-size:10px;font-weight:800;color:#f59e0b;text-transform:uppercase;letter-spacing:.5px;flex:1;font-family:'Nunito Sans',sans-serif}

/* ── Classification table (HTML-rendered rows) ── */
.up-ct-hdr{display:flex;padding:7px 12px;border-bottom:1px solid rgba(245,158,11,0.1)}
.up-ct-hdr span{color:#3d4570;font-size:8px;text-transform:uppercase;letter-spacing:.8px;font-weight:700;font-family:'Nunito Sans',sans-serif}
.up-ct-row{display:flex;align-items:center;padding:5px 12px;border-bottom:1px solid rgba(31,37,64,0.5)}
.up-ct-row:hover{background:rgba(245,158,11,0.04)}
.up-ct-date{font-family:'DM Mono',monospace;font-size:10px;color:#8892b0}
.up-ct-desc{font-family:'Nunito Sans',sans-serif;font-size:10px;color:#f0f2ff}
.up-ct-val{font-family:'DM Mono',monospace;font-size:10px}
.up-ct-val.neg{color:#ff5757}
.up-ct-val.pos{color:#22d3a5}

/* ── Error block ── */
.up-err-block{background:rgba(255,87,87,0.06);border:1px solid rgba(255,87,87,0.18);border-radius:8px;padding:12px 14px;margin-bottom:12px}
.up-err-title{font-size:11px;font-weight:800;color:#ff5757;margin-bottom:4px;font-family:'Nunito Sans',sans-serif}
.up-err-sub{font-size:10px;color:#8892b0;margin-bottom:10px;font-family:'Nunito Sans',sans-serif}

/* ── Actions bar ── */
.up-actions{display:flex;align-items:center;gap:8px;justify-content:flex-end;margin-top:8px}
.up-act-status{flex:1;font-size:10px;color:#8892b0;font-family:'Nunito Sans',sans-serif}
.up-act-status.ok{color:#22d3a5;font-weight:700}

/* ── Success card (last upload) ── */
.up-saved-card{display:flex;align-items:center;gap:8px;padding:10px 14px;background:rgba(34,211,165,0.07);border:1px solid rgba(34,211,165,0.2);border-radius:8px;margin-bottom:8px}
.up-saved-dot{width:7px;height:7px;border-radius:50%;background:#22d3a5;flex-shrink:0}
.up-saved-name{font-size:12px;font-weight:700;color:#f0f2ff;flex:1;font-family:'Nunito Sans',sans-serif}
.up-saved-meta{font-size:10px;color:#8892b0;font-family:'DM Mono',monospace}

/* ── Type select row ── */
.up-type-row{padding:10px 12px;display:flex;align-items:center;gap:10px}
.up-type-lbl{font-size:10px;color:#8892b0;flex:1;font-family:'Nunito Sans',sans-serif}

/* ── Info badges ── */
.up-info-badge{display:inline-block;font-size:9px;padding:2px 8px;border-radius:4px;font-weight:700;font-family:'DM Mono',monospace}
.up-info-badge.green{background:rgba(34,211,165,0.1);color:#22d3a5;border:1px solid rgba(34,211,165,0.2)}
.up-info-badge.amber{background:rgba(245,158,11,0.1);color:#f59e0b;border:1px solid rgba(245,158,11,0.2)}
.up-info-badge.red{background:rgba(255,87,87,0.1);color:#ff5757;border:1px solid rgba(255,87,87,0.2)}
.up-info-badge.blue{background:rgba(56,189,248,0.1);color:#38bdf8;border:1px solid rgba(56,189,248,0.2)}

/* ── Streamlit widget overrides for upload page ── */

[data-testid="stFileUploader"] {
    margin-bottom: 18px;
    position: relative;
    z-index: 1;
    min-height: 220px !important;
}
/* Внутренний контейнер виджета иногда схлопывает высоту */
[data-testid="stFileUploader"] > div {
    min-height: 220px !important;
}

/* Дропзона: пунктир, тёмный фон, кнопка внизу — высокое окно */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploader"] section[role="presentation"][data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploader"] section[role="presentation"] {
    border: 1px dashed #6272a4 !important;
    border-radius: 12px !important;
    background: rgba(17, 21, 38, 0.55) !important;
    padding: 28px 24px 22px !important;
    min-height: 200px !important;
    box-sizing: border-box !important;
    transition: border-color .2s, background .2s, box-shadow .2s !important;
    box-shadow: inset 0 0 0 1px rgba(31, 37, 64, 0.4) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover,
[data-testid="stFileUploader"] section[role="presentation"]:hover {
    border-color: rgba(255, 213, 0, 0.55) !important;
    background: rgba(255, 213, 0, 0.06) !important;
}

/* Скрываем стандартный контент Streamlit (иконка, «200MB», типы) — подпись даёт .up-drop-ghost */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] > div > svg:first-of-type,
[data-testid="stFileUploader"] section[role="presentation"] > div > svg:first-of-type {
    display: none !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] > div > *:nth-child(2):not(button):not(:has(button)),
[data-testid="stFileUploader"] section[role="presentation"] > div > *:nth-child(2):not(button):not(:has(button)) {
    display: none !important;
}
/* Подпись Streamlit иногда в отдельных span — делаем невидимой, не трогая кнопку и input */
[data-testid="stFileUploader"] section[role="presentation"] small,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] small {
    visibility: hidden !important;
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
}

[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] > div,
[data-testid="stFileUploader"] section[role="presentation"] > div {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-end !important;
    gap: 14px !important;
    min-height: 148px !important;
    flex: 1 1 auto !important;
}

/* Browse — вторичная кнопка в стиле макета */
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
    background: rgba(24, 29, 48, 0.9) !important;
    border: 1px solid #3d4a6b !important;
    color: #cbd5e1 !important;
    border-radius: 8px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    font-family: 'Nunito Sans', sans-serif !important;
}
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:hover {
    border-color: #FFD500 !important;
    color: #FFD500 !important;
}

/* Строка загруженного файла (чип) */
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
    background: rgba(34, 211, 165, 0.12) !important;
    border: 1px solid rgba(34, 211, 165, 0.32) !important;
    border-radius: 8px !important;
    margin-top: 10px !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] [data-testid="stFileUploaderFileName"] {
    color: #f0f2ff !important;
    font-weight: 700 !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] [data-testid="stFileUploaderFileSize"] {
    color: #8892b0 !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDeleteBtn"] button {
    color: #8892b0 !important;
}

/* Только селект «месяц» (сразу над file_uploader): белое поле как в макете */
[data-testid="stVerticalBlock"] > div:has([data-testid="stSelectbox"]):has(+ div [data-testid="stFileUploader"]) [data-baseweb="select"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    min-height: 42px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
}
[data-testid="stVerticalBlock"] > div:has([data-testid="stSelectbox"]):has(+ div [data-testid="stFileUploader"]) [data-baseweb="select"] > div {
    color: #0b0e1a !important;
}
[data-testid="stVerticalBlock"] > div:has([data-testid="stSelectbox"]):has(+ div [data-testid="stFileUploader"]) [data-baseweb="select"] svg {
    fill: #0b0e1a !important;
}

/* Mini selects for classification rows */
.mini-classify-row [data-testid="stSelectbox"] [data-baseweb="select"] {
    min-height: 28px !important;
    font-size: 9px !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid #1f2540 !important;
    border-radius: 0 !important;
}
.mini-classify-row [data-testid="stSelectbox"] [data-baseweb="select"] span {
    color: #FFD500 !important;
    font-weight: 700 !important;
    font-size: 9px !important;
}

/* Save button — yellow */
.up-save-btn button {
    background: #FFD500 !important;
    border: 1px solid #FFD500 !important;
    border-radius: 7px !important;
    color: #0b0e1a !important;
    font-size: 12px !important;
    font-weight: 800 !important;
    padding: 9px 22px !important;
    font-family: 'Nunito Sans', sans-serif !important;
    transition: .2s !important;
}
.up-save-btn button:hover {
    background: #FFE94D !important;
}
.up-save-btn button:disabled {
    opacity: 1 !important;
    cursor: not-allowed !important;
    background: transparent !important;
    border: 1px solid #3d4a6b !important;
    color: #6b7280 !important;
}

/* Password input */
.up-pwd-input input {
    background: #181d30 !important;
    border: 1px solid #1f2540 !important;
    border-radius: 6px !important;
    color: #f0f2ff !important;
    font-size: 11px !important;
    padding: 7px 10px !important;
    font-family: 'DM Mono', monospace !important;
}
.up-pwd-input input:focus {
    border-color: #FFD500 !important;
}

/* Expander in upload context */
.up-expander [data-testid="stExpander"] {
    background: rgba(245,158,11,0.04) !important;
    border: 1px solid rgba(245,158,11,0.12) !important;
    border-radius: 8px !important;
}

/* DAS / NFS-e verification container */
.up-verify-container {
    background: rgba(245,158,11,0.04);
    border: 1px solid rgba(245,158,11,0.12);
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 12px;
}
</style>
"""


# ─────────────────────────────────────────────
# Helper functions (moved from app.py)
# ─────────────────────────────────────────────

def auto_detect_source(df: pd.DataFrame, filename: str):
    """Detect source type from DataFrame columns and/or filename."""
    cols = set(c.strip().lower() for c in df.columns) if len(df.columns) > 0 else set()
    fname = filename.lower()

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
    if "release_date" in cols or "transaction_net_amount" in cols or "partial_balance" in cols:
        return "extrato_mp"
    if "initial_balance" in cols and "final_balance" in cols:
        return "extrato_mp"
    if "data lançamento" in cols or "data lancamento" in cols:
        if any("r$" in c for c in cols):
            return "extrato_c6_brl"
        if any("us$" in c or "usd" in c for c in cols):
            return "extrato_c6_usd"
        return "extrato_c6_brl"

    # Filename-based detection
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
    if fname.startswith("01k") and (fname.endswith(".csv") or fname.endswith(".pdf")):
        return "extrato_c6_brl"
    if "trafficstars" in fname or "traffic" in fname:
        return "trafficstars"
    if "bybit" in fname:
        return "bybit_history"
    if "pgdasd" in fname or "das-" in fname or ("das" in fname and "simples" in fname):
        return "das_simples"
    if "nfs" in fname or "nfse" in fname or fname.startswith("nf "):
        return "nfse_shps"
    return None


def try_read_csv(file_bytes: bytes, nrows: int = 5):
    """Try to read CSV with different separators."""
    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, nrows=nrows, encoding="utf-8")
            if len(df.columns) > 2:
                return df
        except Exception:
            continue
    return None


def _parse_val(v):
    """Parse number — supports BRL format (1.234,56) and standard."""
    if pd.isna(v):
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _fmt_brl(v):
    """Format value as BRL-style string."""
    if v < 0:
        return f"−{abs(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"+{v:,.2f}".replace(",", " ").replace(".", ",")


# ─────────────────────────────────────────────
# HTML rendering helpers
# ─────────────────────────────────────────────

def _render_header(L):
    st.markdown(f'''
    <div class="up-hdr">
        <div class="up-hdr-title">{t("upload_screen_title", L)}</div>
        <div class="up-hdr-sub">LATAMSELLERS</div>
    </div>
    ''', unsafe_allow_html=True)


def _render_dropzone_caption(L):
    """Подпись внутри дропзоны (поверх виджета, без перехвата кликов)."""
    t1 = html.escape(t("upload_drop_primary", L))
    t2 = html.escape(t("upload_formats_line", L))
    st.markdown(f'''
    <div class="up-drop-ghost-float" aria-hidden="true">
        <div class="up-drop-ghost-inner">
            <span class="up-drop-folder">📁</span>
            <span class="up-drop-t1">{t1}</span>
            <span class="up-drop-t2">{t2}</span>
        </div>
    </div>
    ''', unsafe_allow_html=True)


def _render_file_status_row(filename, meta_text, color="green"):
    """Render the file info row with colored dot."""
    dot_color = {"green": "#22d3a5", "amber": "#f59e0b", "red": "#ff5757"}.get(color, "#22d3a5")
    extra_class = " amber" if color == "amber" else ""
    st.markdown(f'''
    <div class="up-res-ok{extra_class}">
        <div class="up-res-dot" style="background:{dot_color}"></div>
        <div class="up-res-name">{filename}</div>
        <div class="up-res-meta">{meta_text}</div>
    </div>
    ''', unsafe_allow_html=True)


def _render_warn_header(label_text):
    st.markdown(f'''
    <div class="up-warn-block">
        <div class="up-warn-hdr">
            <span style="font-size:12px">⚠</span>
            <span class="up-warn-lbl">{label_text}</span>
        </div>
    </div>
    ''', unsafe_allow_html=True)


def _render_error_block(title, subtitle):
    st.markdown(f'''
    <div class="up-err-block">
        <div class="up-err-title">{title}</div>
        <div class="up-err-sub">{subtitle}</div>
    </div>
    ''', unsafe_allow_html=True)


def _render_info_badge(text, color="green"):
    st.markdown(f'<span class="up-info-badge {color}">{text}</span>', unsafe_allow_html=True)


def _render_saved_card(name, meta):
    st.markdown(f'''
    <div class="up-saved-card">
        <div class="up-saved-dot"></div>
        <div class="up-saved-name">{name}</div>
        <div class="up-saved-meta">{meta}</div>
    </div>
    ''', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# State: ENCRYPTED (password required)
# ─────────────────────────────────────────────

def _handle_encrypted_state(L, ufile, file_bytes, ext):
    """Render encrypted file state — password input + retry."""
    _render_error_block(
        t("file_encrypted", L),
        f"{ufile.name} · {t('pwd_not_found', L)}"
    )
    col_pwd, col_btn = st.columns([3, 1])
    with col_pwd:
        st.markdown('<div class="up-pwd-input">', unsafe_allow_html=True)
        pwd_input = st.text_input(
            "pwd", placeholder=t("enter_password", L),
            type="password", key=f"pwd_{ufile.name}",
            label_visibility="collapsed",
        )
        st.markdown('</div>', unsafe_allow_html=True)
    with col_btn:
        retry = st.button(t("try_btn", L), key=f"retry_{ufile.name}")

    if retry and pwd_input:
        unlocked_data, pwd, status = try_unlock(file_bytes, ufile.name, [pwd_input])
        if status == "unlocked":
            st.session_state[f"unlocked_{ufile.name}"] = unlocked_data
            st.session_state[f"unlocked_pwd_{ufile.name}"] = pwd_input
            st.rerun()
        else:
            _render_info_badge(f"✕ {t('unlock_fail', L)}", "red")

    # Cancel
    st.markdown(f'''
    <div class="up-actions">
        <div class="up-act-status"></div>
    </div>
    ''', unsafe_allow_html=True)

    return None, None  # file_bytes not unlocked


# ─────────────────────────────────────────────
# State: UNKNOWN TYPE
# ─────────────────────────────────────────────

def _handle_unknown_state(L, ufile, row_count):
    """Render unknown type state — manual source selector."""
    meta = f"{row_count} {t('rows_suffix', L)}" if row_count else ""
    _render_file_status_row(ufile.name, meta, color="amber")

    _render_warn_header(t("type_unknown", L))

    # Source selector with group prefixes
    all_sources = {k: v["name"] for k, v in DATA_SOURCES.items()}
    source_groups = {
        "ECOM": ["vendas_ml", "collection_mp", "extrato_mp", "fatura_ml", "ads_publicidade",
                  "armazenagem_full", "stock_full", "full_express", "after_collection"],
        "Banco": ["extrato_nubank", "fatura_nubank"],
        "Serviços": ["extrato_c6_brl", "extrato_c6_usd", "trafficstars", "invoices_estonia",
                      "das_simples", "nfse_shps", "bybit_history"],
    }

    options = ["—"]
    format_map = {"—": f"— {t('select_doc_type_short', L)} —"}
    for group, ids in source_groups.items():
        for sid in ids:
            if sid in all_sources:
                options.append(sid)
                format_map[sid] = f"[{group}] {all_sources[sid]}"

    chosen = st.selectbox(
        t("select_doc_type_short", L),
        options,
        format_func=lambda x: format_map.get(x, x),
        key=f"manual_type_{ufile.name}",
        label_visibility="collapsed",
    )

    if chosen == "—":
        st.markdown(f'''
        <div class="up-actions">
            <div class="up-act-status">{t("indicate_type", L)}</div>
        </div>
        ''', unsafe_allow_html=True)
        return None

    return chosen


# ─────────────────────────────────────────────
# Transaction classification for bank statements
# ─────────────────────────────────────────────

def _classify_bank_transactions(L, ufile, file_bytes, ext, detected_source, upload_month):
    """
    Parse and classify bank statement transactions.
    Returns (tx_classifications list, tx_splits dict) or (None, {}).
    """
    PROJECTS = load_projects()
    project_options = list(PROJECTS.keys()) + ["—"]
    category_options = [
        "internal_transfer", "income", "expense", "supplier", "fulfillment",
        "shipping", "ads", "tax", "accounting", "salary", "freelancer",
        "rent", "utilities", "software", "bank_fee", "fx", "loan",
        "investment", "refund", "dividends", "personal", "uncategorized",
    ]

    # MP extrato — show summary balances from header
    if detected_source == "extrato_mp":
        try:
            df_summary = pd.read_csv(io.BytesIO(file_bytes), sep=";", nrows=1, encoding="utf-8")
            if "INITIAL_BALANCE" in df_summary.columns:
                row0 = df_summary.iloc[0]
                def parse_brl_n(v):
                    try:
                        return float(str(v).replace(".", "").replace(",", "."))
                    except (ValueError, TypeError):
                        return 0
                init_b = parse_brl_n(row0.get("INITIAL_BALANCE", 0))
                creds = parse_brl_n(row0.get("CREDITS", 0))
                debs = parse_brl_n(row0.get("DEBITS", 0))
                final_b = parse_brl_n(row0.get("FINAL_BALANCE", 0))
                def fmt_brl(v):
                    return f"R$ {v:,.0f}".replace(",", ".")
                st.markdown(f"""
| Saldo inicial | Créditos | Débitos | Saldo final |
|---|---|---|---|
| **{fmt_brl(init_b)}** | **{fmt_brl(creds)}** | **{fmt_brl(debs)}** | **{fmt_brl(final_b)}** |
                """)
        except Exception:
            pass

    try:
        # Read full file
        df_tx = None
        if detected_source == "extrato_mp":
            for skip in [3, 2, 4]:
                try:
                    df_tx = pd.read_csv(io.BytesIO(file_bytes), sep=";", skiprows=skip, encoding="utf-8")
                    if "RELEASE_DATE" in df_tx.columns or "TRANSACTION_TYPE" in df_tx.columns:
                        break
                except Exception:
                    continue
        else:
            for sep_try in [",", ";"]:
                try:
                    df_tx = pd.read_csv(io.BytesIO(file_bytes), sep=sep_try, encoding="utf-8")
                    if len(df_tx.columns) > 2:
                        break
                except Exception:
                    continue
            if df_tx is None or len(df_tx.columns) <= 2:
                for skip in [5, 8, 10]:
                    try:
                        df_tx = pd.read_csv(io.BytesIO(file_bytes), sep=",", skiprows=skip, encoding="utf-8")
                        if len(df_tx.columns) > 2:
                            break
                    except Exception:
                        continue

        if df_tx is None or len(df_tx) == 0:
            return None, {}

        # Identify columns
        desc_col = value_col = entrada_col = saida_col = date_col = None
        for c in df_tx.columns:
            cl = str(c).lower()
            if "descri" in cl or "título" in cl or "titulo" in cl or "transaction_type" in cl:
                desc_col = c
            if "entrada" in cl:
                entrada_col = c
            if "saída" in cl or "saida" in cl:
                saida_col = c
            if (("valor" in cl and "valor do dia" not in cl) or "transaction_net_amount" in cl) and value_col is None:
                value_col = c
            if ("data" in cl or "release_date" in cl) and date_col is None:
                date_col = c

        # Build classification table
        mp_income_skipped = 0
        mp_total_income = 0
        class_rows = []

        for idx, row in df_tx.iterrows():
            desc = str(row.get(desc_col, "")) if desc_col else ""
            if entrada_col and saida_col:
                entrada = _parse_val(row.get(entrada_col, 0))
                saida = _parse_val(row.get(saida_col, 0))
                val = entrada - saida
            else:
                val_raw = row.get(value_col, 0) if value_col else 0
                val = _parse_val(val_raw)

            if detected_source == "extrato_mp":
                is_liberacao = "liberação" in desc.lower() or "liberacao" in desc.lower()
                if val > 0 or is_liberacao:
                    mp_income_skipped += 1
                    mp_total_income += abs(val)
                    continue

            date_val = str(row.get(date_col, "")) if date_col else ""
            cls = classify_transaction(desc, val)
            class_rows.append({
                "Data": date_val,
                "Valor": val,
                "Descrição": desc[:80],
                "Категория": cls["category"],
                "Проект": cls["project"] or "❓",
                "Класс.": cls["label"],
            })

        if detected_source == "extrato_mp" and mp_income_skipped > 0:
            _render_info_badge(
                f"MP: {mp_income_skipped} поступлений (R$ {mp_total_income:,.2f}) → отчёт продаж",
                "blue"
            )

        df_class = pd.DataFrame(class_rows)

        # Split group detection
        def is_split_group(row):
            cat = row.get("Категория", "")
            label_lo = str(row.get("Класс.", "")).lower()
            return (cat == "fulfillment" or "fatura ml" in label_lo
                    or "retido" in label_lo or "devolu" in label_lo or "reclamaç" in label_lo)

        def needs_attention(row):
            if is_split_group(row):
                return False
            cat = row.get("Категория", "")
            proj = row.get("Проект", "")
            return cat == "uncategorized" or not proj or proj == "❓"

        df_uncl = df_class[df_class.apply(needs_attention, axis=1)].copy()

        # ── stateWarn: show unclassified transactions ──
        if len(df_uncl) > 0:
            _render_warn_header(f"{len(df_uncl)} {t('uncategorized_n_tx', L)}")

            # Classification mini-table using st.columns per row
            for idx in df_uncl.index:
                row = df_uncl.loc[idx]
                date_short = str(row["Data"])[:5] if row["Data"] else ""
                val = row["Valor"]
                val_class = "neg" if val < 0 else "pos"
                val_str = _fmt_brl(val)

                c1, c2, c3, c4, c5 = st.columns([1, 3, 1.2, 2, 2])
                with c1:
                    st.markdown(f'<div class="up-ct-date">{date_short}</div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="up-ct-desc">{row["Descrição"]}</div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="up-ct-val {val_class}">{val_str}</div>', unsafe_allow_html=True)
                with c4:
                    cat = st.selectbox(
                        "cat", ["—"] + category_options,
                        index=(category_options.index(row["Категория"]) + 1) if row["Категория"] in category_options else 0,
                        key=f"cat_{idx}_{ufile.name}",
                        label_visibility="collapsed",
                    )
                    if cat != "—":
                        df_class.at[idx, "Категория"] = cat
                with c5:
                    proj = st.selectbox(
                        "proj", ["—"] + project_options,
                        index=(project_options.index(row["Проект"]) + 1) if row["Проект"] in project_options and row["Проект"] != "❓" else 0,
                        key=f"proj_{idx}_{ufile.name}",
                        label_visibility="collapsed",
                    )
                    if proj != "—":
                        df_class.at[idx, "Проект"] = proj

            # Check if all classified now
            still_uncl = df_class[df_class.apply(needs_attention, axis=1)]
            all_classified = len(still_uncl) == 0
        else:
            all_classified = True
            _render_info_badge("✅ Все транзакции классифицированы", "green")

        # All transactions in expander
        with st.expander(f"📋 Все транзакции ({len(df_class)})", expanded=False):
            st.dataframe(df_class, use_container_width=True, hide_index=True)

        # Metrics
        categorized_count = len(df_class[(df_class["Категория"] != "uncategorized") & (df_class["Проект"] != "❓") & (df_class["Проект"] != "")])
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Всего", len(df_class))
        col_s2.metric("✅ Класс.", categorized_count)
        col_s3.metric("❓ Некласс.", len(df_class) - categorized_count)

        # ── Splittable transactions: GROUP by category ──
        ecom_projects = [pid for pid, p in load_projects().items() if p.get("type") in ("ecom", "hybrid")]

        def split_group(row):
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

        edited_grp = df_class.copy()
        edited_grp["__group"] = edited_grp.apply(split_group, axis=1)
        groups_df = edited_grp[edited_grp["__group"].notna()]

        tx_splits = {}
        if len(groups_df) > 0:
            st.markdown("#### 🔀 Разделение между проектами (по группам)")

            group_labels = {
                "fulfillment": "📦 Full Express / Fulfillment",
                "fatura_ml": "📋 Fatura ML",
                "retido": "🔒 Dinheiro retido ML",
                "devolucoes": "↩️ Devoluções e Reclamações ML",
            }

            for group_key in ["fulfillment", "fatura_ml", "retido", "devolucoes"]:
                grp = groups_df[groups_df["__group"] == group_key]
                if len(grp) == 0:
                    continue
                title = group_labels[group_key]
                total_abs = float(grp["Valor"].abs().sum())

                with st.expander(f"{title} — **R$ {total_abs:,.2f}** ({len(grp)} оп.)", expanded=True):
                    cols = st.columns(len(ecom_projects))
                    split_values = {}
                    for i, proj in enumerate(ecom_projects):
                        with cols[i]:
                            v = st.number_input(
                                proj, min_value=0.0, value=0.0, step=0.01,
                                format="%.2f", key=f"grp_split_{ufile.name}_{group_key}_{proj}",
                            )
                            split_values[proj] = v

                    total_split = sum(split_values.values())
                    if abs(total_split - total_abs) < 0.01:
                        _render_info_badge(f"✅ R$ {total_split:,.2f}", "green")
                    elif total_split == 0:
                        _render_info_badge(f"⏳ R$ {total_abs:,.2f}", "amber")
                    else:
                        _render_info_badge(f"⚠️ {total_split:,.2f} / {total_abs:,.2f}", "red")

                    with st.expander(f"Показать {len(grp)} операций"):
                        st.dataframe(
                            grp[["Data", "Valor", "Descrição"]], use_container_width=True,
                            hide_index=True,
                            column_config={"Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")},
                        )

                    tx_splits[group_key] = {
                        "total": total_abs, "split": split_values, "qtd": len(grp),
                    }

        # Project summary
        with st.expander("📊 Сводка по проектам"):
            proj_summary = df_class.groupby("Проект").agg(
                qtd=("Valor", "count"), total=("Valor", "sum"),
            ).reset_index()
            if tx_splits:
                split_totals = {}
                for group_data in tx_splits.values():
                    for proj, amt in group_data.get("split", {}).items():
                        if amt > 0:
                            split_totals[proj] = split_totals.get(proj, 0) - amt
                if split_totals:
                    st.markdown("**Из splits (Full Express + Fatura ML + Devoluções):**")
                    st.dataframe(
                        pd.DataFrame([{"Проект": p, "Total": v} for p, v in split_totals.items()]),
                        use_container_width=True, hide_index=True,
                        column_config={"Total": st.column_config.NumberColumn("Total", format="R$ %.2f")},
                    )
            st.dataframe(
                proj_summary, use_container_width=True, hide_index=True,
                column_config={"total": st.column_config.NumberColumn("Total", format="R$ %.2f")},
            )

        tx_classifications = df_class.to_dict("records")
        tx_splits_serializable = {str(k): v for k, v in tx_splits.items()}
        return tx_classifications, tx_splits_serializable

    except Exception as e:
        st.warning(f"⚠️ Erro ao classificar: {e}")
        return None, {}


# ─────────────────────────────────────────────
# SKU classification for vendas_ml
# ─────────────────────────────────────────────

def _handle_sku_classification(L, ufile, file_bytes, ext):
    """Check and handle unclassified SKUs for vendas_ml."""
    PROJECTS = load_projects()
    try:
        if ext == ".csv":
            df_sku_check = pd.read_csv(io.BytesIO(file_bytes), sep=";", skiprows=5, encoding="utf-8")
        else:
            df_sku_check = pd.read_excel(io.BytesIO(file_bytes))

        unclassified_skus = []
        for _, row in df_sku_check.iterrows():
            sku = str(row.get("SKU", "")).strip()
            mlb = str(row.get("# de anúncio", row.get("# de anuncio", ""))).strip()
            proj = get_project_by_sku(sku, mlb)
            if proj == "NAO_CLASSIFICADO" and (sku or mlb):
                titulo = str(row.get("Título do anúncio", row.get("Titulo do anuncio", "")))[:60]
                unclassified_skus.append({"SKU": sku, "MLB": mlb, "Titulo": titulo})

        if unclassified_skus:
            df_unc = pd.DataFrame(unclassified_skus).drop_duplicates(subset=["SKU", "MLB"])
            _render_warn_header(f"⚠️ {len(df_unc)} SKU без проекта")

            ecom_proj_list = ["—"] + [pid for pid, p in PROJECTS.items() if p.get("type") == "ecom"]
            assignments_made = []
            for idx, urow in df_unc.iterrows():
                c1, c2, c3 = st.columns([2, 3, 2])
                c1.code(f"{urow['SKU']}  {urow['MLB']}")
                c2.caption(urow["Titulo"])
                chosen = c3.selectbox(
                    "Проект", ecom_proj_list,
                    key=f"assign_{urow['SKU']}_{urow['MLB']}_{ufile.name}",
                    label_visibility="collapsed",
                )
                if chosen != "—":
                    assignments_made.append({"sku": urow["SKU"], "mlb": urow["MLB"], "project": chosen})

            if assignments_made:
                st.markdown('<div class="up-save-btn">', unsafe_allow_html=True)
                if st.button(f"💾 Сохранить {len(assignments_made)} назначений", key=f"save_assign_{ufile.name}"):
                    updated_projects = load_projects()
                    for a in assignments_made:
                        pid = a["project"]
                        if pid not in updated_projects:
                            continue
                        p = updated_projects[pid]
                        if a["mlb"] and a["mlb"] not in p.get("mlb_fallback", []):
                            p.setdefault("mlb_fallback", []).append(a["mlb"])
                        if a["sku"]:
                            already_covered = any(a["sku"].startswith(pfx) for pfx in p.get("sku_prefixes", []) if pfx)
                            if not already_covered:
                                p.setdefault("sku_prefixes", []).append(a["sku"])
                    save_projects(updated_projects)
                    _render_info_badge(f"✅ Сохранено {len(assignments_made)} назначений!", "green")
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            _render_info_badge("✅ Все SKU классифицированы", "green")
    except Exception as e:
        st.warning(f"⚠️ Не удалось проверить SKU: {e}")


# ─────────────────────────────────────────────
# PDF handling (DAS, NFS-e)
# ─────────────────────────────────────────────

def _detect_pdf_content(file_bytes, ufile_name, manual_source):
    """Detect DAS or NFS-e from PDF content. Returns (das_parsed, nfse_parsed, updated_manual_source)."""
    das_parsed = None
    nfse_parsed = None

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""

        is_das_by_content = ("Simples Nacional" in first_page_text and "Documento de Arrecadação" in first_page_text) \
                            or "PGDASD" in first_page_text
        is_das_by_filename = "pgdasd" in ufile_name.lower() or "das-" in ufile_name.lower()

        is_nfse_by_content = "NFS-e" in first_page_text or "Nota Fiscal de Serviço" in first_page_text or "DANFSe" in first_page_text
        is_nfse_by_filename = "nfs" in ufile_name.lower() or ufile_name.lower().startswith("nf ")

        if is_das_by_content or is_das_by_filename:
            if manual_source == "auto":
                manual_source = "das_simples"
            from reports import parse_das_pdf
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)
            das_parsed = parse_das_pdf(tmp_path, original_filename=ufile_name)
            tmp_path.unlink(missing_ok=True)
            if das_parsed is None:
                st.warning("⚠️ DAS detectado mas parser falhou — verifique manualmente")

        elif is_nfse_by_content or is_nfse_by_filename:
            if manual_source == "auto":
                manual_source = "nfse_shps"
            from reports import parse_nfse_pdf
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)
            nfse_parsed = parse_nfse_pdf(tmp_path, original_filename=ufile_name)
            tmp_path.unlink(missing_ok=True)
    except Exception as e:
        st.warning(f"⚠️ Erro ao analisar PDF: {e}")

    return das_parsed, nfse_parsed, manual_source


def _render_nfse_verification(L, nfse_parsed, ufile, upload_month):
    """Render NFS-e verification card. Returns confirmed month."""
    st.markdown('<div class="up-verify-container">', unsafe_allow_html=True)
    st.markdown("### 📄 Verificação da NFS-e detectada")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Número:** {nfse_parsed.get('numero', '?')}")
        st.markdown(f"**Competência:** {nfse_parsed.get('competencia_raw', '?')}")
        st.markdown(f"**Data emissão:** {nfse_parsed.get('data_emissao', '?')}")
        st.markdown(f"**Tomador:** {nfse_parsed.get('tomador', '?')}")
    with col_b:
        st.markdown(f"**Valor:** R$ {nfse_parsed.get('valor', 0):,.2f}")
        st.markdown(f"**Mês de referência:** {nfse_parsed.get('ref_month', '?')}")
        st.markdown(f"**Descrição:** {nfse_parsed.get('descricao', '?')}")

    detected_month = nfse_parsed.get("competencia")
    default_idx = MONTHS.index(detected_month) if detected_month in MONTHS else len(MONTHS) - 1
    confirmed_month = st.selectbox(
        "✏️ Mês de destino (competência da NFS-e):",
        MONTHS, index=default_idx, key=f"nfse_month_{ufile.name}",
    )

    if detected_month and confirmed_month != detected_month:
        _render_info_badge(f"⚠️ {detected_month} → {confirmed_month}", "amber")
    elif detected_month:
        _render_info_badge(f"✅ {confirmed_month}", "green")

    st.markdown('</div>', unsafe_allow_html=True)
    return confirmed_month


def _render_das_verification(L, das_parsed, ufile, upload_month):
    """Render DAS verification card. Returns (confirmed_month, updated das_parsed)."""
    st.markdown('<div class="up-verify-container">', unsafe_allow_html=True)
    st.markdown("### 📄 Verificação do DAS detectado")

    if das_parsed.get("no_text_layer"):
        _render_info_badge("⚠️ PDF sem texto — valores manuais", "amber")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Período:** {das_parsed.get('month', '?')}")
        st.markdown(f"**Vencimento:** {das_parsed.get('vencimento', '?') or '—'}")
        if not das_parsed.get("no_text_layer"):
            st.markdown(f"**Valor Total:** R$ {das_parsed.get('total', 0):,.2f}")

    with col_b:
        if das_parsed.get("no_text_layer"):
            st.markdown("**Composição (digite manualmente):**")
            irpj = st.number_input("IRPJ (1001)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"irpj_{ufile.name}")
            csll = st.number_input("CSLL (1002)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"csll_{ufile.name}")
            cofins = st.number_input("COFINS (1004)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"cofins_{ufile.name}")
            pis = st.number_input("PIS (1005)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"pis_{ufile.name}")
            inss = st.number_input("INSS (1006)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"inss_{ufile.name}")
            iss = st.number_input("ISS (1010)", min_value=0.0, value=0.0, step=0.01, format="%.2f", key=f"iss_{ufile.name}")
            das_parsed["irpj"] = irpj
            das_parsed["csll"] = csll
            das_parsed["cofins"] = cofins
            das_parsed["pis"] = pis
            das_parsed["inss"] = inss
            das_parsed["iss"] = iss
            das_parsed["total"] = irpj + csll + cofins + pis + inss + iss
            st.markdown(f"### **TOTAL: R$ {das_parsed['total']:,.2f}**")
        else:
            st.markdown(f"**IRPJ (1001):** R$ {das_parsed.get('irpj', 0):,.2f}")
            st.markdown(f"**CSLL (1002):** R$ {das_parsed.get('csll', 0):,.2f}")
            st.markdown(f"**COFINS (1004):** R$ {das_parsed.get('cofins', 0):,.2f}")
            st.markdown(f"**PIS (1005):** R$ {das_parsed.get('pis', 0):,.2f}")
            st.markdown(f"**INSS (1006):** R$ {das_parsed.get('inss', 0):,.2f}")
            st.markdown(f"**ISS (1010):** R$ {das_parsed.get('iss', 0):,.2f}")

    detected_month = das_parsed.get("month_iso")
    default_idx = MONTHS.index(detected_month) if detected_month in MONTHS else len(MONTHS) - 1
    confirmed_month = st.selectbox(
        "✏️ Confirme/altere o mês de destino:",
        MONTHS, index=default_idx, key=f"confirm_month_{ufile.name}",
    )

    if detected_month and confirmed_month != detected_month:
        _render_info_badge(f"⚠️ {detected_month} → {confirmed_month}", "amber")
    elif detected_month:
        _render_info_badge(f"✅ {confirmed_month}", "green")

    st.markdown('</div>', unsafe_allow_html=True)
    return confirmed_month, das_parsed


# ─────────────────────────────────────────────
# Date coverage detection
# ─────────────────────────────────────────────

def _detect_date_coverage(file_bytes, ext, detected_source):
    """Detect date range and row count. Returns (d_min, d_max, row_count) or None."""
    if ext not in (".csv", ".xlsx", ".xls"):
        return None

    try:
        df_dates = None
        if ext == ".csv":
            if detected_source == "extrato_mp":
                for skip in [3, 2, 4]:
                    try:
                        df_try = pd.read_csv(io.BytesIO(file_bytes), sep=";", skiprows=skip, encoding="utf-8")
                        if "RELEASE_DATE" in df_try.columns or len(df_try.columns) >= 4:
                            df_dates = df_try
                            break
                    except Exception:
                        continue
            else:
                for sep in [",", ";", "\t"]:
                    try:
                        df_try = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding="utf-8")
                        if len(df_try.columns) > 2:
                            df_dates = df_try
                            break
                    except Exception:
                        continue
                if df_dates is None or len(df_dates.columns) <= 2:
                    for skip in [5, 8, 10]:
                        try:
                            df_dates = pd.read_csv(io.BytesIO(file_bytes), skiprows=skip, encoding="utf-8")
                            if len(df_dates.columns) > 2:
                                break
                        except Exception:
                            continue
        else:
            df_dates = pd.read_excel(io.BytesIO(file_bytes))

        if df_dates is None or len(df_dates) == 0:
            return None

        date_cols = [c for c in df_dates.columns if any(k in str(c).lower() for k in
                     ["date", "data", "fecha", "desde", "até", "created", "approved", "release"])]
        if not date_cols:
            for c in df_dates.columns:
                try:
                    pd.to_datetime(df_dates[c].dropna().head(), dayfirst=True)
                    date_cols.append(c)
                    break
                except Exception:
                    continue

        if date_cols:
            col_name = date_cols[0]
            dates = pd.to_datetime(df_dates[col_name], dayfirst=True, errors="coerce").dropna()
            if len(dates) > 0:
                return (
                    dates.min().strftime("%d/%m/%Y"),
                    dates.max().strftime("%d/%m/%Y"),
                    len(df_dates),
                )
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# Duplicate check
# ─────────────────────────────────────────────

def _check_duplicates(file_bytes, upload_month, detected_source, ext):
    """Check for duplicates. Returns list of info/warning messages."""
    messages = []
    new_hash = hashlib.md5(file_bytes).hexdigest()
    month_dir = DATA_DIR / upload_month
    saved_name = f"{detected_source}{ext}"
    target = month_dir / saved_name

    if target.exists():
        existing_hash = hashlib.md5(target.read_bytes()).hexdigest()
        existing_size = target.stat().st_size
        existing_date = datetime.fromtimestamp(target.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        if existing_hash == new_hash:
            messages.append(("warn", f"Arquivo IDÊNTICO: _data/{upload_month}/{saved_name} ({existing_size:,} bytes, {existing_date})"))
        else:
            messages.append(("info", f"Substituirá: _data/{upload_month}/{saved_name} ({existing_size:,} → {len(file_bytes):,} bytes)"))

    # Cross-month check
    duplicate_locations = []
    for m in MONTHS:
        if m == upload_month:
            continue
        other_path = DATA_DIR / m / saved_name
        if other_path.exists():
            try:
                if hashlib.md5(other_path.read_bytes()).hexdigest() == new_hash:
                    duplicate_locations.append(f"_data/{m}/{saved_name}")
            except Exception:
                pass
    if duplicate_locations:
        messages.append(("warn", "Idêntico em: " + " · ".join(duplicate_locations)))

    return messages


# ─────────────────────────────────────────────
# Save logic
# ─────────────────────────────────────────────

def _save_file(ufile, file_bytes, ext, detected_source, upload_month,
               das_parsed, nfse_parsed, tx_classifications, tx_splits_serializable,
               was_unlocked, found_pwd):
    """Save file + sidecars. Returns True on success."""
    import json as json_mod

    month_dir = DATA_DIR / upload_month
    saved_name = f"{detected_source}{ext}"
    target = month_dir / saved_name

    month_dir.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f_out:
        f_out.write(file_bytes)

    # DAS sidecar
    if detected_source == "das_simples" and das_parsed:
        sidecar_path = month_dir / f"{detected_source}.json"
        sidecar_data = {
            "month": das_parsed.get("month"),
            "month_iso": das_parsed.get("month_iso"),
            "vencimento": das_parsed.get("vencimento"),
            "total": das_parsed.get("total", 0),
            "irpj": das_parsed.get("irpj", 0),
            "csll": das_parsed.get("csll", 0),
            "cofins": das_parsed.get("cofins", 0),
            "pis": das_parsed.get("pis", 0),
            "inss": das_parsed.get("inss", 0),
            "iss": das_parsed.get("iss", 0),
            "manual_input": das_parsed.get("no_text_layer", False),
            "original_filename": ufile.name,
        }
        with open(sidecar_path, "w", encoding="utf-8") as jf:
            json_mod.dump(sidecar_data, jf, indent=2, ensure_ascii=False)

    # NFS-e sidecar
    if detected_source == "nfse_shps" and nfse_parsed:
        numero = nfse_parsed.get("numero") or "unknown"
        sidecar_path = month_dir / f"{detected_source}_{numero}.json"
        with open(sidecar_path, "w", encoding="utf-8") as jf:
            json_mod.dump({**nfse_parsed, "original_filename": ufile.name}, jf, indent=2, ensure_ascii=False)

    # Transaction classifications sidecar
    if tx_classifications:
        sidecar_path = month_dir / f"{detected_source}_classifications.json"
        with open(sidecar_path, "w", encoding="utf-8") as jf:
            json_mod.dump({
                "original_filename": ufile.name,
                "month": upload_month,
                "source": detected_source,
                "transactions": tx_classifications,
                "full_express_splits": tx_splits_serializable or {},
            }, jf, indent=2, ensure_ascii=False, default=str)

    # Update session state
    if "last_upload" not in st.session_state:
        st.session_state.last_upload = []
    st.session_state.last_upload.append({
        "original_name": ufile.name,
        "saved_as": saved_name,
        "month": upload_month,
        "size": len(file_bytes),
        "source": detected_source,
        "unlocked": was_unlocked,
        "password": found_pwd,
    })
    return True


# ═══════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════

def render_upload_page(L):
    """Render the redesigned upload page."""

    # Inject CSS
    st.markdown(UPLOAD_CSS, unsafe_allow_html=True)

    # Header
    _render_header(L)

    # ── Last upload results ──
    if "last_upload" in st.session_state and st.session_state.last_upload:
        for item in st.session_state.last_upload:
            src_name = DATA_SOURCES.get(item["source"], {}).get("name", item["source"])
            meta = f"{src_name} · {item['month']} · {item['size']:,} bytes"
            if item.get("unlocked"):
                meta = f"🔓 {meta}"
            _render_saved_card(item["original_name"], meta)

        if st.button(t("clear_result", L), key="clear_upload_result"):
            st.session_state.last_upload = []
            st.rerun()

        st.markdown("---")

    # ── Upload form ──
    st.markdown(f'<div class="up-field-label">{t("upload_month_field", L)}</div>', unsafe_allow_html=True)
    upload_month = st.selectbox(
        t("ref_month", L), MONTHS, index=len(MONTHS) - 1,
        label_visibility="collapsed",
    )

    uploaded = st.file_uploader(
        t("drag_file", L),
        type=["csv", "xlsx", "xls", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if not uploaded:
        _render_dropzone_caption(L)
        return

    # ── Process each uploaded file ──
    for ufile in uploaded:
        st.markdown("---")

        ufile.seek(0)
        file_bytes = ufile.read()
        ext = Path(ufile.name).suffix.lower()
        manual_source = "auto"

        # ── Step 1: Auto-unlock ──
        was_unlocked = False
        found_pwd = None

        # Check if previously unlocked via password input
        if f"unlocked_{ufile.name}" in st.session_state:
            file_bytes = st.session_state[f"unlocked_{ufile.name}"]
            found_pwd = st.session_state.get(f"unlocked_pwd_{ufile.name}")
            was_unlocked = True

        if not was_unlocked and ext in (".xlsx", ".xls", ".pdf") and KNOWN_PASSWORDS:
            unlocked_data, pwd, status = try_unlock(file_bytes, ufile.name, KNOWN_PASSWORDS)
            if status == "unlocked":
                file_bytes = unlocked_data
                was_unlocked = True
                found_pwd = pwd
            elif status == "encrypted":
                # File is encrypted but no known password worked → stateError
                _handle_encrypted_state(L, ufile, file_bytes, ext)
                continue

        # Show unlock badge if applicable
        if was_unlocked:
            _render_info_badge(f"🔓 {t('unlock_success', L)} {found_pwd}", "green")

        # ── Step 1.5: PDF content detection ──
        das_parsed = None
        nfse_parsed = None
        if ext == ".pdf":
            das_parsed, nfse_parsed, manual_source = _detect_pdf_content(file_bytes, ufile.name, manual_source)

        # NFS-e verification card
        if nfse_parsed:
            upload_month = _render_nfse_verification(L, nfse_parsed, ufile, upload_month)

        # DAS verification card
        if das_parsed:
            upload_month, das_parsed = _render_das_verification(L, das_parsed, ufile, upload_month)

        # ── Step 2: Auto-detect source type ──
        detected_source = manual_source
        if detected_source == "auto":
            # C6 by raw content
            if ext == ".csv":
                try:
                    first_line = file_bytes[:200].decode("utf-8", errors="ignore")
                    if "C6 BANK" in first_line or "EXTRATO DE CONTA CORRENTE C6" in first_line:
                        detected_source = "extrato_c6_brl"
                except Exception:
                    pass

            if detected_source == "auto" and ext in (".csv", ".xlsx", ".xls"):
                try:
                    if ext == ".csv":
                        df_peek = try_read_csv(file_bytes, nrows=10)
                    else:
                        df_peek = pd.read_excel(io.BytesIO(file_bytes), nrows=10)
                    if df_peek is not None:
                        detected_source = auto_detect_source(df_peek, ufile.name)
                except Exception as e:
                    st.warning(f"{t('detect_error', L)}: {e}")

            # Fallback: filename
            if detected_source == "auto" or detected_source is None:
                detected_source = auto_detect_source(pd.DataFrame(), ufile.name)

        # ── stateUnknown: type not detected ──
        if not detected_source or detected_source == "auto":
            # Count rows for display
            row_count = None
            if ext in (".csv", ".xlsx", ".xls"):
                try:
                    if ext == ".csv":
                        df_tmp = try_read_csv(file_bytes)
                    else:
                        df_tmp = pd.read_excel(io.BytesIO(file_bytes), nrows=5)
                    row_count = len(df_tmp) if df_tmp is not None else None
                except Exception:
                    pass

            chosen = _handle_unknown_state(L, ufile, row_count)
            if chosen is None:
                continue
            detected_source = chosen

        # ── Step 3: stateOk path — show detection result ──
        src_name = DATA_SOURCES.get(detected_source, {}).get("name", detected_source)

        # Date coverage
        coverage = _detect_date_coverage(file_bytes, ext, detected_source)
        if coverage:
            d_min, d_max, row_count = coverage
            meta_text = f"{row_count:,} {t('rows_suffix', L)} · {d_min} → {d_max}"
        else:
            meta_text = f"{ufile.size:,} bytes"

        _render_file_status_row(ufile.name, meta_text, color="green")
        _render_info_badge(f"{t('detected_as', L)}: {src_name}", "blue")

        # Duplicate check
        dup_messages = _check_duplicates(file_bytes, upload_month, detected_source, ext)
        for msg_type, msg_text in dup_messages:
            color = "amber" if msg_type == "warn" else "blue"
            _render_info_badge(msg_text, color)

        # ── SKU classification (vendas_ml) ──
        if detected_source == "vendas_ml" and ext in (".csv", ".xlsx", ".xls"):
            _handle_sku_classification(L, ufile, file_bytes, ext)

        # ── Transaction classification (bank statements) ──
        tx_classifications = None
        tx_splits_serializable = {}
        if detected_source in ("extrato_nubank", "extrato_c6_brl", "extrato_mp") and ext == ".csv":
            tx_classifications, tx_splits_serializable = _classify_bank_transactions(
                L, ufile, file_bytes, ext, detected_source, upload_month
            )

        # ── Save button ──
        st.markdown('<div class="up-save-btn">', unsafe_allow_html=True)
        if st.button(
            f"{t('save_arrow', L)}  {detected_source} → {upload_month}",
            key=f"save_{ufile.name}",
        ):
            success = _save_file(
                ufile, file_bytes, ext, detected_source, upload_month,
                das_parsed, nfse_parsed, tx_classifications, tx_splits_serializable,
                was_unlocked, found_pwd,
            )
            if success:
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
