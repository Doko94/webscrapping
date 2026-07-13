from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from .data_loader import (
        CSV_CANDIDATES,
        clean_records,
        dataset_file_info,
        load_dataset,
        normalize_text,
        searchable_columns,
        to_numeric,
    )
except ImportError:
    from data_loader import (
        CSV_CANDIDATES,
        clean_records,
        dataset_file_info,
        load_dataset,
        normalize_text,
        searchable_columns,
        to_numeric,
    )


def get_health() -> dict[str, Any]:
    consolidado = dataset_file_info("consolidado")
    return {
        "status": "ok",
        "has_consolidado": consolidado["exists"],
        "consolidado_rows": consolidado["rows"],
    }


def get_metadata() -> dict[str, Any]:
    files = {key: dataset_file_info(key) for key in CSV_CANDIDATES}
    consolidado = load_dataset("consolidado")

    supermarkets: list[str] = []
    categories: list[str] = []
    if not consolidado.empty:
        if "supermarket" in consolidado.columns:
            supermarkets = sorted(consolidado["supermarket"].dropna().astype(str).unique().tolist())
        if "category_std" in consolidado.columns:
            categories = sorted(consolidado["category_std"].dropna().astype(str).unique().tolist())

    return {
        "files": files,
        "supermarkets": supermarkets,
        "categories": categories,
    }


def product_summary() -> dict[str, Any]:
    df = load_dataset("consolidado")
    if df.empty:
        return {
            "total_products": 0,
            "supermarkets": [],
            "categories": [],
            "offers": 0,
        }

    summary: dict[str, Any] = {
        "total_products": int(len(df)),
        "supermarkets": [],
        "categories": [],
        "offers": 0,
    }

    if "supermarket" in df.columns:
        by_market = (
            df.groupby("supermarket", dropna=False)
            .size()
            .reset_index(name="products")
            .sort_values("products", ascending=False)
        )
        summary["supermarkets"] = clean_records(by_market)

    if "category_std" in df.columns:
        by_category = (
            df.groupby("category_std", dropna=False)
            .size()
            .reset_index(name="products")
            .sort_values("products", ascending=False)
            .head(12)
        )
        summary["categories"] = clean_records(by_category)

    if "in_offer" in df.columns:
        offer_text = df["in_offer"].astype(str).str.lower()
        summary["offers"] = int(offer_text.isin(["true", "1", "si", "sí"]).sum())

    return summary


def search_tokens(value: str) -> list[str]:
    stop_words = {"de", "del", "la", "las", "el", "los", "y"}
    return [
        token
        for token in normalize_text(value).split()
        if len(token) > 1 and token not in stop_words
    ]


def search_products(
    query: str,
    supermarket: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    df = load_dataset("consolidado")
    if df.empty:
        return []

    filtered = df.copy()

    if supermarket and "supermarket" in filtered.columns:
        filtered = filtered[filtered["supermarket"].astype(str).str.lower() == supermarket.lower()]

    cols = searchable_columns(filtered)
    if not cols:
        return []

    normalized_query = normalize_text(query)
    query_tokens = search_tokens(query)
    haystack = filtered[cols].fillna("").astype(str).agg(" ".join, axis=1).map(normalize_text)

    if query_tokens:
        mask = haystack.map(lambda value: all(token in value for token in query_tokens))
    else:
        mask = haystack.str.contains(normalized_query, na=False, regex=False)

    filtered = filtered[mask].copy()
    if filtered.empty:
        return []

    if "price" in filtered.columns:
        filtered["price_num"] = to_numeric(filtered["price"])
        filtered.loc[filtered["price_num"] <= 0, "price_num"] = pd.NA
        filtered = filtered.sort_values(["price_num", "name"], na_position="last")

    visible_cols = [
        "sku",
        "name",
        "brand",
        "supermarket",
        "price",
        "list_price",
        "discount_price",
        "in_offer",
        "net_content",
        "unit",
        "price_per_unit",
        "category_std",
        "category",
        "subcategory",
        "last_category",
        "detail_url",
        "image_url",
        "extracted_at",
    ]
    existing_cols = [col for col in visible_cols if col in filtered.columns]
    return clean_records(filtered[existing_cols], limit=limit)


def compare_product(query: str, limit_per_market: int = 5) -> dict[str, Any]:
    df = load_dataset("consolidado")
    if df.empty or not query.strip() or "supermarket" not in df.columns:
        return {"query": query, "markets": []}

    matches = search_products(query=query, limit=200)
    if not matches:
        return {"query": query, "markets": []}

    match_df = pd.DataFrame(matches)
    if "price" in match_df.columns:
        match_df["price_num"] = to_numeric(match_df["price"])
        match_df = match_df.sort_values(["supermarket", "price_num"], na_position="last")

    markets = []
    for market, group in match_df.groupby("supermarket", dropna=False):
        markets.append(
            {
                "supermarket": market,
                "items": clean_records(group.drop(columns=["price_num"], errors="ignore"), limit=limit_per_market),
            }
        )

    return {"query": query, "markets": markets}


def cba_summary() -> dict[str, Any]:
    resumen = load_dataset("cba_resumen")
    optima = load_dataset("cba_optima")
    cobertura = load_dataset("cba_cobertura")
    ahorro = load_dataset("cba_ahorro")
    ranking = load_dataset("cba_ranking")

    return {
        "resumen_supermercado": clean_records(resumen),
        "canasta_optima": clean_records(optima, limit=30),
        "cobertura": clean_records(cobertura, limit=100),
        "ahorro_supermercado": clean_records(ahorro),
        "ranking_supermercados": clean_records(ranking),
    }


def scenario_summary(kind: str) -> dict[str, Any]:
    if kind == "economic":
        total = load_dataset("economic_total")
        summary = load_dataset("economic_summary")
    elif kind == "premium":
        total = load_dataset("premium_total")
        summary = load_dataset("premium_summary")
    else:
        raise ValueError("Escenario no soportado")

    return {
        "total_por_supermercado": clean_records(total),
        "resumen_final": clean_records(summary, limit=100),
    }


def cart_summary() -> dict[str, Any]:
    return {
        "resumen": clean_records(load_dataset("cart_summary")),
        "total": clean_records(load_dataset("cart_total")),
    }
