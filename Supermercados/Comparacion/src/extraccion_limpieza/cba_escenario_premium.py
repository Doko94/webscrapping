from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass, field
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

OUT_CBA_DIR = OUTPUT_DIR / "out_cba"
OUT_CBA_DIR.mkdir(parents=True, exist_ok=True)


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


def contains_any(text: str, phrases: list[str]) -> bool:
    t = clean_text(text)
    return any(clean_text(p) in t for p in phrases)


def contains_all(text: str, phrases: list[str]) -> bool:
    t = clean_text(text)
    return all(clean_text(p) in t for p in phrases)


def contains_word(text: str, word: str) -> bool:
    t = clean_text(text)
    w = clean_text(word)
    return re.search(rf"\b{re.escape(w)}\b", t) is not None


def contains_any_word(text: str, words: list[str]) -> bool:
    return any(contains_word(text, w) for w in words)


def contains_all_words(text: str, words: list[str]) -> bool:
    return all(contains_word(text, w) for w in words)


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


def parse_price_per_unit(x) -> float:
    if pd.isna(x):
        return np.nan
    s = str(x).lower()
    m = re.search(r"([\d\.,]+)", s)
    if not m:
        return np.nan
    return safe_to_float(m.group(1))


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


def parse_size_from_name(name: str) -> tuple[float, Optional[str]]:
    txt = clean_text(name)

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

    _, name_unit = parse_size_from_name(row.get("name", ""))
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

    name_val, name_unit = parse_size_from_name(row.get("name", ""))
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


def ensure_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    return df


def find_cba_csv() -> Path:
    candidates = [
        OUT_CBA_DIR / "cba_anexo1_diciembre2025.csv",
        OUTPUT_DIR / "cba_anexo1_diciembre2025.csv",
        SCRIPT_DIR / "cba_anexo1_diciembre2025.csv",
        SCRIPT_DIR / "output" / "cba_anexo1_diciembre2025.csv",
        SRC_DIR / "output" / "cba_anexo1_diciembre2025.csv",
    ]

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        "No encontré cba_anexo1_diciembre2025.csv en ninguna de estas rutas:\n"
        + "\n".join(str(x) for x in candidates)
    )


# =========================================================
# ESPECIFICACIÓN PREMIUM
# =========================================================
@dataclass
class PremiumSpec:
    cba_name: str
    formato_objetivo: str
    include_any: list[str] = field(default_factory=list)
    include_all: list[str] = field(default_factory=list)
    exclude_any: list[str] = field(default_factory=list)
    category_any: list[str] = field(default_factory=list)
    subcategory_any: list[str] = field(default_factory=list)
    last_category_any: list[str] = field(default_factory=list)

    include_name_words_any: list[str] = field(default_factory=list)
    include_name_words_all: list[str] = field(default_factory=list)
    exclude_name_any: list[str] = field(default_factory=list)

    preferred_brands: list[str] = field(default_factory=list)

    unit_family: Optional[str] = None
    target_size_std: Optional[float] = None
    min_size_std: Optional[float] = None
    max_size_std: Optional[float] = None
    top_n_per_market: int = 12


