from __future__ import annotations

import argparse
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# HELPERS TEXTO
# ============================================================
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _fix_common_broken_sequences(s: str) -> str:
    replacements = {
        "Ã¡": "á",
        "Ã©": "é",
        "Ã­": "í",
        "Ã³": "ó",
        "Ãº": "ú",
        "Ã": "Á",
        "Ã‰": "É",
        "Ã": "Í",
        "Ã“": "Ó",
        "Ãš": "Ú",
        "Ã±": "ñ",
        "Ã‘": "Ñ",
        "Ã¼": "ü",
        "Ãœ": "Ü",
        "Â°": "°",
        "Â": "",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "â€¢": "•",
        "Ã§": "ç",
        "Ã‡": "Ç",
    }
    out = s
    for bad, good in replacements.items():
        out = out.replace(bad, good)
    return out


def fix_mojibake_text(x):
    if pd.isna(x):
        return x

    s = str(x).strip()
    if not s:
        return s

    original = s

    # intento 1
    try:
        s = s.encode("latin1").decode("utf-8")
    except Exception:
        s = original

    # intento 2 adicional si todavía quedan marcadores
    if any(m in s for m in ["Ã", "Â", "â€", "â€œ", "â€", "â€“", "â€™"]):
        try:
            s = s.encode("cp1252").decode("utf-8")
        except Exception:
            pass

    s = _fix_common_broken_sequences(s)
    s = s.replace("\x96", "-").replace("\x97", "-").replace("\xa0", " ")
    return s


def fix_mojibake_df(df: pd.DataFrame, columns: Optional[list[str]] = None) -> pd.DataFrame:
    df = df.copy()
    if columns is None:
        columns = df.select_dtypes(include=["object"]).columns.tolist()

    for c in columns:
        if c in df.columns:
            df[c] = df[c].apply(fix_mojibake_text)

    return df


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    s = fix_mojibake_text(x)
    s = str(s).lower()
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ============================================================
# HELPERS NÚMEROS / UNIDADES
# ============================================================
def safe_to_float(x) -> float:
    if pd.isna(x):
        return np.nan

    s = str(x).strip().lower()
    s = s.replace("$", "").replace("clp", "").replace(" ", "")

    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")

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


def normalize_unit_value(value, unit) -> float:
    if pd.isna(value) or pd.isna(unit):
        return np.nan

    try:
        v = float(str(value).replace(",", "."))
    except Exception:
        return np.nan

    u = str(unit).strip().lower()

    if u == "kg":
        return v * 1000
    if u in {"g", "gr"}:
        return v
    if u in {"l", "lt"}:
        return v * 1000
    if u in {"ml", "cc"}:
        return v
    if u in {"un", "unidad", "unidades"}:
        return v

    return np.nan


def month_quantity_std(daily_qty: float, unit: str) -> float:
    return float(daily_qty) * 30.0


def latest_csv_by_prefix(folder: Path, prefix: str) -> Optional[Path]:
    files = sorted(folder.glob(f"{prefix}*.csv"))
    return files[-1] if files else None


# ============================================================
# CONFIG CBA
# ============================================================
@dataclass
class CBAItem:
    cba_name: str
    unit: str
    daily_qty: float


