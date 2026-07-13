import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin


def to_int_clp(value) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = re.sub(r"[^\d]", "", str(value))
    return int(text) if text else None


def first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if value == {} or value == []:
            continue
        return value
    return None


def walk_nodes(obj: Any):
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from walk_nodes(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_nodes(item)


def deep_find_first(obj: Any, keys: List[str]) -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and value not in (None, "", [], {}):
                return value
        for value in obj.values():
            found = deep_find_first(value, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = deep_find_first(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def deep_find_all_lists(obj: Any) -> List[List[dict]]:
    lists = []
    for node in walk_nodes(obj):
        if isinstance(node, list) and node and all(isinstance(item, dict) for item in node[: min(10, len(node))]):
            lists.append(node)
    return lists


def score_product_candidate(items: List[dict]) -> int:
    score = 0
    for product in items[:100]:
        sku = deep_find_first(product, ["sku", "skuId", "itemId", "id", "productId", "productID", "ean"])
        name = deep_find_first(product, ["name", "productName", "displayName", "productTitle", "title"])
        price = deep_find_first(product, ["price", "bestPrice", "sellingPrice", "finalPrice", "Price", "currentPrice", "sellingPriceValue"])
        if sku:
            score += 2
        if name:
            score += 3
        if price is not None:
            score += 1
    return score


def pick_best_products_list(data: Any) -> Optional[List[dict]]:
    lists = [items for items in deep_find_all_lists(data) if len(items) >= 2]
    best = None
    best_score = -1
    for items in lists:
        score = score_product_candidate(items) * 1000 + min(len(items), 500)
        if score > best_score:
            best = items
            best_score = score
    return best


def parse_detail_url(product: dict, base_url: str) -> str:
    candidate = deep_find_first(product, ["detailUrl", "detailURL", "url", "link", "href", "slug", "productUrl", "canonicalUrl"])
    if isinstance(candidate, str) and candidate.strip():
        value = candidate.strip()
        if value.startswith("http"):
            return value
        if value.startswith("/"):
            return urljoin(base_url, value)
        return urljoin(base_url, f"/{value}")
    return ""


def parse_image_url(product: dict) -> str:
    candidate = deep_find_first(product, ["imageUrl", "image", "images", "src", "image_url", "thumbnail"])
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if isinstance(candidate, list) and candidate:
        first = candidate[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first_non_empty(first.get("url"), first.get("src"), first.get("imageUrl"), "") or ""
    if isinstance(candidate, dict):
        return first_non_empty(candidate.get("url"), candidate.get("src"), candidate.get("imageUrl"), "") or ""
    return ""


def parse_prices(product: dict) -> Tuple[Optional[int], Optional[int]]:
    price = deep_find_first(product, ["price", "bestPrice", "sellingPrice", "finalPrice", "Price", "currentPrice", "sellingPriceValue"])
    list_price = deep_find_first(product, ["listPrice", "priceWithoutDiscount", "referencePrice", "ListPrice", "originalPrice", "wasPrice"])
    return to_int_clp(price), to_int_clp(list_price)


def parse_product(product: dict, base_url: str) -> Optional[dict]:
    sku = deep_find_first(product, ["sku", "skuId", "itemId", "id", "productId", "productID", "ean"])
    name = deep_find_first(product, ["name", "productName", "displayName", "productTitle", "title"])
    if sku is None or name is None:
        return None

    price, list_price = parse_prices(product)
    brand = deep_find_first(product, ["brand", "brandName", "Brand", "brandText"])

    return {
        "sku": str(sku).strip(),
        "name": str(name).strip()[:250],
        "brand": str(brand).strip()[:120] if brand else "",
        "price": price,
        "list_price": list_price,
        "in_offer": price is not None and list_price is not None and price < list_price,
        "detail_url": parse_detail_url(product, base_url),
        "image_url": parse_image_url(product),
    }


def extract_products_from_json(data: Any, base_url: str) -> List[dict]:
    products = pick_best_products_list(data)
    if not products:
        return []

    dedup: Dict[str, dict] = {}
    for product in products:
        parsed = parse_product(product, base_url)
        if parsed and parsed["sku"]:
            dedup[parsed["sku"]] = parsed
    return list(dedup.values())


def looks_like_product_api_url(url: str) -> bool:
    lowered = url.lower()
    hints = ["search", "products", "product", "catalog", "plp", "item", "collection", "query", "browse"]
    return any(hint in lowered for hint in hints)


async def capture_product_response_rows(page, goto_url: str, base_url: str, settle_ms: int = 4500) -> Tuple[List[dict], str]:
    captures = []

    async def on_response(response):
        try:
            if response.request.resource_type not in ("xhr", "fetch"):
                return
            if not looks_like_product_api_url(response.url):
                return

            content_type = (response.headers.get("content-type") or "").lower()
            if "json" not in content_type and "javascript" not in content_type and "text/plain" not in content_type:
                return

            try:
                data = await response.json()
            except Exception:
                return

            products = extract_products_from_json(data, base_url)
            if products:
                captures.append({"response_url": response.url, "products": products})
        except Exception:
            return

    page.on("response", on_response)
    try:
        await page.goto(goto_url, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1200)
        for _ in range(3):
            try:
                await page.mouse.wheel(0, 1400)
            except Exception:
                pass
            await asyncio.sleep(0.8)
        await page.wait_for_timeout(settle_ms)
    finally:
        page.remove_listener("response", on_response)

    if not captures:
        return [], ""

    best = max(captures, key=lambda capture: len(capture["products"]))
    return best["products"], best["response_url"]
