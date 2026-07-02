import re
import unicodedata
import numpy as np
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


# =========================================================
# TEXTO
# =========================================================
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).lower()
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# =========================================================
# NÚMEROS / PRECIO
# =========================================================
def safe_to_float(x):
    if pd.isna(x):
        return np.nan

    s = str(x).strip().lower()
    s = s.replace("$", "").replace("clp", "").replace(" ", "")

    # manejo simple de separadores
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


# =========================================================
# UNIDADES
# =========================================================
def normalize_unit_family(unit):
    if pd.isna(unit):
        return None

    u = str(unit).strip().lower()

    if u in {"kg", "g", "gr"}:
        return "mass"
    if u in {"l", "lt", "ml"}:
        return "volume"
    if u in {"un", "unidad", "unidades"}:
        return "unit"

    return None


def normalize_unit_value(value, unit):
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
    if u == "ml":
        return v
    if u in {"un", "unidad", "unidades"}:
        return v

    return np.nan


def size_bucket(size_std):
    if pd.isna(size_std):
        return None
    if size_std <= 0:
        return None

    if size_std <= 50:
        return "0_50"
    if size_std <= 100:
        return "51_100"
    if size_std <= 250:
        return "101_250"
    if size_std <= 500:
        return "251_500"
    if size_std <= 1000:
        return "501_1000"
    if size_std <= 2000:
        return "1001_2000"
    return "2000_plus"


# =========================================================
# FIRMAS DE BLOQUEO
# =========================================================
def short_name_signature(name: str) -> str:
    s = clean_text(name)
    toks = [t for t in s.split() if len(t) >= 3]
    return " ".join(toks[:3])


def brand_prefix(brand: str) -> str:
    s = clean_text(brand)
    return s[:4] if s else ""


# =========================================================
# SCORES
# =========================================================
def brand_score(a, b) -> float:
    a = clean_text(a)
    b = clean_text(b)

    if not a or not b:
        return 0.6
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9

    sa = set(a.split())
    sb = set(b.split())

    if not sa or not sb:
        return 0.6

    return len(sa & sb) / len(sa | sb)


def size_ratio_ok(a, b, tolerance=0.08) -> bool:
    if pd.isna(a) or pd.isna(b):
        return True
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) / max(a, b) <= tolerance


# =========================================================
# UNION FIND
# =========================================================
class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int):
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# =========================================================
# PREPARACIÓN
# =========================================================
def prepare_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    required = [
        "name",
        "brand",
        "price",
        "net_content",
        "unit",
        "category_std",
        "supermarket",
    ]
    for c in required:
        if c not in df.columns:
            df[c] = None

    df["name_clean"] = df["name"].apply(clean_text)
    df["brand_clean"] = df["brand"].apply(clean_text)
    df["price_num"] = df["price"].apply(safe_to_float)
    df["unit_family"] = df["unit"].apply(normalize_unit_family)
    df["size_std"] = df.apply(lambda x: normalize_unit_value(x["net_content"], x["unit"]), axis=1)

    df["category_std"] = df["category_std"].fillna("").astype(str)
    df["name_sig"] = df["name"].apply(short_name_signature)
    df["size_bucket"] = df["size_std"].apply(size_bucket)
    df["brand_prefix"] = df["brand"].apply(brand_prefix)

    df["match_text"] = (
        df["brand_clean"].fillna("") + " " +
        df["name_clean"].fillna("") + " " +
        df["category_std"].fillna("")
    ).str.strip()

    return df