PREMIUM_SPECS: list[PremiumSpec] = [
PremiumSpec(
    "Arroz", "1 kg premium",
    include_any=["arroz", "basmati", "jazmin", "arborio"],
    include_name_words_any=["arroz", "basmati", "jazmin", "arborio"],
    exclude_any=["inflado", "cereal", "galleta", "barra", "sazonador", "condimento", "sopa", "preparado"],
    exclude_name_any=["inflado", "cereal", "galleta", "barra", "sazonador", "condimento", "preparado"],
    preferred_brands=["taj mahal", "miraflores", "tucapel", "los boldos", "carozzi"],
    subcategory_any=["arroz"],
    last_category_any=["arroz"],
    unit_family="mass",
    target_size_std=1000,
    min_size_std=350,
    max_size_std=1200
),
    PremiumSpec(
        "Aceite vegetal combinado o puro", "1 litro premium",
        include_any=["aceite"],
        include_name_words_any=["aceite"],
        exclude_any=["vinagre", "jugo", "limon", "sucedaneo", "spray"],
        exclude_name_any=["vinagre", "jugo", "limon", "sucedaneo", "spray"],
        preferred_brands=["mazola", "chef", "miraflores"],
        category_any=["despensa", "aceites", "aceites y aderezos"],
        subcategory_any=["aceites"],
        last_category_any=["aceites", "aceite"],
        unit_family="volume", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    PremiumSpec(
        "Avena", "500 g premium",
        include_any=["avena"],
        include_name_words_any=["avena"],
        exclude_any=["yogurt", "yoghurt", "bebida", "granola", "barra", "galleta"],
        exclude_name_any=["yogurt", "yoghurt", "bebida", "granola", "barra", "galleta"],
        preferred_brands=["quaker", "selecta"],
        unit_family="mass", target_size_std=500, min_size_std=300, max_size_std=1000
    ),
    PremiumSpec(
        "Leche líquida entera", "1 litro premium",
        include_all=["leche", "entera"],
        include_name_words_all=["leche", "entera"],
        exclude_any=["sin lactosa", "descremada", "semidescremada", "almendra", "soya", "polvo"],
        exclude_name_any=["sin", "lactosa", "descremada", "semidescremada", "almendra", "soya", "polvo"],
        preferred_brands=["colun", "soprole", "nestle"],
        subcategory_any=["leche", "leches"],
        last_category_any=["leche"],
        unit_family="volume", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    PremiumSpec(
        "Yogurt", "premium tradicional",
        include_any=["yogurt", "yoghurt"],
        include_name_words_any=["yogurt", "yoghurt"],
        exclude_any=["proteina", "protein", "avena"],
        exclude_name_any=["proteina", "protein", "avena"],
        preferred_brands=["soprole", "colun", "nestle"],
        subcategory_any=["yogurt"],
        last_category_any=["yogurt", "batido"],
        unit_family="mass", min_size_std=80, max_size_std=1200
    ),
    PremiumSpec(
        "Queso gouda", "premium",
        include_all=["queso", "gouda"],
        include_name_words_all=["queso", "gouda"],
        exclude_any=["crema", "snack"],
        exclude_name_any=["crema", "snack"],
        preferred_brands=["colun", "quillaipes", "soprole"],
        unit_family="mass", min_size_std=100, max_size_std=600
    ),
    PremiumSpec(
        "Chocolate", "barra premium",
        include_any=["chocolate"],
        include_name_words_any=["chocolate"],
        exclude_any=["flan", "mousse", "postre", "cereal", "galleta"],
        exclude_name_any=["flan", "mousse", "postre", "cereal", "galleta"],
        preferred_brands=["trencito", "milka", "nestle"],
        category_any=["chocolates", "dulces", "snacks"],
        unit_family="mass", min_size_std=30, max_size_std=250
    ),
    PremiumSpec(
        "Jamón de cerdo", "premium",
        include_any=["jamon"],
        include_name_words_any=["jamon"],
        exclude_any=["mortadela", "chorizo", "salame"],
        exclude_name_any=["mortadela", "chorizo", "salame"],
        preferred_brands=["la preferida", "pf", "winter"],
        category_any=["fiambres", "quesos y fiambres"],
        unit_family="mass", min_size_std=80, max_size_std=600
    ),
    PremiumSpec(
        "Paté", "premium",
        include_any=["pate"],
        include_name_words_any=["pate"],
        exclude_any=["jamon", "mortadela", "chorizo"],
        exclude_name_any=["jamon", "mortadela", "chorizo"],
        preferred_brands=["winter", "pf"],
        category_any=["fiambres", "pate"],
        unit_family="mass", min_size_std=80, max_size_std=300
    ),
    PremiumSpec(
        "Pechuga de pollo", "premium",
        include_any=["pollo"],
        include_all=["pechuga"],
        include_name_words_all=["pechuga"],
        exclude_any=["trutro", "ala", "entero", "apanado", "nugget", "molida"],
        exclude_name_any=["trutro", "ala", "entero", "apanado", "nugget", "molida"],
        preferred_brands=["super pollo", "ariztia"],
        category_any=["carnes", "carnes y pescados"],
        subcategory_any=["pollo"],
        last_category_any=["pechuga"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    PremiumSpec(
        "Trutro de pollo", "premium",
        include_all=["trutro", "pollo"],
        include_name_words_all=["trutro"],
        exclude_any=["pechuga", "apanado", "panitas"],
        exclude_name_any=["pechuga", "apanado", "panitas"],
        preferred_brands=["super pollo", "ariztia"],
        category_any=["carnes", "carnes y pescados"],
        subcategory_any=["pollo"],
        last_category_any=["trutro"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
]


# =========================================================
# PREPARACIÓN DE DATOS
# =========================================================
def prepare_products(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_columns(
        df,
        [
            "sku", "supermarket", "name", "brand", "price", "list_price",
            "discount_price", "in_offer", "net_content", "unit", "price_per_unit",
            "price_per_unit_list", "saving_text", "image_url", "detail_url",
            "category_std", "subcategory", "last_category"
        ],
    ).copy()

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

    # price manda como antes
    df["list_price_num"] = df["list_price"].apply(safe_to_float)
    df["fallback_price_num"] = df["price"].apply(safe_to_float)
    df["price_num"] = df["list_price_num"].fillna(df["fallback_price_num"])

    # info extra
    df["discount_price_num"] = df["discount_price"].apply(safe_to_float)
    df["price_per_unit_web"] = df["price_per_unit"].apply(parse_price_per_unit)
    df["price_per_unit_list_web"] = df["price_per_unit_list"].apply(parse_price_per_unit)

    df["unit_family"] = df.apply(robust_unit_family, axis=1)
    df["size_std"] = df.apply(robust_size_std, axis=1)

    df["price_per_std_unit_calc"] = np.where(
        df["price_num"].notna() & df["size_std"].notna() & (df["size_std"] > 0),
        df["price_num"] / df["size_std"],
        np.nan,
    )

    df = df[df["price_num"].notna()].copy()
    df = df[(df["price_num"] > 100) & (df["price_num"] < 500000)].copy()

    return df


# =========================================================
# MATCHER PREMIUM
# =========================================================
def row_matches_spec(row: pd.Series, spec: PremiumSpec) -> bool:
    text = row.get("all_text", "")
    name = row.get("name_clean", "")
    category = row.get("category_std_clean", "")
    subcat = row.get("subcategory_clean", "")
    lastcat = row.get("last_category_clean", "")
    unit_family = row.get("unit_family", None)
    size_std = row.get("size_std", np.nan)
    price_num = row.get("price_num", np.nan)

    if pd.isna(price_num) or price_num <= 0:
        return False

    if contains_any(text, ["perro", "gato", "mascota", "pet", "alimento perro"]):
        return False

    if spec.include_any and not contains_any(text, spec.include_any):
        return False

    if spec.include_all and not contains_all(text, spec.include_all):
        return False

    if spec.include_name_words_any and not contains_any_word(name, spec.include_name_words_any):
        return False

    if spec.include_name_words_all and not contains_all_words(name, spec.include_name_words_all):
        return False

    if spec.exclude_any and contains_any(text, spec.exclude_any):
        return False

    if spec.exclude_name_any and contains_any(name, spec.exclude_name_any):
        return False

    if spec.category_any and category:
        if not contains_any(category, spec.category_any):
            return False

    if spec.subcategory_any and subcat:
        if not contains_any(subcat, spec.subcategory_any):
            return False

    if spec.last_category_any and lastcat:
        if not contains_any(lastcat, spec.last_category_any):
            return False

    if spec.unit_family and unit_family != spec.unit_family:
        return False

    if pd.notna(size_std):
        if spec.min_size_std is not None and size_std < spec.min_size_std:
            return False
        if spec.max_size_std is not None and size_std > spec.max_size_std:
            return False

    return True


def compute_premium_score(row: pd.Series, spec: PremiumSpec) -> float:
    score = 0.0
    text = row.get("all_text", "")
    name = row.get("name_clean", "")
    brand = row.get("brand_clean", "")
    category = row.get("category_std_clean", "")
    subcat = row.get("subcategory_clean", "")
    lastcat = row.get("last_category_clean", "")
    size_std = row.get("size_std", np.nan)

    if spec.include_any and contains_any(text, spec.include_any):
        score += 2

    if spec.include_all and contains_all(text, spec.include_all):
        score += 2

    if spec.include_name_words_any and contains_any_word(name, spec.include_name_words_any):
        score += 4

    if spec.include_name_words_all and contains_all_words(name, spec.include_name_words_all):
        score += 5

    if spec.category_any and contains_any(category, spec.category_any):
        score += 1

    if spec.subcategory_any and contains_any(subcat, spec.subcategory_any):
        score += 1.5

    if spec.last_category_any and contains_any(lastcat, spec.last_category_any):
        score += 1.5

    if spec.preferred_brands and contains_any(brand, spec.preferred_brands):
        score += 4

    if pd.notna(size_std) and spec.target_size_std is not None:
        diff = abs(size_std - spec.target_size_std)
        score += max(0, 3 - (diff / max(spec.target_size_std, 1)) * 3)

    return score


def build_candidates(df_products: pd.DataFrame) -> pd.DataFrame:
    frames = []

    for spec in PREMIUM_SPECS:
        tmp = df_products[df_products.apply(lambda r: row_matches_spec(r, spec), axis=1)].copy()

        if tmp.empty:
            continue

        tmp["cba_name"] = spec.cba_name
        tmp["formato_objetivo"] = spec.formato_objetivo
        tmp["premium_score"] = tmp.apply(lambda r: compute_premium_score(r, spec), axis=1)

        # premium: primero score, luego list_price
        tmp = tmp.sort_values(
            ["supermarket", "premium_score", "price_num"],
            ascending=[True, False, True],
            na_position="last",
        )

        tmp = tmp.groupby("supermarket", as_index=False).head(spec.top_n_per_market)
        frames.append(tmp)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)

    keep = [
        "cba_name", "formato_objetivo", "supermarket", "sku", "name", "brand",
        "price_num", "list_price_num", "fallback_price_num", "discount_price_num",
        "unit", "net_content", "unit_family", "size_std",
        "price_per_unit_web", "price_per_unit_list_web", "price_per_std_unit_calc",
        "category_std", "subcategory", "last_category",
        "premium_score", "detail_url"
    ]
    out = ensure_columns(out, keep)
    return out[keep].copy()


def build_best_by_market(df_candidates: pd.DataFrame) -> pd.DataFrame:
    if df_candidates.empty:
        return pd.DataFrame()

    out = (
        df_candidates.sort_values(
            ["cba_name", "supermarket", "premium_score", "price_num"],
            ascending=[True, True, False, True],
            na_position="last",
        )
        .groupby(["cba_name", "supermarket"], as_index=False)
        .first()
    )
    return out


def build_final_summary(df_best_market: pd.DataFrame) -> pd.DataFrame:
    if df_best_market.empty:
        return pd.DataFrame()

    winners = (
        df_best_market.sort_values(
            ["cba_name", "premium_score", "price_num"],
            ascending=[True, False, True],
            na_position="last",
        )
        .groupby("cba_name", as_index=False)
        .first()
        .rename(columns={
            "supermarket": "best_supermarket",
            "sku": "best_sku",
            "name": "best_name",
            "brand": "best_brand",
            "price_num": "best_price_num",
            "unit": "best_unit",
            "net_content": "best_net_content",
            "unit_family": "best_unit_family",
            "size_std": "best_size_std",
            "discount_price_num": "best_discount_price_num",
            "price_per_unit_web": "best_price_per_unit_web",
            "price_per_unit_list_web": "best_price_per_unit_list_web",
            "price_per_std_unit_calc": "best_price_per_std_unit_calc",
            "category_std": "best_category_std",
            "subcategory": "best_subcategory",
            "last_category": "best_last_category",
            "premium_score": "best_premium_score",
            "detail_url": "best_detail_url",
        })
    )

    price_pivot = (
        df_best_market.pivot_table(
            index="cba_name",
            columns="supermarket",
            values="price_num",
            aggfunc="first"
        )
        .reset_index()
    )
    price_pivot.columns = [f"price_{c}" if c != "cba_name" else c for c in price_pivot.columns]

    coverage = df_best_market.groupby("cba_name")["supermarket"].nunique().reset_index(name="supermarkets_found")

    summary = winners.merge(price_pivot, on="cba_name", how="left").merge(coverage, on="cba_name", how="left")

    cols = [
        "cba_name", "formato_objetivo", "supermarkets_found",
        "best_supermarket", "best_name", "best_brand", "best_price_num",
        "best_unit", "best_net_content", "best_unit_family", "best_size_std",
        "best_discount_price_num", "best_price_per_unit_web",
        "best_price_per_unit_list_web", "best_price_per_std_unit_calc",
        "best_category_std", "best_subcategory", "best_last_category",
        "best_premium_score", "best_detail_url",
        "price_jumbo", "price_lider", "price_unimarc",
    ]
    summary = ensure_columns(summary, cols)
    return summary[cols].copy()


def build_total_cost_by_market(df_best_market: pd.DataFrame, df_cba: pd.DataFrame) -> pd.DataFrame:
    if df_best_market.empty:
        return pd.DataFrame()

    total = (
        df_best_market.groupby("supermarket", as_index=False)
        .agg(
            total_cba_premium=("price_num", "sum"),
            productos_encontrados=("cba_name", "nunique")
        )
        .sort_values("total_cba_premium", ascending=True)
        .reset_index(drop=True)
    )

    total["ranking_premium"] = total.index + 1
    total["productos_cba_objetivo"] = len(df_cba)

    total["cobertura_pct"] = np.where(
        total["productos_cba_objetivo"] > 0,
        (total["productos_encontrados"] / total["productos_cba_objetivo"] * 100).round(2),
        np.nan
    )

    total["cobertura_pct_fmt"] = total["cobertura_pct"].map(
        lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else None
    )

    return total


# =========================================================
# PIPELINE
# =========================================================
def run_pipeline(input_csv: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    consolidado_path = Path(input_csv) if input_csv else latest_csv_by_prefix(OUTPUT_DIR / "consolidado", "supermercados_consolidado")
    if consolidado_path is None or not consolidado_path.exists():
        raise FileNotFoundError("No encontré supermercados_consolidado*.csv en src/output")

    cba_csv_path = find_cba_csv()

    print(f"[INFO] Leyendo consolidado: {consolidado_path}")
    print(f"[INFO] Leyendo CBA: {cba_csv_path}")

    df_consolidado = load_csv_robust(consolidado_path)
    df_cba = load_csv_robust(cba_csv_path)

    df_products = prepare_products(df_consolidado)
    df_candidates = build_candidates(df_products)
    df_best_market = build_best_by_market(df_candidates)
    df_summary = build_final_summary(df_best_market)
    df_total = build_total_cost_by_market(df_best_market, df_cba)

    return df_candidates, df_best_market, df_summary, df_total


def main():
    parser = argparse.ArgumentParser(description="Escenario Premium: mejor match + mejor marca + luego precio.")
    parser.add_argument("--input_csv", type=str, default=None, help="Ruta opcional al supermercados_consolidado*.csv")
    args = parser.parse_args()

    out_dir = OUTPUT_DIR / "cba_escenario_premium"
    out_dir.mkdir(parents=True, exist_ok=True)

    df_candidates, df_best_market, df_summary, df_total = run_pipeline(args.input_csv)

    export_csv(df_candidates, out_dir / "cba_premium_candidatos.csv")
    export_csv(df_best_market, out_dir / "cba_premium_mejor_por_supermercado.csv")
    export_csv(df_summary, out_dir / "cba_premium_resumen_final.csv")
    export_csv(df_total, out_dir / "cba_premium_total_por_supermercado.csv")

    print(f"[OK] candidatos: {len(df_candidates)}")
    print(f"[OK] mejor por supermercado: {len(df_best_market)}")
    print(f"[OK] resumen final: {len(df_summary)}")
    print(f"[OK] total supermercados: {len(df_total)}")
    print(f"[OK] Archivos generados en: {out_dir}")


if __name__ == "__main__":
    main()