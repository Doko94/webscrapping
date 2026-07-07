from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# =========================================================
# RUTAS
# =========================================================
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = SRC_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_DIR = OUTPUT_DIR / "carrito_comparado"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CART_TXT = SCRIPT_DIR / "carrito.txt"


# =========================================================
# HELPERS TEXTO
# =========================================================
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).lower()
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9\s/_\-.x]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(text: str) -> list[str]:
    txt = clean_text(text)
    return [t for t in txt.split() if t]


def contains_any(text: str, phrases: list[str]) -> bool:
    t = clean_text(text)
    return any(clean_text(p) in t for p in phrases)


def contains_word(text: str, word: str) -> bool:
    t = clean_text(text)
    w = clean_text(word)
    return re.search(rf"\b{re.escape(w)}\b", t) is not None


# =========================================================
# HELPERS NUMÉRICOS
# =========================================================
def safe_to_float(x) -> float:
    if pd.isna(x):
        return np.nan

    s = str(x).strip().lower()
    s = s.replace("$", "").replace("clp", "").replace(" ", "")

    if "." in s and "," not in s:
        s = s.replace(".", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except Exception:
        return np.nan


def normalize_unit_family(unit: Optional[str]) -> Optional[str]:
    if unit is None or pd.isna(unit):
        return None

    u = str(unit).strip().lower()

    if u in {"kg", "g", "gr"}:
        return "mass"
    if u in {"l", "lt", "ml", "cc"}:
        return "volume"
    if u in {"un", "unidad", "unidades"}:
        return "unit"

    return None


def convert_to_std(value: float, unit: str) -> float:
    if pd.isna(value) or unit is None or pd.isna(unit):
        return np.nan

    u = str(unit).strip().lower()

    if u == "kg":
        return value * 1000
    if u in {"g", "gr"}:
        return value
    if u in {"l", "lt"}:
        return value * 1000
    if u in {"ml", "cc"}:
        return value
    if u in {"un", "unidad", "unidades"}:
        return value

    return np.nan


SIZE_PATTERNS = [
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|l|lt|ml|cc)\b", re.I),
    re.compile(r"\b(\d+)\s*(un|unidad|unidades)\b", re.I),
    re.compile(r"\bx\s*(\d+)\b", re.I),
]


def parse_size_from_text(text: str) -> tuple[float, Optional[str]]:
    txt = clean_text(text)

    for pat in SIZE_PATTERNS:
        m = pat.search(txt)
        if m:
            value = safe_to_float(m.group(1))
            unit = m.group(2) if len(m.groups()) >= 2 else "un"
            if unit == "x":
                unit = "un"
            return value, unit.lower()

    return np.nan, None


def robust_unit_family(row: pd.Series) -> Optional[str]:
    uf = normalize_unit_family(row.get("unit", None))
    if uf is not None:
        return uf

    _, name_unit = parse_size_from_text(row.get("name", ""))
    return normalize_unit_family(name_unit)


def robust_size_std(row: pd.Series) -> float:
    raw_unit = str(row.get("unit", "")).strip().lower()
    raw_nc = row.get("net_content", np.nan)

    nc_num = safe_to_float(raw_nc)
    unit_family = normalize_unit_family(raw_unit)

    if pd.notna(nc_num) and unit_family is not None:
        std = convert_to_std(nc_num, raw_unit)
        if pd.notna(std):
            return std

    name_val, name_unit = parse_size_from_text(row.get("name", ""))
    if pd.notna(name_val) and name_unit is not None:
        std = convert_to_std(name_val, name_unit)
        if pd.notna(std):
            return std

    return np.nan


# =========================================================
# IO
# =========================================================
def latest_csv_by_prefix(folder: Path, prefix: str) -> Optional[Path]:
    files = sorted(folder.glob(f"{prefix}*.csv"))
    return files[-1] if files else None


