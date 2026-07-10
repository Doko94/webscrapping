from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
API_DIR = SRC_DIR / "api"
WEB_DATA_DIR = PROJECT_DIR / "web" / "public" / "data"

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


def main() -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    write_json("health.json", get_health())
    write_json("metadata.json", get_metadata())
    write_json("products_summary.json", product_summary())
    write_json("cba_summary.json", cba_summary())
    write_json("cart_summary.json", cart_summary())
    write_json("scenarios_economic.json", scenario_summary("economic"))
    write_json("scenarios_premium.json", scenario_summary("premium"))
    write_json("products_index.json", build_products_index())


if __name__ == "__main__":
    main()
