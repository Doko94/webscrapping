from pathlib import Path
import logging
import sys

import pandas as pd

from config import MarketConfig
from pipeline import consolidate_market, export_outputs
from normalizers import normalize_common
from readers import read_csv_jumbo, read_csv_robust
from builders import (
    build_jumbo_categories,
    build_unimarc_categories,
    build_lider_categories,
)
from product_matcher import run_matching


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def get_project_paths() -> dict[str, Path]:
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    comparacion_dir = src_dir.parent
    supermercados_dir = comparacion_dir.parent
    output_dir = src_dir / "output" / "consolidado"

    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "script_dir": script_dir,
        "src_dir": src_dir,
        "comparacion_dir": comparacion_dir,
        "supermercados_dir": supermercados_dir,
        "output_dir": output_dir,
    }


def get_market_configs(supermercados_dir: Path) -> list[MarketConfig]:
    return [
        MarketConfig(
            name="jumbo",
            output_dir=supermercados_dir / "Jumbo" / "output",
            reader=read_csv_jumbo,
            category_builder=build_jumbo_categories,
        ),
        MarketConfig(
            name="unimarc",
            output_dir=supermercados_dir / "Unimarc" / "output",
            reader=read_csv_robust,
            category_builder=build_unimarc_categories,
        ),
        MarketConfig(
            name="lider",
            output_dir=supermercados_dir / "Lider" / "output",
            reader=read_csv_robust,
            category_builder=build_lider_categories,
        ),
    ]


def log_selected_files(market_name: str, selected_files: list[tuple[str, str]]) -> None:
    logger.info("Archivos seleccionados para %s:", market_name)
    if not selected_files:
        logger.info(" - Sin archivos seleccionados")
        return

    for categoria, archivo in selected_files:
        logger.info(" - %s: %s", categoria, archivo)


def build_categories_by_market(market_name: str, df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw.empty:
        return df_raw.copy()

    if market_name == "jumbo":
        return build_jumbo_categories(df_raw)

    if market_name == "unimarc":
        return build_unimarc_categories(df_raw)

    if market_name == "lider":
        return build_lider_categories(df_raw)

    raise ValueError(f"Supermercado no soportado: {market_name}")


def main() -> None:
    paths = get_project_paths()

    script_dir = paths["script_dir"]
    src_dir = paths["src_dir"]
    comparacion_dir = paths["comparacion_dir"]
    supermercados_dir = paths["supermercados_dir"]
    output_dir = paths["output_dir"]

    logger.info("Script dir: %s", script_dir)
    logger.info("Src dir: %s", src_dir)
    logger.info("Comparacion dir: %s", comparacion_dir)
    logger.info("Supermercados dir: %s", supermercados_dir)
    logger.info("Output dir: %s", output_dir)

    configs = get_market_configs(supermercados_dir)

    dfs_norm: list[pd.DataFrame] = []

    for config in configs:
        logger.info("Procesando supermercado: %s", config.name)

        df_raw, selected_files = consolidate_market(config)
        log_selected_files(config.name, selected_files)

        if df_raw is None or df_raw.empty:
            logger.warning("No hay datos consolidados para %s", config.name)
            continue

        logger.info("Construyendo categorías para %s...", config.name)
        df_built = build_categories_by_market(config.name, df_raw)

        if "supermercado" in df_built.columns:
            df_built = df_built.rename(columns={"supermercado": "supermarket"})

        logger.info("Normalizando columnas para %s...", config.name)
        df_norm = normalize_common(df_built, config.name)

        if df_norm is not None and not df_norm.empty:
            # evita dataframes totalmente vacíos o con columnas todas nulas
            if not df_norm.dropna(axis=1, how="all").empty:
                dfs_norm.append(df_norm)

        logger.info("Filas normalizadas %s: %s", config.name, len(df_norm))

    frames = [df for df in dfs_norm if df is not None and not df.empty]

    if not frames:
        logger.warning("No se generaron dataframes normalizados.")
        return

    df_supermercados = pd.concat(frames, ignore_index=True)
    logger.info("Total filas unificadas: %s", len(df_supermercados))

    logger.info("Exportando consolidado antes del matching...")
    export_outputs(
        df_supermercados,
        output_dir,
        "supermercados_consolidado",
    )

    logger.info("Iniciando matching de productos...")
    results = run_matching(df_supermercados)

    df_prepared = results["df_prepared"]
    df_matches = results["df_matches"]
    df_grouped = results["df_grouped"]
    df_group_detail = results["df_group_detail"]
    df_prices = results["df_prices"]

    logger.info("Filas prepared: %s", len(df_prepared))
    logger.info("Filas matches: %s", len(df_matches))
    logger.info("Filas grouped: %s", len(df_grouped))
    logger.info("Filas group detail: %s", len(df_group_detail))
    logger.info("Filas resumen precios: %s", len(df_prices))

    export_outputs(
        df_matches,
        output_dir,
        "productos_matches",
    )

    export_outputs(
        df_grouped,
        output_dir,
        "productos_grouped",
    )

    export_outputs(
        df_group_detail,
        output_dir,
        "productos_group_detail",
    )

    export_outputs(
        df_prices,
        output_dir,
        "productos_baratos",
    )

    print("\n===== HEAD CONSOLIDADO =====")
    print(df_supermercados.head())

    print("\n===== HEAD MATCHES =====")
    print(df_matches.head())

    print("\n===== HEAD PRODUCTOS BARATOS =====")
    print(df_prices.head())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Error en la ejecución principal: %s", e)
        sys.exit(1)