from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


API_DIR = Path(__file__).resolve().parent
SRC_DIR = API_DIR.parent
OUTPUT_DIR = SRC_DIR / "output"
CONSOLIDADO_DIR = OUTPUT_DIR / "consolidado"
CBA_DIR = OUTPUT_DIR / "cba"
CBA_AHORRO_DIR = CBA_DIR / "ahorro"
CART_DIR = OUTPUT_DIR / "carrito_comparado"
ECONOMIC_DIR = OUTPUT_DIR / "cba_escenario1_economico"
PREMIUM_DIR = OUTPUT_DIR / "cba_escenario_premium"
OUT_CBA_DIR = OUTPUT_DIR / "out_cba"


CSV_CANDIDATES = {
    "consolidado": (CONSOLIDADO_DIR, "supermercados_consolidado"),
    "productos_baratos": (CONSOLIDADO_DIR, "productos_baratos"),
    "cba_resumen": (CBA_DIR, "cba_resumen_supermercado"),
    "cba_optima": (CBA_DIR, "cba_canasta_optima"),
    "cba_cobertura": (CBA_DIR, "cba_cobertura"),
    "cba_ahorro": (CBA_AHORRO_DIR, "cba_ahorro_supermercado"),
    "cba_ranking": (CBA_AHORRO_DIR, "cba_ranking_supermercados"),
    "cart_summary": (CART_DIR, "carrito_resumen_ejecutivo"),
    "cart_total": (CART_DIR, "carrito_totales_ejecutivos"),
    "economic_total": (ECONOMIC_DIR, "cba_econ_total_por_supermercado"),
    "economic_summary": (ECONOMIC_DIR, "cba_econ_resumen_final"),
    "premium_total": (PREMIUM_DIR, "cba_premium_total_por_supermercado"),
    "premium_summary": (PREMIUM_DIR, "cba_premium_resumen_final"),
    "official_cba": (OUT_CBA_DIR, "cba_anexo1_diciembre2025"),
}


def latest_csv_by_prefix(folder: Path, prefix: str) -> Path | None:
    if not folder.exists():
        return None

    files = sorted(folder.glob(f"{prefix}*.csv"))
    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def get_csv_path(key: str) -> Path | None:
    folder, prefix = CSV_CANDIDATES[key]
    return latest_csv_by_prefix(folder, prefix)


def read_csv_robust(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (";", ","):
            try:
                df = pd.read_csv(path, sep=sep, encoding=encoding, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue

    return pd.read_csv(path, encoding="utf-8-sig")


@lru_cache(maxsize=32)
def load_csv_cached(path_text: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    return read_csv_robust(Path(path_text))


def load_dataset(key: str) -> pd.DataFrame:
    path = get_csv_path(key)
    if path is None or not path.exists():
        return pd.DataFrame()

    return load_csv_cached(str(path), path.stat().st_mtime).copy()


def dataset_file_info(key: str) -> dict[str, Any]:
    path = get_csv_path(key)
    if path is None or not path.exists():
        return {
            "key": key,
            "exists": False,
            "path": None,
            "rows": 0,
            "updated_at": None,
        }

    df = load_dataset(key)
    return {
        "key": key,
        "exists": True,
        "path": str(path),
        "file_name": path.name,
        "rows": int(len(df)),
        "updated_at": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
    }


def clean_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []

    out = df.copy()
    if limit is not None:
        out = out.head(limit)

    out = out.replace({np.nan: None})
    return [make_json_safe(record) for record in out.to_dict(orient="records")]


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NaT:
        return None
    return value


def normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def searchable_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in ("name", "brand", "category", "subcategory", "last_category", "category_std") if col in df.columns]
