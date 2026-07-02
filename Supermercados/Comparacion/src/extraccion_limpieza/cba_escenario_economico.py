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

    # Chile: 6.990 = 6990
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
    """
    Extrae el número desde textos como:
    '$2.222 x lt'
    '$6.230 x kg'
    '$1.000 x kg'
    """
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
# ESPECIFICACIÓN ESCENARIO 1 ECONÓMICO
# =========================================================
@dataclass
class EconSpec:
    cba_name: str
    formato_objetivo: str
    include_any: list[str] = field(default_factory=list)
    include_all: list[str] = field(default_factory=list)
    exclude_any: list[str] = field(default_factory=list)
    category_any: list[str] = field(default_factory=list)
    subcategory_any: list[str] = field(default_factory=list)
    last_category_any: list[str] = field(default_factory=list)

    # NUEVO: reglas más estrictas por nombre
    include_name_words_any: list[str] = field(default_factory=list)
    include_name_words_all: list[str] = field(default_factory=list)
    exclude_name_any: list[str] = field(default_factory=list)

    unit_family: Optional[str] = None
    target_size_std: Optional[float] = None
    min_size_std: Optional[float] = None
    max_size_std: Optional[float] = None
    top_n_per_market: int = 5


ECON_SPECS: list[EconSpec] = [
    EconSpec(
        "Arroz", "1 kg clasico",
        include_any=["arroz"],
        include_name_words_any=["arroz"],
        exclude_any=["basmati", "arborio", "risotto", "jazmin", "jasmine", "integral", "salvaje", "inflado", "cereal", "galleta", "barra", "bebida", "leche de arroz", "sazonador", "condimento", "sopa", "pollo con arroz", "arroz preparado", "arroz y legumbres", "lenteja", "poroto"],
        exclude_name_any=["lenteja", "poroto", "cereal", "galleta", "barra", "sazonador", "condimento"],
        subcategory_any=["arroz"],
        last_category_any=["arroz"],
        unit_family="mass", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    EconSpec(
        "Pan corriente sin envasar", "500 g a 1 kg pan corriente",
        include_any=["pan"],
        include_name_words_any=["pan"],
        exclude_any=["molde", "hamburguesa", "hot dog", "ciabatta", "italiano", "croissant", "galleta", "levadura", "camaron"],
        exclude_name_any=["molde", "hamburguesa", "hot", "dog", "ciabatta", "italiano", "croissant", "camaron"],
        subcategory_any=["pan", "panaderia"],
        last_category_any=["pan"],
        unit_family="mass", min_size_std=400, max_size_std=1200
    ),
    EconSpec(
        "Espiral", "400 g a 1 kg pasta espiral",
        include_any=["espiral", "fideo espiral", "pasta espiral"],
        include_name_words_any=["espiral"],
        exclude_any=["integral", "arroz"],
        exclude_name_any=["arroz"],
        unit_family="mass", min_size_std=350, max_size_std=1200
    ),
    EconSpec(
        "Harina de trigo", "1 kg",
        include_any=["harina de trigo", "harina"],
        include_name_words_any=["harina"],
        exclude_any=["avena", "almendra", "coco", "premezcla", "integral"],
        exclude_name_any=["avena", "almendra", "coco", "premezcla", "integral"],
        unit_family="mass", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    EconSpec(
        "Avena", "500 g tradicional o instantanea",
        include_any=["avena tradicional", "avena instantanea", "hojuelas de avena", "avena"],
        include_name_words_any=["avena"],
        exclude_any=["yogurt", "yoghurt", "bebida", "leche", "granola", "barra", "galleta", "batido", "proteina", "protein"],
        exclude_name_any=["yogurt", "yoghurt", "bebida", "leche", "granola", "barra", "galleta", "batido", "proteina", "protein"],
        unit_family="mass", target_size_std=500, min_size_std=300, max_size_std=1000
    ),
    EconSpec(
        "Azúcar", "1 kg",
        include_any=["azucar"],
        include_name_words_any=["azucar"],
        exclude_any=["sin azucar", "endulzante", "stevia", "sucralosa", "cereal", "chocolate", "galleta"],
        exclude_name_any=["endulzante", "stevia", "sucralosa", "cereal", "chocolate", "galleta"],
        unit_family="mass", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    EconSpec(
        "Leche líquida entera", "1 litro",
        include_all=["leche", "entera"],
        include_name_words_all=["leche", "entera"],
        exclude_any=["sin lactosa", "descremada", "semidescremada", "almendra", "soya", "polvo", "alfajor", "galleta"],
        exclude_name_any=["sin", "lactosa", "descremada", "semidescremada", "almendra", "soya", "polvo", "alfajor", "galleta"],
        subcategory_any=["leche", "leches"],
        last_category_any=["leche"],
        unit_family="volume", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    EconSpec(
        "Yogurt", "100 g a 1 kg yogurt tradicional",
        include_any=["yogurt", "yoghurt"],
        include_name_words_any=["yogurt", "yoghurt"],
        exclude_any=["proteina", "protein", "avena", "miel"],
        exclude_name_any=["proteina", "protein", "avena", "miel"],
        subcategory_any=["yogurt"],
        last_category_any=["yogurt", "batido"],
        unit_family="mass", min_size_std=80, max_size_std=1200
    ),
    EconSpec(
        "Queso gouda", "150 g a 500 g",
        include_all=["queso", "gouda"],
        include_name_words_all=["queso", "gouda"],
        exclude_any=["crema", "snack"],
        exclude_name_any=["crema", "snack"],
        unit_family="mass", min_size_std=100, max_size_std=600
    ),
    EconSpec(
        "Queso crema", "100 g a 300 g",
        include_all=["queso", "crema"],
        include_name_words_all=["queso", "crema"],
        exclude_any=["gouda", "snack"],
        exclude_name_any=["gouda", "snack"],
        unit_family="mass", min_size_std=80, max_size_std=400
    ),
    EconSpec(
        "Huevo de gallina", "6 a 12 unidades",
        include_any=["huevo"],
        include_name_words_any=["huevo"],
        exclude_any=["sorpresa", "chocolate", "codorniz"],
        exclude_name_any=["sorpresa", "chocolate", "codorniz"],
        unit_family="unit", min_size_std=6, max_size_std=12
    ),
    EconSpec(
        "Mantequilla con sal", "100 g a 250 g",
        include_any=["mantequilla"],
        include_name_words_any=["mantequilla"],
        exclude_any=["sin sal", "galleta", "margarina"],
        exclude_name_any=["galleta", "margarina"],
        unit_family="mass", min_size_std=80, max_size_std=300
    ),
    EconSpec(
        "Margarina", "200 g a 500 g",
        include_any=["margarina"],
        include_name_words_any=["margarina"],
        exclude_any=["galleta"],
        exclude_name_any=["galleta"],
        unit_family="mass", min_size_std=150, max_size_std=600
    ),
    EconSpec(
        "Aceite vegetal combinado o puro", "1 litro",
        include_any=["aceite"],
        include_name_words_any=["aceite"],
        exclude_any=["oliva", "palta", "spray", "coco", "vinagre", "jugo", "limon", "sucedaneo"],
        exclude_name_any=["vinagre", "jugo", "limon", "sucedaneo"],
        category_any=["despensa", "aceites", "aceites y aderezos"],
        subcategory_any=["aceites"],
        last_category_any=["aceites", "aceite"],
        unit_family="volume", target_size_std=1000, min_size_std=900, max_size_std=1100
    ),
    EconSpec(
        "Plátano", "1 kg granel",
        include_any=["platano"],
        include_name_words_any=["platano"],
        exclude_any=["yogurt", "compota", "snack", "chips", "ensure", "nectar"],
        exclude_name_any=["yogurt", "batido", "ensure", "nectar"],
        category_any=["frutas y verduras"],
        subcategory_any=["frutas"],
        last_category_any=["frutas", "platano"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Manzana", "1 kg granel",
        include_any=["manzana"],
        include_name_words_any=["manzana"],
        exclude_any=["compota", "jugo", "galleta", "pure", "postre", "repollo"],
        exclude_name_any=["compota", "pure", "postre", "repollo"],
        category_any=["frutas y verduras"],
        subcategory_any=["frutas"],
        last_category_any=["frutas", "manzana"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Lechuga", "1 unidad o equivalente",
        include_any=["lechuga"],
        include_name_words_any=["lechuga"],
        exclude_any=["ensalada lista", "mix", "cuatro estaciones"],
        exclude_name_any=["ensalada", "mix", "cuatro", "estaciones"],
        category_any=["frutas y verduras"],
        unit_family="mass", min_size_std=200, max_size_std=1000
    ),
    EconSpec(
        "Limón", "1 kg granel",
        include_any=["limon"],
        include_name_words_any=["limon"],
        exclude_any=["jugo", "galleta", "limpieza", "sabor", "cloro"],
        exclude_name_any=["jugo", "cloro", "limpieza"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=1000, min_size_std=300, max_size_std=2000
    ),
    EconSpec(
        "Palta", "700 g a 1 kg",
        include_any=["palta"],
        include_name_words_any=["palta"],
        exclude_any=["aderezo", "salsa"],
        exclude_name_any=["aderezo", "salsa"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=1500
    ),
    EconSpec(
        "Tomate", "500 g a 1 kg",
        include_any=["tomate"],
        include_name_words_any=["tomate"],
        exclude_any=["salsa", "sofrito", "crema", "pasta"],
        exclude_name_any=["salsa", "sofrito", "crema", "pasta"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=500, min_size_std=300, max_size_std=1500
    ),
    EconSpec(
        "Zanahoria", "1 kg",
        include_any=["zanahoria"],
        include_name_words_any=["zanahoria"],
        exclude_any=["compota", "snack", "galleta"],
        exclude_name_any=["compota", "snack", "galleta"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Cebolla nueva", "1 kg",
        include_any=["cebolla"],
        include_name_words_any=["cebolla"],
        exclude_any=["aritos", "crispy", "polvo"],
        exclude_name_any=["aritos", "crispy", "polvo"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Choclo congelado", "500 g",
        include_any=["choclo congelado", "choclo"],
        include_name_words_any=["choclo"],
        exclude_any=["palomitas", "snack"],
        exclude_name_any=["palomitas", "snack"],
        unit_family="mass", target_size_std=500, min_size_std=300, max_size_std=1000
    ),
    EconSpec(
        "Papa de guarda", "1 kg",
        include_any=["papa"],
        include_name_words_any=["papa"],
        exclude_any=["papas fritas", "chips", "pure", "hamburguesa de papa", "snack"],
        exclude_name_any=["chips", "pure", "hamburguesa", "snack", "fritas"],
        category_any=["frutas y verduras"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=3000
    ),
    EconSpec(
        "Pechuga de pollo", "1 kg",
        include_any=["pollo"],
        include_all=["pechuga"],
        include_name_words_all=["pechuga"],
        exclude_any=["trutro", "ala", "entero", "apanado", "nugget", "hamburguesa", "molida"],
        exclude_name_any=["trutro", "ala", "entero", "apanado", "nugget", "molida"],
        category_any=["carnes", "carnes y pescados"],
        subcategory_any=["pollo"],
        last_category_any=["pechuga"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Pollo entero", "1.5 kg a 3 kg",
        include_any=["pollo"],
        include_name_words_any=["pollo"],
        exclude_any=["pechuga", "trutro", "apanado", "nugget", "molida", "hamburguesa", "consome", "sopa", "alimento perro", "alimento de perro", "pet"],
        exclude_name_any=["pechuga", "trutro", "apanado", "nugget", "molida", "hamburguesa", "consome", "sopa", "perro", "pet"],
        category_any=["carnes", "carnes y pescados"],
        unit_family="mass", target_size_std=2000, min_size_std=1000, max_size_std=3500
    ),
    EconSpec(
        "Trutro de pollo", "1 kg",
        include_all=["trutro", "pollo"],
        include_name_words_all=["trutro"],
        exclude_any=["apanado", "panitas", "consome", "sopa", "pechuga"],
        exclude_name_any=["pechuga", "apanado"],
        category_any=["carnes", "carnes y pescados"],
        subcategory_any=["pollo"],
        last_category_any=["trutro"],
        unit_family="mass", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Jamón de cerdo", "100 g a 500 g",
        include_all=["jamon"],
        include_name_words_any=["jamon"],
        exclude_any=["pavo", "galleta", "mortadela", "chorizo", "salame"],
        exclude_name_any=["mortadela", "chorizo", "salame"],
        category_any=["fiambres", "quesos y fiambres"],
        unit_family="mass", min_size_std=80, max_size_std=600
    ),
    EconSpec(
        "Paté", "100 g a 200 g",
        include_any=["pate"],
        include_name_words_any=["pate"],
        exclude_any=["jamon", "mortadela", "chorizo"],
        exclude_name_any=["jamon", "mortadela", "chorizo"],
        category_any=["fiambres", "pate"],
        unit_family="mass", min_size_std=80, max_size_std=300
    ),
    EconSpec(
        "Agua mineral", "1 litro a 3 litros",
        include_all=["agua"],
        include_name_words_any=["agua"],
        exclude_any=["saborizada", "bebida", "jugo"],
        exclude_name_any=["saborizada", "bebida", "jugo"],
        unit_family="volume", min_size_std=1000, max_size_std=3000
    ),
    EconSpec(
        "Bebida gaseosa tradicional", "1.5 L a 3 L",
        include_any=["bebida"],
        include_name_words_any=["bebida"],
        exclude_any=["zero", "sin azucar", "light", "energetica", "isotonica", "agua", "jugo"],
        exclude_name_any=["zero", "light", "energetica", "isotonica", "agua", "jugo"],
        unit_family="volume", min_size_std=1500, max_size_std=3000
    ),
    EconSpec(
        "Jugo líquido", "1 litro",
        include_all=["jugo"],
        include_name_words_any=["jugo"],
        exclude_any=["polvo", "sabor yogurt"],
        exclude_name_any=["polvo", "yogurt"],
        unit_family="volume", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Néctar líquido", "1 litro",
        include_all=["nectar"],
        include_name_words_any=["nectar"],
        exclude_any=["polvo"],
        exclude_name_any=["polvo"],
        unit_family="volume", target_size_std=1000, min_size_std=500, max_size_std=2000
    ),
    EconSpec(
        "Chocolate", "barra economica",
        include_any=["chocolate"],
        include_name_words_any=["chocolate"],
        exclude_any=["cereal", "galleta", "helado", "leche chocolatada", "brownie", "flan", "mousse", "postre"],
        exclude_name_any=["flan", "mousse", "postre"],
        category_any=["chocolates", "dulces", "snacks"],
        unit_family="mass", min_size_std=30, max_size_std=200
    ),
    EconSpec(
        "Papas fritas", "snack 100 g a 350 g",
        include_all=["papas fritas"],
        include_name_words_any=["papas", "fritas"],
        exclude_any=["papa cruda", "mix de vegetales"],
        exclude_name_any=["cruda", "mix", "vegetales"],
        unit_family="mass", min_size_std=50, max_size_std=400
    ),
    EconSpec(
        "Salsa de tomate", "200 g a 500 g",
        include_all=["salsa", "tomate"],
        include_name_words_all=["salsa", "tomate"],
        exclude_any=["tomate fresco", "sofrito"],
        exclude_name_any=["fresco", "sofrito"],
        unit_family="mass", min_size_std=150, max_size_std=600
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

    # Lo que manda: list_price
    df["list_price_num"] = df["list_price"].apply(safe_to_float)
    df["fallback_price_num"] = df["price"].apply(safe_to_float)
    df["price_num"] = df["list_price_num"].fillna(df["fallback_price_num"])

    # Solo info extra
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

    # filtrar precios inválidos
    df = df[df["price_num"].notna()].copy()
    df = df[(df["price_num"] > 100) & (df["price_num"] < 100000)].copy()

    return df


# =========================================================
# MATCHER
# =========================================================
def row_matches_spec(row: pd.Series, spec: EconSpec) -> bool:
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


def compute_score(row: pd.Series, spec: EconSpec) -> float:
    score = 0.0
    text = row.get("all_text", "")
    name = row.get("name_clean", "")
    category = row.get("category_std_clean", "")
    subcat = row.get("subcategory_clean", "")
    lastcat = row.get("last_category_clean", "")
    size_std = row.get("size_std", np.nan)

    if spec.include_any and contains_any(text, spec.include_any):
        score += 2

    if spec.include_all and contains_all(text, spec.include_all):
        score += 2

    if spec.include_name_words_any and contains_any_word(name, spec.include_name_words_any):
        score += 3

    if spec.include_name_words_all and contains_all_words(name, spec.include_name_words_all):
        score += 4

    if spec.category_any and contains_any(category, spec.category_any):
        score += 1

    if spec.subcategory_any and contains_any(subcat, spec.subcategory_any):
        score += 1.5

    if spec.last_category_any and contains_any(lastcat, spec.last_category_any):
        score += 1.5

    if pd.notna(size_std) and spec.target_size_std is not None:
        diff = abs(size_std - spec.target_size_std)
        score += max(0, 3 - (diff / max(spec.target_size_std, 1)) * 3)

    return score


# Ajuste fino adicional para ciertos productos problemáticos
def apply_special_filters(tmp: pd.DataFrame, spec: EconSpec) -> pd.DataFrame:
    name = tmp["name_clean"]

    if spec.cba_name == "Aceite vegetal combinado o puro":
        tmp = tmp[name.str.contains(r"\baceite\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(vinagre|jugo|limon|sucedaneo)\b", na=False, regex=True)]

    elif spec.cba_name == "Plátano":
        tmp = tmp[name.str.contains(r"\bplatano\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(yogurt|yoghurt|ensure|nectar|batido)\b", na=False, regex=True)]

    elif spec.cba_name == "Manzana":
        tmp = tmp[name.str.contains(r"\bmanzana\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(pure|postre|repollo|compota)\b", na=False, regex=True)]

    elif spec.cba_name == "Chocolate":
        tmp = tmp[name.str.contains(r"\bchocolate\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(flan|mousse|postre)\b", na=False, regex=True)]

    elif spec.cba_name == "Jamón de cerdo":
        tmp = tmp[name.str.contains(r"\bjamon\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(mortadela|chorizo|salame)\b", na=False, regex=True)]

    elif spec.cba_name == "Paté":
        tmp = tmp[name.str.contains(r"\bpate\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\b(jamon|mortadela|chorizo)\b", na=False, regex=True)]

    elif spec.cba_name == "Pechuga de pollo":
        tmp = tmp[name.str.contains(r"\bpechuga\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\btrutro\b", na=False, regex=True)]

    elif spec.cba_name == "Trutro de pollo":
        tmp = tmp[name.str.contains(r"\btrutro\b", na=False, regex=True)]
        tmp = tmp[~name.str.contains(r"\bpechuga\b", na=False, regex=True)]

    return tmp


def build_candidates(df_products: pd.DataFrame) -> pd.DataFrame:
    frames = []

    for spec in ECON_SPECS:
        tmp = df_products[df_products.apply(lambda r: row_matches_spec(r, spec), axis=1)].copy()

        if tmp.empty:
            continue

        tmp = apply_special_filters(tmp, spec)

        if tmp.empty:
            continue

        tmp["cba_name"] = spec.cba_name
        tmp["formato_objetivo"] = spec.formato_objetivo
        tmp["match_score"] = tmp.apply(lambda r: compute_score(r, spec), axis=1)

        # manda list_price + mejor score
        tmp = tmp.sort_values(
            ["supermarket", "match_score", "price_num"],
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
        "match_score", "detail_url"
    ]
    out = ensure_columns(out, keep)
    return out[keep].copy()


def build_best_by_market(df_candidates: pd.DataFrame) -> pd.DataFrame:
    if df_candidates.empty:
        return pd.DataFrame()

    out = (
        df_candidates.sort_values(
            ["cba_name", "supermarket", "match_score", "price_num"],
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
            ["cba_name", "price_num", "match_score"],
            ascending=[True, True, False],
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
            "match_score": "best_match_score",
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
        "best_match_score", "best_detail_url",
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
            total_cba_economica=("price_num", "sum"),
            productos_encontrados=("cba_name", "nunique")
        )
        .sort_values("total_cba_economica", ascending=True)
        .reset_index(drop=True)
    )

    total["ranking_economico"] = total.index + 1
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
    consolidado_path = Path(input_csv) if input_csv else latest_csv_by_prefix(OUTPUT_DIR, "supermercados_consolidado")
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
    parser = argparse.ArgumentParser(
        description="Escenario 1 Económico: list_price manda; oferta y precio por kg/lt/un solo como info extra."
    )
    parser.add_argument("--input_csv", type=str, default=None, help="Ruta opcional al supermercados_consolidado*.csv")
    args = parser.parse_args()

    out_dir = OUTPUT_DIR / "cba_escenario1_economico"
    out_dir.mkdir(parents=True, exist_ok=True)

    df_candidates, df_best_market, df_summary, df_total = run_pipeline(args.input_csv)

    export_csv(df_candidates, out_dir / "cba_econ_candidatos.csv")
    export_csv(df_best_market, out_dir / "cba_econ_mejor_por_supermercado.csv")
    export_csv(df_summary, out_dir / "cba_econ_resumen_final.csv")
    export_csv(df_total, out_dir / "cba_econ_total_por_supermercado.csv")

    print(f"[OK] candidatos: {len(df_candidates)}")
    print(f"[OK] mejor por supermercado: {len(df_best_market)}")
    print(f"[OK] resumen final: {len(df_summary)}")
    print(f"[OK] total supermercados: {len(df_total)}")
    print(f"[OK] Archivos generados en: {out_dir}")


if __name__ == "__main__":
    main()