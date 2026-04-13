"""
Каталог SKU: тип поставщика (import/local) и себестоимость BRL.
Хранение: _data/sku_catalog.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import DATA_DIR

CATALOG_FILENAME = "sku_catalog.json"
VALID_SUPPLIER_TYPES = frozenset({"import", "local"})


def catalog_path() -> Path:
    return DATA_DIR / CATALOG_FILENAME


def normalize_sku(sku: str) -> str:
    return (sku or "").strip().upper()


def _coerce_item(it: dict[str, Any]) -> dict[str, Any] | None:
    sku_raw = str(it.get("sku", "")).strip()
    sku_key = normalize_sku(sku_raw)
    if not sku_key:
        return None
    st = str(it.get("supplier_type") or "local").lower().strip()
    if st not in VALID_SUPPLIER_TYPES:
        st = "local"
    cost_raw = it.get("unit_cost_brl")
    cost: float | None
    try:
        if cost_raw is None or cost_raw == "":
            cost = None
        else:
            c = float(cost_raw)
            cost = c if c >= 0 else None
    except (TypeError, ValueError):
        cost = None
    return {
        "sku": sku_raw,
        "supplier_type": st,
        "unit_cost_brl": cost,
        "note": str(it.get("note") or ""),
    }


def load_catalog() -> list[dict[str, Any]]:
    path = catalog_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("items") if isinstance(raw, dict) else []
        return [x for x in items if isinstance(x, dict)]
    except Exception:
        return []


def save_catalog(items: list[dict[str, Any]]) -> bool:
    """Сохранить каталог; дубликаты SKU — последняя строка побеждает."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        row = _coerce_item(it)
        if row is None:
            continue
        merged[normalize_sku(row["sku"])] = row
    out_items = [merged[k] for k in sorted(merged.keys())]
    payload = {"version": 1, "items": out_items}
    try:
        catalog_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def build_catalog_index() -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for it in load_catalog():
        row = _coerce_item(it)
        if row is None:
            continue
        idx[normalize_sku(row["sku"])] = {
            "supplier_type": row["supplier_type"],
            "unit_cost_brl": row["unit_cost_brl"],
            "note": row["note"],
        }
    return idx


def get_sku_row(sku: str) -> dict[str, Any] | None:
    return build_catalog_index().get(normalize_sku(sku))


def assess_stock_for_project(
    project: str,
    by_sku: dict[str, int] | None,
    stock_units_external: int,
    avg_cost_per_unit_brl: float | None,
) -> dict[str, Any]:
    """
    Оценка стоимости стока: явные цены из каталога; без цены — avg_cost_per_unit_brl
    (если задан); иначе SKU попадают в missing_*.
    project зарезервирован для будущих фильтров.
    """
    _ = project
    by_sku = by_sku or {}
    idx = build_catalog_index()

    total_val = 0.0
    by_supplier: dict[str, float] = {"import": 0.0, "local": 0.0, "fallback": 0.0}
    units_from_catalog = 0
    units_from_fallback = 0
    missing_skus: list[str] = []
    missing_units = 0

    avg: float | None
    try:
        if avg_cost_per_unit_brl is None:
            avg = None
        else:
            a = float(avg_cost_per_unit_brl)
            avg = a if a > 0 else None
    except (TypeError, ValueError):
        avg = None

    for sku, qty in by_sku.items():
        q = int(qty) if qty else 0
        if q <= 0:
            continue
        key = normalize_sku(str(sku))
        row = idx.get(key)
        cost: float | None = None
        if row and row.get("unit_cost_brl") is not None:
            try:
                c = float(row["unit_cost_brl"])
                if c > 0:
                    cost = c
            except (TypeError, ValueError):
                pass
        if cost is not None:
            line = q * cost
            total_val += line
            units_from_catalog += q
            st = row["supplier_type"]
            if st not in by_supplier:
                st = "local"
            by_supplier[st] = by_supplier.get(st, 0) + line
        elif avg is not None:
            total_val += q * avg
            units_from_fallback += q
            by_supplier["fallback"] += q * avg
        else:
            missing_skus.append(str(sku).strip())
            missing_units += q

    ext = int(stock_units_external or 0)
    if ext > 0:
        if avg is not None:
            total_val += ext * avg
            units_from_fallback += ext
            by_supplier["fallback"] += ext * avg
        else:
            missing_units += ext

    return {
        "stock_value_brl": round(total_val, 2),
        "by_supplier_type": {k: round(v, 2) for k, v in by_supplier.items() if v > 0},
        "units_from_catalog": units_from_catalog,
        "units_from_fallback": units_from_fallback,
        "missing_skus": sorted(set(missing_skus)),
        "missing_units": missing_units,
    }
