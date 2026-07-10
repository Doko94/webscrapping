from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
API_DIR = SRC_DIR / "api"
WEB_DATA_DIR = PROJECT_DIR / "web" / "public" / "data"
CBA_ITEM_MATCHES_PATH = SRC_DIR / "output" / "cba" / "cba_item_matches.csv"

sys.path.insert(0, str(API_DIR))

from data_loader import clean_records, load_dataset  # noqa: E402
from services import (  # noqa: E402
    cart_summary,
    cba_summary,
    get_health,
    get_metadata,
    product_summary,
    scenario_summary,
)


PRODUCT_INDEX_COLUMNS = [
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


def write_json(file_name: str, data: Any) -> None:
    path = WEB_DATA_DIR / file_name
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK {path.relative_to(PROJECT_DIR)}")


def build_products_index() -> list[dict[str, Any]]:
    df = load_dataset("consolidado")
    if df.empty:
        return []

    existing_cols = [col for col in PRODUCT_INDEX_COLUMNS if col in df.columns]
    if not existing_cols:
        return []

    return clean_records(df[existing_cols])


def build_cba_items_by_supermarket() -> list[dict[str, Any]]:
    if not CBA_ITEM_MATCHES_PATH.exists():
        return []

    df = pd.read_csv(CBA_ITEM_MATCHES_PATH, sep=";", encoding="utf-8-sig", low_memory=False)
    if df.empty or "supermarket" not in df.columns or "cba_name" not in df.columns:
        return []

    rows: list[dict[str, Any]] = []
    for supermarket, group in df.groupby("supermarket", dropna=True):
        items = sorted(group["cba_name"].dropna().astype(str).unique().tolist())
        rows.append(
            {
                "supermarket": supermarket,
                "covered_items": items,
                "covered_items_count": len(items),
            }
        )

    return sorted(rows, key=lambda row: row["supermarket"])


def build_cba_cost_drivers(limit: int = 12) -> list[dict[str, Any]]:
    if not CBA_ITEM_MATCHES_PATH.exists():
        return []

    df = pd.read_csv(CBA_ITEM_MATCHES_PATH, sep=";", encoding="utf-8-sig", low_memory=False)
    required_cols = {"supermarket", "cba_name", "name", "estimated_month_cost"}
    if df.empty or not required_cols.issubset(df.columns):
        return []

    df = df.copy()
    df["estimated_month_cost"] = pd.to_numeric(df["estimated_month_cost"], errors="coerce")
    df = df.dropna(subset=["estimated_month_cost"])
    df = df.sort_values("estimated_month_cost")

    best_by_market_item = df.groupby(["supermarket", "cba_name"], as_index=False).first()
    drivers = best_by_market_item.sort_values("estimated_month_cost", ascending=False).head(limit)

    cols = [
        "supermarket",
        "cba_name",
        "name",
        "brand",
        "price_num",
        "estimated_month_cost",
        "detail_url",
    ]
    existing_cols = [col for col in cols if col in drivers.columns]
    return clean_records(drivers[existing_cols])


def main() -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cba_data = cba_summary()
    cba_data["items_by_supermarket"] = build_cba_items_by_supermarket()
    cba_data["cost_drivers"] = build_cba_cost_drivers()

    write_json("health.json", get_health())
    write_json("metadata.json", get_metadata())
    write_json("products_summary.json", product_summary())
    write_json("cba_summary.json", cba_data)
    write_json("cart_summary.json", cart_summary())
    write_json("scenarios_economic.json", scenario_summary("economic"))
    write_json("scenarios_premium.json", scenario_summary("premium"))
    write_json("products_index.json", build_products_index())


if __name__ == "__main__":
    main()