CBA_ITEMS = [
    CBAItem("Arroz", "G", 22.2),
    CBAItem("Pan corriente sin envasar", "G", 151.2),
    CBAItem("Espiral", "G", 20.2),
    CBAItem("Galleta dulce", "G", 1.1),
    CBAItem("Galleta no dulce", "G", 0.5),
    CBAItem("Torta 15 o 20 personas", "G", 7.2),
    CBAItem("Prepizza familiar", "G", 0.8),
    CBAItem("Harina de trigo", "G", 10.2),
    CBAItem("Avena", "G", 5.1),
    CBAItem("Asiento", "G", 0.3),
    CBAItem("Carne molida", "G", 4.9),
    CBAItem("Chuleta de cerdo centro o vetada", "G", 3.9),
    CBAItem("Costillar de cerdo", "G", 1.8),
    CBAItem("Pulpa de cerdo", "G", 4.0),
    CBAItem("Carne de pavo molida", "G", 1.2),
    CBAItem("Pechuga de pollo", "G", 4.7),
    CBAItem("Pollo entero", "G", 20.4),
    CBAItem("Trutro de pollo", "G", 15.3),
    CBAItem("Pulpa de cordero fresco o refrigerado", "G", 0.2),
    CBAItem("Salchicha y vienesa de ave", "G", 2.3),
    CBAItem("Salchicha y vienesa tradicional", "G", 0.2),
    CBAItem("Longaniza", "G", 4.2),
    CBAItem("Jamón de cerdo", "G", 9.4),
    CBAItem("Pate", "G", 2.9),
    CBAItem("Merluza fresca o refrigerada", "G", 8.1),
    CBAItem("Choritos frescos o refrigerados en su concha", "G", 2.7),
    CBAItem("Jurel en conserva", "G", 18.8),
    CBAItem("Surtido en conserva", "G", 0.3),
    CBAItem("Leche líquida entera", "CC", 73.7),
    CBAItem("Leche en polvo entera instantánea", "G", 3.2),
    CBAItem("Yogurt", "G", 20.8),
    CBAItem("Queso Gouda", "G", 4.3),
    CBAItem("Quesillo y queso fresco con sal", "G", 0.9),
    CBAItem("Queso crema", "G", 0.3),
    CBAItem("Huevo de gallina", "G", 13.1),
    CBAItem("Mantequilla con sal", "G", 1.2),
    CBAItem("Margarina", "G", 3.6),
    CBAItem("Aceite vegetal combinado o puro", "CC", 15.7),
    CBAItem("Plátano", "G", 110.2),
    CBAItem("Manzana", "G", 51.1),
    CBAItem("Maní salado", "G", 0.4),
    CBAItem("Poroto", "G", 13.1),
    CBAItem("Lenteja", "G", 1.7),
    CBAItem("Lechuga", "G", 25.2),
    CBAItem("Zapallo", "G", 14.2),
    CBAItem("Limón", "G", 15.7),
    CBAItem("Palta", "G", 12.5),
    CBAItem("Tomate", "G", 44.6),
    CBAItem("Zanahoria", "G", 6.3),
    CBAItem("Cebolla nueva", "G", 17.5),
    CBAItem("Choclo congelado", "G", 5.7),
    CBAItem("Papa de guarda", "G", 121.5),
    CBAItem("Azúcar", "G", 28.8),
    CBAItem("Chocolate", "G", 0.9),
    CBAItem("Caramelo", "G", 1.9),
    CBAItem("Helado familiar un sabor", "CC", 9.3),
    CBAItem("Salsa de tomate", "G", 20.1),
    CBAItem("Sucedáneo de café", "G", 1.0),
    CBAItem("Te para preparar", "G", 1.8),
    CBAItem("Agua mineral", "CC", 9.4),
    CBAItem("Bebida gaseosa tradicional", "CC", 46.9),
    CBAItem("Bebida energizante", "CC", 0.1),
    CBAItem("Refresco isotónico", "CC", 0.3),
    CBAItem("Jugo líquido", "CC", 4.5),
    CBAItem("Néctar líquido", "CC", 0.1),
    CBAItem("Refresco en polvo", "G", 1.3),
    CBAItem("Completo", "G", 6.4),
    CBAItem("Papas fritas", "G", 0.8),
    CBAItem("Té corriente (según establecimiento) - para desayuno", "G", 1.3),
    CBAItem("Biscochos dulces y medialunas - para desayuno", "G", 0.1),
    CBAItem("Entrada (ensalada o sopa) - para almuerzo", "G", 0.0),
    CBAItem("Postre - para almuerzo", "G", 0.0),
    CBAItem("Promoción de comida rápida", "G", 0.7),
    CBAItem("Tostadas (palta o mantequilla o mermelada o mezcla de estas) - para desayuno", "G", 0.0),
    CBAItem("Aliado (jamón queso) o Barros Jarpa - para once", "G", 0.0),
    CBAItem("Pollo asado entero", "G", 2.0),
    CBAItem("Empanada de horno", "G", 1.5),
    CBAItem("Colación o menú del día o almuerzo ejecutivo", "G", 4.5),
    CBAItem("Plato de fondo - para almuerzo", "G", 0.8),
]

STOPWORDS = {
    "de", "o", "con", "sin", "para", "del", "la", "el", "los", "las",
    "segun", "entero", "fresco", "refrigerado", "corriente", "tradicional",
    "centro", "vetada", "combinado", "puro", "instantanea", "familiar",
    "un", "sabor", "nueva"
}

