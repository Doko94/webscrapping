import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import pandas as pd

TS_RE = re.compile(r"(?P<date>20\d{6})_(?P<time>\d{6})")

STANDARD_COLS = [
    "sku","name","brand","price","list_price","discount_price",
    "in_offer","net_content","unit",
    "price_per_unit","price_per_unit_list",
    "saving_text","image_url","detail_url",
    "category","subcategory","last_category",
    "category_url","page_num","extracted_at",
    "supermarket","archivo","ruta_archivo",
    "timestamp_archivo","mtime_archivo","category_std"
]

@dataclass
class MarketConfig:
    name: str
    output_dir: Path
    reader: Callable[[Path], pd.DataFrame]
    category_builder: Callable[[pd.DataFrame], pd.DataFrame]