def load_csv_robust(path: Path) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        for sep in [",", ";"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception:
                pass
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", low_memory=False)


def export_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")


def read_cart_txt(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"No encontré el carrito: {path}")

    items = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            items.append(s)

    if not items:
        raise ValueError("El carrito.txt no contiene productos válidos")

    return items


# =========================================================
# MODELO DE CONSULTA
# =========================================================
@dataclass
class CartQuery:
    raw_text: str
    clean_query: str
    tokens: list[str]
    desired_size_std: Optional[float]
    desired_unit_family: Optional[str]


def build_cart_queries(items: list[str]) -> list[CartQuery]:
    out = []
    for item in items:
        size_val, size_unit = parse_size_from_text(item)
        desired_unit_family = normalize_unit_family(size_unit)
        desired_size_std = convert_to_std(size_val, size_unit) if pd.notna(size_val) and size_unit else np.nan

        out.append(
            CartQuery(
                raw_text=item,
                clean_query=clean_text(item),
                tokens=tokenize(item),
                desired_size_std=desired_size_std if pd.notna(desired_size_std) else np.nan,
                desired_unit_family=desired_unit_family,
            )
        )
    return out


# =========================================================
# PREPARACIÓN DEL CATÁLOGO
# =========================================================
def prepare_catalog(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    required = [
        "sku", "name", "brand", "price", "list_price", "discount_price",
        "net_content", "unit", "detail_url", "category_std", "subcategory",
        "last_category", "supermarket"
    ]
    for c in required:
        if c not in df.columns:
            df[c] = np.nan

    df["name_clean"] = df["name"].apply(clean_text)
    df["brand_clean"] = df["brand"].apply(clean_text)
    df["category_std_clean"] = df["category_std"].apply(clean_text)
    df["subcategory_clean"] = df["subcategory"].apply(clean_text)
    df["last_category_clean"] = df["last_category"].apply(clean_text)

    df["all_text"] = (
        df["name_clean"].fillna("") + " " +
        df["brand_clean"].fillna("") + " " +
        df["category_std_clean"].fillna("") + " " +
        df["subcategory_clean"].fillna("") + " " +
        df["last_category_clean"].fillna("")
    ).str.strip()

    # list_price manda
    df["list_price_num"] = df["list_price"].apply(safe_to_float)
    df["price_num"] = df["price"].apply(safe_to_float)
    df["discount_price_num"] = df["discount_price"].apply(safe_to_float)

    df["effective_price"] = df["list_price_num"].fillna(df["price_num"])

    df["unit_family"] = df.apply(robust_unit_family, axis=1)
    df["size_std"] = df.apply(robust_size_std, axis=1)

    df = df[df["effective_price"].notna()].copy()
    df = df[(df["effective_price"] > 100) & (df["effective_price"] < 500000)].copy()

    return df


# =========================================================
# MATCHING CARRITO
# =========================================================
GLOBAL_EXCLUDES = [
    "perro", "gato", "mascota", "pet", "alimento perro", "alimento de perro",
]


def compute_match_score(row: pd.Series, query: CartQuery) -> float:
    text = row["all_text"]
    name = row["name_clean"]
    category = row["category_std_clean"]
    brand = row["brand_clean"]
    score = 0.0

    if contains_any(text, GLOBAL_EXCLUDES):
        return -999.0

    token_hits = 0
    valid_tokens = [tok for tok in query.tokens if len(tok) > 1]

    for tok in valid_tokens:
        if contains_word(text, tok):
            token_hits += 1
            score += 3
        if contains_word(name, tok):
            score += 2

    if token_hits == 0:
        return -999.0

    coverage = token_hits / max(len(valid_tokens), 1)
    score += coverage * 5

    for tok in valid_tokens:
        if contains_word(category, tok):
            score += 1
        if contains_word(brand, tok):
            score += 0.5

    if query.desired_unit_family and row["unit_family"] == query.desired_unit_family:
        score += 2

    if pd.notna(query.desired_size_std) and pd.notna(row["size_std"]) and query.desired_size_std > 0:
        diff_ratio = abs(row["size_std"] - query.desired_size_std) / query.desired_size_std
        score += max(0, 4 - diff_ratio * 4)

    return score


def find_candidates_for_query(df_catalog: pd.DataFrame, query: CartQuery, top_n_per_market: int = 5) -> pd.DataFrame:
    tmp = df_catalog.copy()
    tmp["cart_query"] = query.raw_text
    tmp["match_score"] = tmp.apply(lambda r: compute_match_score(r, query), axis=1)

    tmp = tmp[tmp["match_score"] > 0].copy()
    if tmp.empty:
        return tmp

    q_tokens = [t for t in query.tokens if len(t) > 2]
    if q_tokens:
        strong_mask = tmp["name_clean"].apply(
            lambda x: any(contains_word(x, tok) for tok in q_tokens)
        )
        tmp = tmp[strong_mask].copy()

    if tmp.empty:
        return tmp

    tmp = tmp.sort_values(
        ["supermarket", "match_score", "effective_price"],
        ascending=[True, False, True],
        na_position="last",
    )

    tmp = tmp.groupby("supermarket", as_index=False).head(top_n_per_market)
    return tmp


def build_best_per_market(df_candidates: pd.DataFrame) -> pd.DataFrame:
    if df_candidates.empty:
        return pd.DataFrame()

    out = (
        df_candidates.sort_values(
            ["cart_query", "supermarket", "match_score", "effective_price"],
            ascending=[True, True, False, True],
            na_position="last",
        )
        .groupby(["cart_query", "supermarket"], as_index=False)
        .first()
    )
    return out


def build_summary_high_level(df_best_market: pd.DataFrame) -> pd.DataFrame:
    if df_best_market.empty:
        return pd.DataFrame()

    best_low = (
        df_best_market.sort_values(
            ["cart_query", "effective_price", "match_score"],
            ascending=[True, True, False],
            na_position="last",
        )
        .groupby("cart_query", as_index=False)
        .first()
        .rename(columns={
            "supermarket": "supermercado_mas_conveniente",
            "sku": "sku_mas_conveniente",
            "name": "producto_mas_conveniente",
            "brand": "marca_mas_conveniente",
            "effective_price": "precio_mas_bajo",
            "detail_url": "url_mas_conveniente",
            "match_score": "score_mas_conveniente",
        })
    )

    best_high = (
        df_best_market.sort_values(
            ["cart_query", "effective_price", "match_score"],
            ascending=[True, False, False],
            na_position="last",
        )
        .groupby("cart_query", as_index=False)
        .first()
        .rename(columns={
            "supermarket": "supermercado_mas_caro",
            "sku": "sku_mas_caro",
            "name": "producto_mas_caro",
            "brand": "marca_mas_caro",
            "effective_price": "precio_mas_alto",
            "detail_url": "url_mas_caro",
            "match_score": "score_mas_caro",
        })
    )

    pivot_prices = (
        df_best_market.pivot_table(
            index="cart_query",
            columns="supermarket",
            values="effective_price",
            aggfunc="first"
        )
        .reset_index()
    )
    pivot_prices.columns = [f"precio_{c}" if c != "cart_query" else c for c in pivot_prices.columns]

    coverage = (
        df_best_market.groupby("cart_query")["supermarket"]
        .nunique()
        .reset_index(name="supermercados_encontrados")
    )

    summary = (
        best_low.merge(best_high, on="cart_query", how="left")
        .merge(pivot_prices, on="cart_query", how="left")
        .merge(coverage, on="cart_query", how="left")
    )

    summary["ahorro_abs"] = summary["precio_mas_alto"] - summary["precio_mas_bajo"]
    summary["ahorro_pct_vs_mas_caro"] = np.where(
        summary["precio_mas_alto"] > 0,
        (summary["ahorro_abs"] / summary["precio_mas_alto"] * 100).round(2),
        np.nan,
    )

    summary = summary.rename(columns={"cart_query": "producto_buscado"})

    cols = [
        "producto_buscado",
        "supermercados_encontrados",
        "supermercado_mas_conveniente",
        "producto_mas_conveniente",
        "marca_mas_conveniente",
        "precio_mas_bajo",
        "supermercado_mas_caro",
        "producto_mas_caro",
        "marca_mas_caro",
        "precio_mas_alto",
        "ahorro_abs",
        "ahorro_pct_vs_mas_caro",
        "precio_jumbo",
        "precio_lider",
        "precio_unimarc",
        "url_mas_conveniente",
        "url_mas_caro",
    ]
    for c in cols:
        if c not in summary.columns:
            summary[c] = np.nan

    return summary[cols].copy()


def build_executive_total(df_summary: pd.DataFrame) -> pd.DataFrame:
    if df_summary.empty:
        return pd.DataFrame()

    total_items = len(df_summary)
    encontrados = int((df_summary["supermercados_encontrados"] > 0).sum())
    total_bajo = df_summary["precio_mas_bajo"].sum()
    total_alto = df_summary["precio_mas_alto"].sum()
    ahorro_total = total_alto - total_bajo
    ahorro_pct = (ahorro_total / total_alto * 100) if total_alto > 0 else np.nan

    supermercado_ganador = (
        df_summary["supermercado_mas_conveniente"]
        .value_counts(dropna=True)
        .reset_index()
    )
    supermercado_ganador.columns = ["supermercado", "items_ganados"]

    top = supermercado_ganador.iloc[0]["supermercado"] if not supermercado_ganador.empty else None

    out = pd.DataFrame([{
        "items_carrito": total_items,
        "items_con_match": encontrados,
        "cobertura_pct": round(encontrados / total_items * 100, 2) if total_items > 0 else np.nan,
        "costo_total_mas_conveniente": round(total_bajo, 0),
        "costo_total_mas_alto": round(total_alto, 0),
        "ahorro_total": round(ahorro_total, 0),
        "ahorro_pct_vs_mas_caro": round(ahorro_pct, 2) if pd.notna(ahorro_pct) else np.nan,
        "supermercado_que_gana_mas_items": top,
    }])

    return out


# =========================================================
# PIPELINE
# =========================================================
def run_pipeline() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    consolidado_path = latest_csv_by_prefix(OUTPUT_DIR / "consolidado", "supermercados_consolidado")
    if consolidado_path is None or not consolidado_path.exists():
        raise FileNotFoundError("No encontré supermercados_consolidado*.csv en src/output")

    if not CART_TXT.exists():
        raise FileNotFoundError(f"No encontré carrito.txt en {SCRIPT_DIR}")

    print(f"[INFO] Leyendo consolidado: {consolidado_path}")
    print(f"[INFO] Leyendo carrito: {CART_TXT}")

    df_consolidado = load_csv_robust(consolidado_path)
    cart_items = read_cart_txt(CART_TXT)
    cart_queries = build_cart_queries(cart_items)

    df_catalog = prepare_catalog(df_consolidado)

    candidate_frames = []
    for q in cart_queries:
        tmp = find_candidates_for_query(df_catalog, q, top_n_per_market=5)
        if not tmp.empty:
            candidate_frames.append(tmp)

    df_candidates = pd.concat(candidate_frames, ignore_index=True) if candidate_frames else pd.DataFrame()
    df_best_market = build_best_per_market(df_candidates)
    df_summary = build_summary_high_level(df_best_market)
    df_exec = build_executive_total(df_summary)

    return df_candidates, df_best_market, df_summary, df_exec


def main():
    df_candidates, df_best_market, df_summary, df_exec = run_pipeline()

    export_csv(df_candidates, OUT_DIR / "carrito_candidatos.csv")
    export_csv(df_best_market, OUT_DIR / "carrito_mejor_por_supermercado.csv")
    export_csv(df_summary, OUT_DIR / "carrito_resumen_ejecutivo.csv")
    export_csv(df_exec, OUT_DIR / "carrito_totales_ejecutivos.csv")

    print(f"[OK] candidatos: {len(df_candidates)}")
    print(f"[OK] mejor por supermercado: {len(df_best_market)}")
    print(f"[OK] resumen ejecutivo: {len(df_summary)}")
    print(f"[OK] totales ejecutivos: {len(df_exec)}")
    print(f"[OK] Archivos generados en: {OUT_DIR}")

# hola
if __name__ == "__main__":
    main()