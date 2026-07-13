import csv
from pathlib import Path
from typing import List


def _resolve_output_dir(output_dir: Path) -> Path:
    output_path = Path(output_dir)
    if output_path.is_absolute():
        return output_path
    return Path.cwd() / output_path


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _split_group_and_name(label: str, fallback_group: str) -> tuple[str, str]:
    parts = [_clean(part) for part in str(label or "").split(">") if _clean(part)]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    if len(parts) == 1:
        return fallback_group, parts[0]
    return fallback_group, fallback_group


def load_cached_subcategories(output_dir: Path, category_name: str, category_landing: str | None = None) -> List[dict]:
    """Build subcategory inputs from previous Lider CSV outputs.

    Lider often blocks the home/menu discovery flow. Existing output files keep
    stable browse URLs, so they are a useful fallback for scheduled refreshes.
    """
    output_path = _resolve_output_dir(output_dir)
    if not output_path.exists():
        return []

    files = sorted(output_path.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    seen_urls = set()
    subcats = []

    for file_path in files:
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for row in reader:
                    url = _clean(
                        row.get("subcat_url")
                        or row.get("category_url")
                        or row.get("source_json_url")
                        or ""
                    )
                    if not url or "/browse/" not in url:
                        continue

                    normalized_url = url.split("#", 1)[0].rstrip("/")
                    normalized_key = normalized_url.split("?", 1)[0].lower()
                    if normalized_key in seen_urls:
                        continue

                    label = _clean(row.get("subcat_name") or row.get("category") or row.get("last_category") or "")
                    group, name = _split_group_and_name(label, category_name)

                    seen_urls.add(normalized_key)
                    subcats.append({
                        "group": group,
                        "name": name,
                        "url": normalized_url,
                    })
        except Exception as exc:
            print(f"[WARN] No se pudo leer cache de subcategorías {file_path}: {exc}")

        if subcats:
            break

    if not subcats and category_landing:
        subcats.append({
            "group": category_name,
            "name": category_name,
            "url": category_landing,
        })

    return subcats


def load_cached_product_rows(output_dir: Path) -> List[dict]:
    """Return rows from the newest non-empty CSV in a category output folder."""
    output_path = _resolve_output_dir(output_dir)
    if not output_path.exists():
        return []

    files = sorted(output_path.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)

    for file_path in files:
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))
        except Exception as exc:
            print(f"[WARN] No se pudo leer cache de productos {file_path}: {exc}")
            continue

        rows = [
            row for row in rows
            if _clean(row.get("sku")) or _clean(row.get("name")) or _clean(row.get("detail_url"))
        ]
        if rows:
            print(f"[WARN] Productos reutilizados desde cache: {file_path} ({len(rows)} filas)")
            return rows

    return []