CUSTOM_PATTERNS = {
    "Pan corriente sin envasar": [r"\bpan\b"],
    "Espiral": [r"\bespiral\b", r"\bfideo\b", r"\bpasta\b"],
    "Asiento": [r"\basiento\b", r"\bvacuno\b"],
    "Carne molida": [r"\bcarne molida\b", r"\bmolida\b"],
    "Chuleta de cerdo centro o vetada": [r"\bchuleta\b", r"\bcerdo\b"],
    "Costillar de cerdo": [r"\bcostillar\b", r"\bcerdo\b"],
    "Pulpa de cerdo": [r"\bpulpa\b", r"\bcerdo\b"],
    "Carne de pavo molida": [r"\bpavo\b", r"\bmolida\b"],
    "Pechuga de pollo": [r"\bpechuga\b", r"\bpollo\b"],
    "Pollo entero": [r"\bpollo entero\b"],
    "Trutro de pollo": [r"\btrutro\b", r"\bpollo\b"],
    "Pulpa de cordero fresco o refrigerado": [r"\bcordero\b", r"\bpulpa\b"],
    "Salchicha y vienesa de ave": [r"\bviennesa\b", r"\bsalchicha\b", r"\bave\b", r"\bpollo\b", r"\bpavo\b"],
    "Salchicha y vienesa tradicional": [r"\bviennesa\b", r"\bsalchicha\b"],
    "Jamón de cerdo": [r"\bjamon\b"],
    "Pate": [r"\bpate\b", r"\bpat[eé]\b"],
    "Merluza fresca o refrigerada": [r"\bmerluza\b"],
    "Choritos frescos o refrigerados en su concha": [r"\bchorito\b", r"\bchoritos\b", r"\bmejillon\b"],
    "Jurel en conserva": [r"\bjurel\b"],
    "Surtido en conserva": [r"\bsurtido\b", r"\bmariscos\b"],
    "Leche líquida entera": [r"\bleche\b", r"\bentera\b"],
    "Leche en polvo entera instantánea": [r"\bleche en polvo\b"],
    "Quesillo y queso fresco con sal": [r"\bquesillo\b", r"\bqueso fresco\b"],
    "Huevo de gallina": [r"\bhuevo\b"],
    "Aceite vegetal combinado o puro": [r"\baceite\b"],
    "Maní salado": [r"\bmani\b"],
    "Cebolla nueva": [r"\bcebolla\b"],
    "Papa de guarda": [r"\bpapa\b"],
    "Helado familiar un sabor": [r"\bhelado\b"],
    "Sucedáneo de café": [r"\bcafe\b", r"\bsucedaneo\b"],
    "Te para preparar": [r"\bte\b"],
    "Bebida gaseosa tradicional": [r"\bbebida\b", r"\bgaseosa\b"],
    "Bebida energizante": [r"\benergizante\b"],
    "Refresco isotónico": [r"\bisotonica\b", r"\bisotonico\b"],
    "Jugo líquido": [r"\bjugo\b"],
    "Néctar líquido": [r"\bnectar\b"],
    "Refresco en polvo": [r"\brefresco en polvo\b"],
    "Completo": [r"\bcompleto\b"],
    "Papas fritas": [r"\bpapas fritas\b"],
    "Pollo asado entero": [r"\bpollo asado\b"],
    "Empanada de horno": [r"\bempanada\b"],
    "Colación o menú del día o almuerzo ejecutivo": [r"\bmenu\b", r"\balmuerzo\b", r"\bejecutivo\b", r"\bcolacion\b"],
}


# ============================================================
# PREPARACIÓN DE PRODUCTOS
# ============================================================
def prepare_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    required = [
        "supermarket",
        "name",
        "brand",
        "price",
        "net_content",
        "unit",
        "category_std",
        "detail_url",
    ]
    for c in required:
        if c not in df.columns:
            df[c] = None

    df["name"] = df["name"].apply(fix_mojibake_text)
    df["brand"] = df["brand"].apply(fix_mojibake_text)

    df["name_clean"] = df["name"].apply(clean_text)
    df["brand_clean"] = df["brand"].apply(clean_text)
    df["category_std"] = df["category_std"].fillna("").astype(str)
    df["price_num"] = df["price"].apply(safe_to_float)
    df["unit_family"] = df["unit"].apply(normalize_unit_family)
    df["size_std"] = df.apply(lambda x: normalize_unit_value(x["net_content"], x["unit"]), axis=1)

    df["price_per_std_unit"] = np.where(
        (df["price_num"].notna()) & (df["size_std"].notna()) & (df["size_std"] > 0),
        df["price_num"] / df["size_std"],
        np.nan
    )

    return df