# =========================================================
# MATCHING OPTIMIZADO
# =========================================================
def match_products(
    df: pd.DataFrame,
    text_threshold: float = 0.60,
    final_threshold: float = 0.75,
    max_block_size: int = 300,
) -> pd.DataFrame:
    """
    Optimización:
    - no compara todo contra todo globalmente
    - bloquea por:
      category_std + unit_family + size_bucket + name_sig
    - si el bloque sigue grande, divide por prefijo de marca
    """
    df = df.copy().reset_index(drop=True)
    matches = []

    block_cols = ["category_std", "unit_family", "size_bucket", "name_sig"]
    grouped = df.groupby(block_cols, dropna=False)

    total_blocks = 0
    total_candidate_rows = 0

    for _, block in grouped:
        total_blocks += 1
        block = block.copy()

        if len(block) < 2:
            continue

        if block["supermarket"].nunique() < 2:
            continue

        total_candidate_rows += len(block)

        if len(block) > max_block_size:
            subgroups = block.groupby("brand_prefix", dropna=False)
        else:
            subgroups = [(None, block)]

        for _, sub in subgroups:
            sub = sub.copy()

            if len(sub) < 2:
                continue

            if sub["supermarket"].nunique() < 2:
                continue

            texts = sub["match_text"].fillna("").tolist()

            try:
                vec = TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    max_df=0.95,
                )
                X = vec.fit_transform(texts)
                sims = linear_kernel(X, X)
            except ValueError:
                continue

            idxs = sub.index.tolist()

            for i in range(len(sub)):
                row_i = df.loc[idxs[i]]

                for j in range(i + 1, len(sub)):
                    row_j = df.loc[idxs[j]]

                    if row_i["supermarket"] == row_j["supermarket"]:
                        continue

                    text_sim = float(sims[i, j])
                    if text_sim < text_threshold:
                        continue

                    if not size_ratio_ok(row_i["size_std"], row_j["size_std"], tolerance=0.08):
                        continue

                    b_score = brand_score(row_i["brand"], row_j["brand"])
                    final_score = 0.75 * text_sim + 0.25 * b_score

                    if final_score < final_threshold:
                        continue

                    matches.append(
                        {
                            "idx_1": idxs[i],
                            "idx_2": idxs[j],
                            "supermarket_1": row_i["supermarket"],
                            "supermarket_2": row_j["supermarket"],
                            "name_1": row_i["name"],
                            "name_2": row_j["name"],
                            "brand_1": row_i["brand"],
                            "brand_2": row_j["brand"],
                            "price_1": row_i["price_num"],
                            "price_2": row_j["price_num"],
                            "size_std_1": row_i["size_std"],
                            "size_std_2": row_j["size_std"],
                            "unit_family": row_i["unit_family"],
                            "category_std": row_i["category_std"],
                            "text_similarity": round(text_sim, 4),
                            "brand_score": round(b_score, 4),
                            "final_score": round(final_score, 4),
                        }
                    )

    print(f"[INFO] Bloques evaluados: {total_blocks}")
    print(f"[INFO] Filas candidatas dentro de bloques: {total_candidate_rows}")
    print(f"[INFO] Matches encontrados: {len(matches)}")

    return pd.DataFrame(matches)


# =========================================================
# GRUPOS
# =========================================================
def build_groups(df: pd.DataFrame, matches_df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    uf = UnionFind(len(df))

    if not matches_df.empty:
        for _, row in matches_df.iterrows():
            uf.union(int(row["idx_1"]), int(row["idx_2"]))

    df["group_id"] = [uf.find(i) for i in range(len(df))]
    mapping = {g: i + 1 for i, g in enumerate(sorted(df["group_id"].unique()))}
    df["group_id"] = df["group_id"].map(mapping)

    return df


# =========================================================
# DETALLE DE GRUPOS
# =========================================================
def build_group_detail(df_grouped: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "group_id",
        "supermarket",
        "name",
        "brand",
        "category_std",
        "unit",
        "unit_family",
        "net_content",
        "size_std",
        "price",
        "price_num",
        "detail_url",
    ]
    cols = [c for c in cols if c in df_grouped.columns]
    return df_grouped[cols].copy()


# =========================================================
# RESUMEN DE PRECIOS
# =========================================================
def build_price_comparison(df_grouped: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for gid, grp in df_grouped.groupby("group_id"):
        grp = grp[grp["price_num"].notna()].copy()

        if grp.empty:
            continue

        if grp["supermarket"].nunique() < 2:
            continue

        cheapest = grp.loc[grp["price_num"].idxmin()]

        rows.append(
            {
                "group_id": gid,
                "producto_referencia": cheapest.get("name"),
                "marca_referencia": cheapest.get("brand"),
                "category_std": cheapest.get("category_std"),
                "unit_family": cheapest.get("unit_family"),
                "size_std": cheapest.get("size_std"),
                "supermercado_mas_barato": cheapest.get("supermarket"),
                "precio_mas_barato": cheapest.get("price_num"),
                "cantidad_opciones_comparadas": len(grp),
                "supermercados_presentes": ", ".join(sorted(grp["supermarket"].dropna().unique())),
            }
        )

    return pd.DataFrame(rows)


# =========================================================
# PIPELINE PRINCIPAL
# =========================================================
def run_matching(df: pd.DataFrame) -> dict:
    print("[INFO] Preparando productos...")
    df_prep = prepare_products(df)

    print("[INFO] Ejecutando matching optimizado...")
    df_matches = match_products(df_prep)

    print("[INFO] Construyendo grupos...")
    df_grouped = build_groups(df_prep, df_matches)

    print("[INFO] Construyendo detalle por grupo...")
    df_group_detail = build_group_detail(df_grouped)

    print("[INFO] Construyendo resumen de precios...")
    df_prices = build_price_comparison(df_grouped)

    return {
        "df_prepared": df_prep,
        "df_matches": df_matches,
        "df_grouped": df_grouped,
        "df_group_detail": df_group_detail,
        "df_prices": df_prices,
    }