from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# HELPERS
# ============================================================
def latest_csv_by_prefix(folder: Path, prefix: str) -> Optional[Path]:
    files = sorted(folder.glob(f"{prefix}*.csv"))
    return files[-1] if files else None


def load_csv_robust(path: Path) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        for sep in [",", ";"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc)
                if df.shape[1] > 1:
                    return df
            except Exception:
                pass
    return pd.read_csv(path, encoding="utf-8-sig")


def export_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        sep=";",
    )


def get_default_paths() -> tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    output_dir = src_dir / "output"
    cba_dir = output_dir / "cba"
    ahorro_dir = cba_dir / "ahorro"
    ahorro_dir.mkdir(parents=True, exist_ok=True)
    return cba_dir, ahorro_dir


# ============================================================
# CARGA
# ============================================================
def load_cba_inputs(
    resumen_csv: Optional[str] = None,
    optima_csv: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cba_dir, _ = get_default_paths()

    resumen_path = Path(resumen_csv) if resumen_csv else latest_csv_by_prefix(cba_dir, "cba_resumen_supermercado")
    optima_path = Path(optima_csv) if optima_csv else latest_csv_by_prefix(cba_dir, "cba_canasta_optima")

    if resumen_path is None or not resumen_path.exists():
        raise FileNotFoundError("No encontré 'cba_resumen_supermercado.csv'.")

    if optima_path is None or not optima_path.exists():
        raise FileNotFoundError("No encontré 'cba_canasta_optima.csv'.")

    df_resumen = load_csv_robust(resumen_path)
    df_optima = load_csv_robust(optima_path)

    return df_resumen, df_optima


# ============================================================
# MÉTRICAS
# ============================================================
def build_ranking_supermercados(df_resumen: pd.DataFrame) -> pd.DataFrame:
    df = df_resumen.copy()

    if df.empty:
        return df

    for c in ["supermarket", "costo_total_cba_detectada", "cba_items_cubiertos", "cobertura_pct"]:
        if c not in df.columns:
            df[c] = None

    df["costo_total_cba_detectada"] = pd.to_numeric(df["costo_total_cba_detectada"], errors="coerce")
    df["cobertura_pct"] = pd.to_numeric(df["cobertura_pct"], errors="coerce").round(2)
    df["cobertura_pct_fmt"] = df["cobertura_pct"].map(
        lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else None
    )
    df["cba_items_cubiertos"] = pd.to_numeric(df["cba_items_cubiertos"], errors="coerce")

    df = df[df["costo_total_cba_detectada"].notna()].copy()

    if df.empty:
        return df

    df = df.sort_values("costo_total_cba_detectada").reset_index(drop=True)
    costo_min = df["costo_total_cba_detectada"].min()

    df["ranking"] = range(1, len(df) + 1)
    df["ahorro_vs_mas_barato"] = df["costo_total_cba_detectada"] - costo_min
    df["ahorro_pct_vs_mas_barato"] = ((df["ahorro_vs_mas_barato"] / costo_min) * 100).round(2)
    df["ahorro_pct_vs_mas_barato_fmt"] = df["ahorro_pct_vs_mas_barato"].map(
        lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else None
    )

    return df


def build_ahorro_vs_optima(df_resumen: pd.DataFrame, df_optima: pd.DataFrame) -> pd.DataFrame:
    df = df_resumen.copy()

    if df.empty:
        return df

    df["costo_total_cba_detectada"] = pd.to_numeric(df["costo_total_cba_detectada"], errors="coerce")
    df = df[df["costo_total_cba_detectada"].notna()].copy()

    if df.empty:
        return df

    if "estimated_month_cost" not in df_optima.columns:
        df["costo_canasta_optima"] = None
        df["sobrecosto_vs_optima"] = None
        df["sobrecosto_pct_vs_optima"] = None
        return df

    costo_optima = pd.to_numeric(df_optima["estimated_month_cost"], errors="coerce").sum()

    df["costo_canasta_optima"] = costo_optima
    df["sobrecosto_vs_optima"] = df["costo_total_cba_detectada"] - costo_optima
    df["sobrecosto_pct_vs_optima"] = ((df["sobrecosto_vs_optima"] / costo_optima) * 100).round(2)
    df["sobrecosto_pct_vs_optima_fmt"] = df["sobrecosto_pct_vs_optima"].map(
        lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else None
    )

    return df.sort_values("costo_total_cba_detectada")


def build_resumen_ejecutivo(df_ranking: pd.DataFrame, df_ahorro: pd.DataFrame) -> pd.DataFrame:
    if df_ranking.empty:
        return pd.DataFrame()

    mejor = df_ranking.sort_values("costo_total_cba_detectada").iloc[0]
    peor = df_ranking.sort_values("costo_total_cba_detectada", ascending=False).iloc[0]

    rows = [
        {
            "indicador": "supermercado_mas_barato",
            "valor": mejor["supermarket"],
        },
        {
            "indicador": "costo_supermercado_mas_barato",
            "valor": round(float(mejor["costo_total_cba_detectada"]), 2),
        },
        {
            "indicador": "supermercado_mas_caro",
            "valor": peor["supermarket"],
        },
        {
            "indicador": "costo_supermercado_mas_caro",
            "valor": round(float(peor["costo_total_cba_detectada"]), 2),
        },
        {
            "indicador": "brecha_entre_mas_caro_y_mas_barato",
            "valor": round(float(peor["costo_total_cba_detectada"] - mejor["costo_total_cba_detectada"]), 2),
        },
    ]

    if not df_ahorro.empty and "costo_canasta_optima" in df_ahorro.columns:
        costo_optima = pd.to_numeric(df_ahorro["costo_canasta_optima"], errors="coerce").dropna()
        if not costo_optima.empty:
            rows.append(
                {
                    "indicador": "costo_canasta_optima_mezclada",
                    "valor": round(float(costo_optima.iloc[0]), 2),
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# PIPELINE
# ============================================================
def run_cba_ahorro_pipeline(
    resumen_csv: Optional[str] = None,
    optima_csv: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    df_resumen, df_optima = load_cba_inputs(resumen_csv, optima_csv)

    df_ranking = build_ranking_supermercados(df_resumen)
    df_ahorro = build_ahorro_vs_optima(df_resumen, df_optima)
    df_ejecutivo = build_resumen_ejecutivo(df_ranking, df_ahorro)

    return {
        "df_ranking_supermercados": df_ranking,
        "df_ahorro_supermercado": df_ahorro,
        "df_resumen_ejecutivo": df_ejecutivo,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Construye vistas de ahorro por supermercado usando la CBA detectada."
    )
    parser.add_argument("--resumen_csv", type=str, default=None, help="Ruta opcional a cba_resumen_supermercado.csv")
    parser.add_argument("--optima_csv", type=str, default=None, help="Ruta opcional a cba_canasta_optima.csv")
    args = parser.parse_args()

    _, ahorro_dir = get_default_paths()

    results = run_cba_ahorro_pipeline(
        resumen_csv=args.resumen_csv,
        optima_csv=args.optima_csv,
    )

    export_csv(results["df_ranking_supermercados"], ahorro_dir / "cba_ranking_supermercados.csv")
    export_csv(results["df_ahorro_supermercado"], ahorro_dir / "cba_ahorro_supermercado.csv")
    export_csv(results["df_resumen_ejecutivo"], ahorro_dir / "cba_resumen_ejecutivo.csv")

    print("[OK] Archivos generados en:", ahorro_dir)
    print("[OK] Ranking filas:", len(results["df_ranking_supermercados"]))
    print("[OK] Ahorro filas:", len(results["df_ahorro_supermercado"]))
    print("[OK] Resumen ejecutivo filas:", len(results["df_resumen_ejecutivo"]))


if __name__ == "__main__":
    main()