# ============================================================
# REGLAS CBA
# ============================================================
def cba_item_to_patterns(cba_name: str) -> list[str]:
    if cba_name in CUSTOM_PATTERNS:
        return CUSTOM_PATTERNS[cba_name]

    cleaned = clean_text(cba_name)
    words = [w for w in cleaned.split() if len(w) >= 4 and w not in STOPWORDS]

    if not words:
        return [re.escape(cleaned)]

    return [rf"\b{re.escape(w)}\b" for w in words[:4]]


def build_candidate_mask(df: pd.DataFrame, item: CBAItem) -> pd.Series:
    patterns = cba_item_to_patterns(item.cba_name)
    mask = pd.Series(False, index=df.index)

    for p in patterns:
        mask = mask | df["name_clean"].str.contains(p, regex=True, na=False)
        mask = mask | df["brand_clean"].str.contains(p, regex=True, na=False)

    item_family = normalize_unit_family(item.unit)
    if item_family:
        mask = mask & (
            (df["unit_family"] == item_family) |
            (df["unit_family"].isna())
        )

    return mask


def estimate_item_cost(row: pd.Series, item: CBAItem) -> float:
    required_std_qty = month_quantity_std(item.daily_qty, item.unit)

    if pd.notna(row.get("price_per_std_unit")) and required_std_qty > 0:
        return float(row["price_per_std_unit"]) * required_std_qty

    if pd.notna(row.get("price_num")):
        return float(row["price_num"])

    return math.nan


# ============================================================
# MATCHING CBA
# ============================================================
def match_cba_items(df_products: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for item in CBA_ITEMS:
        mask = build_candidate_mask(df_products, item)
        candidates = df_products[mask].copy()

        if candidates.empty:
            rows.append({
                "cba_name": item.cba_name,
                "cba_unit": item.unit,
                "cba_daily_qty": item.daily_qty,
                "cba_month_qty_std": month_quantity_std(item.daily_qty, item.unit),
                "supermarket": None,
                "name": None,
                "brand": None,
                "price_num": np.nan,
                "size_std": np.nan,
                "unit_family": normalize_unit_family(item.unit),
                "estimated_month_cost": np.nan,
                "coverage_status": "missing",
                "detail_url": None,
            })
            continue

        candidates["cba_name"] = item.cba_name
        candidates["cba_unit"] = item.unit
        candidates["cba_daily_qty"] = item.daily_qty
        candidates["cba_month_qty_std"] = month_quantity_std(item.daily_qty, item.unit)
        candidates["estimated_month_cost"] = candidates.apply(lambda r: estimate_item_cost(r, item), axis=1)
        candidates["coverage_status"] = np.where(
            candidates["estimated_month_cost"].notna(),
            "matched",
            "price_missing"
        )

        keep = [
            "cba_name",
            "cba_unit",
            "cba_daily_qty",
            "cba_month_qty_std",
            "supermarket",
            "name",
            "brand",
            "price_num",
            "size_std",
            "unit_family",
            "estimated_month_cost",
            "coverage_status",
            "detail_url",
        ]
        rows.extend(candidates[keep].to_dict("records"))

    return pd.DataFrame(rows)


def build_cba_resumen_supermercado(df_cba_matches: pd.DataFrame) -> pd.DataFrame:
    if df_cba_matches.empty:
        return pd.DataFrame()

    matched = df_cba_matches[df_cba_matches["coverage_status"] == "matched"].copy()
    if matched.empty:
        return pd.DataFrame()

    best_market_item = (
        matched.sort_values(["supermarket", "cba_name", "estimated_month_cost"])
        .groupby(["supermarket", "cba_name"], as_index=False)
        .first()
    )

    resumen = (
        best_market_item.groupby("supermarket", as_index=False)
        .agg(
            cba_items_cubiertos=("cba_name", "nunique"),
            costo_total_cba_detectada=("estimated_month_cost", "sum"),
        )
    )

    resumen["cba_items_totales"] = len(CBA_ITEMS)
    resumen["cobertura_pct"] = (
        resumen["cba_items_cubiertos"] / resumen["cba_items_totales"] * 100
    ).round(2)

    # columna amigable para Excel
    resumen["cobertura_pct_fmt"] = resumen["cobertura_pct"].map(
        lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else None
    )

    return resumen.sort_values("costo_total_cba_detectada")


def build_cba_canasta_optima(df_cba_matches: pd.DataFrame) -> pd.DataFrame:
    matched = df_cba_matches[df_cba_matches["coverage_status"] == "matched"].copy()

    if matched.empty:
        return pd.DataFrame()

    optimal = (
        matched.sort_values(["cba_name", "estimated_month_cost"])
        .groupby("cba_name", as_index=False)
        .first()
    )

    return optimal.sort_values("estimated_month_cost")


def build_cba_cobertura(df_cba_matches: pd.DataFrame) -> pd.DataFrame:
    if df_cba_matches.empty:
        return pd.DataFrame()

    by_item = (
        df_cba_matches.groupby("cba_name", as_index=False)
        .agg(
            candidatos_detectados=("name", lambda s: s.notna().sum()),
            supermercados_detectados=("supermarket", lambda s: s.dropna().nunique()),
            tiene_match=("coverage_status", lambda s: int((s == "matched").any())),
        )
    )

    by_item["estado"] = np.where(by_item["tiene_match"] == 1, "cubierto", "faltante")
    return by_item.sort_values(
        ["estado", "supermercados_detectados", "candidatos_detectados"],
        ascending=[True, False, False]
    )


# ============================================================
# IO
# ============================================================
def get_default_paths() -> tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    output_dir = src_dir / "output"
    cba_output_dir = output_dir / "cba"
    cba_output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, cba_output_dir


def load_input_dataframe(input_csv: Optional[str]) -> pd.DataFrame:
    output_dir, _ = get_default_paths()

    if input_csv:
        path = Path(input_csv)
    else:
        path = latest_csv_by_prefix(output_dir, "supermercados_consolidado")

    if path is None or not path.exists():
        raise FileNotFoundError(
            "No encontré un CSV de 'supermercados_consolidado' para construir la CBA."
        )

    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        for sep in [",", ";"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc)
                if df.shape[1] > 1:
                    df = fix_mojibake_df(df)
                    print(f"[INFO] Archivo CBA leído: {path} | sep={sep} | enc={enc}")
                    return df
            except Exception:
                pass

    df = pd.read_csv(path, encoding="utf-8-sig")
    df = fix_mojibake_df(df)
    return df


def export_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df_export = fix_mojibake_df(df)

    # export limpio en UTF-8 con BOM para Excel
    df_export.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        sep=";",
    )


# ============================================================
# MAIN PIPELINE CBA
# ============================================================
def run_cba_builder(input_csv: Optional[str] = None) -> dict[str, pd.DataFrame]:
    df = load_input_dataframe(input_csv)
    df_products = prepare_products(df)

    df_cba_matches = match_cba_items(df_products)
    df_cba_resumen = build_cba_resumen_supermercado(df_cba_matches)
    df_cba_optima = build_cba_canasta_optima(df_cba_matches)
    df_cba_cobertura = build_cba_cobertura(df_cba_matches)

    df_cba_matches = fix_mojibake_df(df_cba_matches)
    df_cba_optima = fix_mojibake_df(df_cba_optima)
    df_cba_resumen = fix_mojibake_df(df_cba_resumen)
    df_cba_cobertura = fix_mojibake_df(df_cba_cobertura)

    return {
        "df_input": df,
        "df_products": df_products,
        "df_cba_matches": df_cba_matches,
        "df_cba_resumen_supermercado": df_cba_resumen,
        "df_cba_canasta_optima": df_cba_optima,
        "df_cba_cobertura": df_cba_cobertura,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Construye una aproximación de la CBA oficial chilena usando el consolidado de supermercados."
    )
    parser.add_argument(
        "--input_csv",
        type=str,
        default=None,
        help="Ruta opcional al CSV 'supermercados_consolidado'."
    )
    args = parser.parse_args()

    _, cba_output_dir = get_default_paths()

    results = run_cba_builder(args.input_csv)

    export_csv(results["df_cba_matches"], cba_output_dir / "cba_item_matches.csv")
    export_csv(results["df_cba_resumen_supermercado"], cba_output_dir / "cba_resumen_supermercado.csv")
    export_csv(results["df_cba_canasta_optima"], cba_output_dir / "cba_canasta_optima.csv")
    export_csv(results["df_cba_cobertura"], cba_output_dir / "cba_cobertura.csv")

    print("[OK] Archivos CBA generados en:", cba_output_dir)
    print("[OK] Cobertura items:", len(results["df_cba_cobertura"]))
    print("[OK] Matches generados:", len(results["df_cba_matches"]))


if __name__ == "__main__":
    main()