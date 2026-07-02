import asyncio
import csv
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext, APIResponse

OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/carnes_pescados"))

# =========================
# CONFIG
# =========================
BASE = "https://www.jumbo.cl"
MAX_PAGES = 60
HEADLESS = True
DEBUG = True

DEBUG_DUMP_BFF = True
DUMP_DIR = "debug_bff"

OUT_PREFIX = "jumbo_carnes_y_pescados"

# -------------------------
# Subcategorías (menú)
# Nota: añadí "Vacuno" (Mostrar todo) porque ahí aparecen items como "Carne Molida y Bistecs"
# -------------------------
SUBCATS = [
    # Vacuno
    {"name": "Carnes Premium", "url": f"{BASE}/carnes-y-pescados/vacuno/carnes-premium"},
    {"name": "Carnes Americana", "url": f"{BASE}/carnes-y-pescados/vacuno/carnes-americana"},
    {"name": "Carnes para Parrilla", "url": f"{BASE}/carnes-y-pescados/vacuno/carnes-para-parrilla"},
    {"name": "Carnes para Horno", "url": f"{BASE}/carnes-y-pescados/vacuno/carnes-para-horno"},
    {"name": "Vacuno (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/vacuno"},

    # Pollo
    {"name": "Trutros y Pechugas a Granel", "url": f"{BASE}/carnes-y-pescados/pollo/trutros-y-pechugas-a-granel"},
    {"name": "Filetes y Pechuga de Pollo", "url": f"{BASE}/carnes-y-pescados/pollo/filetes-y-pechugas-de-pollo"},
    {"name": "Alitas y Trutros de Pollo", "url": f"{BASE}/carnes-y-pescados/pollo/alitas-y-trutros-de-pollo"},
    {"name": "Pollo Entero", "url": f"{BASE}/carnes-y-pescados/pollo/pollo-entero"},
    {"name": "Pollo (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/pollo"},

    # Cerdo y Cordero
    {"name": "Costillar y Costillitas", "url": f"{BASE}/carnes-y-pescados/cerdo-y-cordero/costillar-y-costillitas"},
    {"name": "Chuletas y Filetes", "url": f"{BASE}/carnes-y-pescados/cerdo-y-cordero/chuletas-y-filetes"},
    {"name": "Pulpa y Lomo de Cerdo", "url": f"{BASE}/carnes-y-pescados/cerdo-y-cordero/pulpa-y-lomo-de-cerdo"},
    {"name": "Malaya y Otros Cortes", "url": f"{BASE}/carnes-y-pescados/cerdo-y-cordero/malaya-y-otros-cortes"},
    {"name": "Cerdo y Cordero (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/cerdo-y-cordero"},

    # Pavo
    {"name": "Filetes y Pechugas de Pavo", "url": f"{BASE}/carnes-y-pescados/pavo/filetes-y-pechugas-de-pavo"},
    {"name": "Pavo Entero", "url": f"{BASE}/carnes-y-pescados/pavo/pavo-entero"},
    {"name": "Trutros y Bistec de Pavo", "url": f"{BASE}/carnes-y-pescados/pavo/trutros-y-bistec-de-pavo"},
    {"name": "Carne Molida y Albondigas de Pavo", "url": f"{BASE}/carnes-y-pescados/pavo/carne-molida-y-albondigas-de-pavo"},
    {"name": "Pavo (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/pavo"},

    # Pescados
    {"name": "Pescados Frescos", "url": f"{BASE}/carnes-y-pescados/pescados/pescados-frescos"},
    {"name": "Pescados Congelados", "url": f"{BASE}/carnes-y-pescados/pescados/pescados-congelados"},
    {"name": "Pescados Apanados", "url": f"{BASE}/carnes-y-pescados/pescados/pescados-apanados"},
    {"name": "Pescados Frescos Envasados", "url": f"{BASE}/carnes-y-pescados/pescados/pescados-frescos-envasados"},
    {"name": "Pescados (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/pescados"},

    # Camarones
    {"name": "Camarones Crudos", "url": f"{BASE}/carnes-y-pescados/camarones/camarones-crudos"},
    {"name": "Camarones Cocidos", "url": f"{BASE}/carnes-y-pescados/camarones/camarones-cocidos"},
    {"name": "Camarones Apanados", "url": f"{BASE}/carnes-y-pescados/camarones/camarones-apanados"},
    {"name": "Camarones (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/camarones"},

    # Mariscos
    {"name": "Mariscos Frescos", "url": f"{BASE}/carnes-y-pescados/mariscos/mariscos-frescos"},
    {"name": "Mariscos Congelados", "url": f"{BASE}/carnes-y-pescados/mariscos/mariscos-congelados"},
    {"name": "Mariscos en Conserva", "url": f"{BASE}/carnes-y-pescados/mariscos/mariscos-en-conserva"},
    {"name": "Mariscos (Mostrar todo)", "url": f"{BASE}/carnes-y-pescados/mariscos"},
]


# =========================
# Utils
# =========================
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def safe_slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:120]

def to_int_clp(x) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return int(x)
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else None

def first_non_empty(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if v == {} or v == []:
            continue
        return v
    return None


# =========================
# Blocking (OneTrust/ads)
# =========================
BLOCK_PATTERNS = [
    "cookielaw.org",
    "onetrust.com",
    "googletagservices.com",
    "googleadservices.com",
    "doubleclick.net",
    "pagead2.googlesyndication.com",
    "maze.co",
    "creativecdn.com",
    "aria.microsoft.com",
    "omnichannelengagementhub.com",
]

def should_block(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in BLOCK_PATTERNS)

async def install_blocking(context: BrowserContext):
    async def route_handler(route):
        if should_block(route.request.url):
            return await route.abort()
        return await route.continue_()
    await context.route("**/*", route_handler)


# =========================
# JSON walking + deep find
# =========================
def walk_nodes(obj: Any):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from walk_nodes(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from walk_nodes(it)

def deep_find_first(obj: Any, keys: List[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and v is not None and v != "":
                return v
        for v in obj.values():
            got = deep_find_first(v, keys)
            if got is not None and got != "":
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = deep_find_first(it, keys)
            if got is not None and got != "":
                return got
    return None

def deep_find_all_lists(obj: Any) -> List[List[dict]]:
    out = []
    for node in walk_nodes(obj):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node[: min(10, len(node))]):
            out.append(node)
    return out

def score_product_list(lst: List[dict]) -> int:
    score = 0
    for p in lst[:50]:
        sku = deep_find_first(p, ["sku", "skuId", "itemId", "id", "productId"])
        name = deep_find_first(p, ["name", "productName", "nameComplete", "productTitle"])
        if sku and name:
            score += 1
    return score

def pick_best_products_list(data: Any) -> Optional[List[dict]]:
    lists = deep_find_all_lists(data)
    if not lists:
        return None
    lists = [lst for lst in lists if len(lst) >= 3]
    if not lists:
        return None

    best = None
    best_score = -1
    for lst in lists:
        s = score_product_list(lst)
        s2 = s * 1000 + min(len(lst), 500)
        if s2 > best_score:
            best_score = s2
            best = lst

    if best is None:
        return None
    if score_product_list(best) < 2:
        return None
    return best


# =========================
# Parse product (robusto)
# =========================
def parse_detail_url(p: dict) -> str:
    cand = deep_find_first(p, ["detailUrl", "detailURL", "url", "link", "href", "slug"])
    if isinstance(cand, str) and cand.strip():
        c = cand.strip()
        if c.startswith("http"):
            return c
        if c.startswith("/"):
            return urljoin(BASE, c)
        return urljoin(BASE, f"/{c}/p")
    return ""

def parse_image_url(p: dict) -> str:
    cand = deep_find_first(p, ["imageUrl", "image_url", "image", "images", "src"])
    if isinstance(cand, str) and cand.strip():
        return cand.strip()
    if isinstance(cand, list) and cand:
        x = cand[0]
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return first_non_empty(x.get("url"), x.get("src"), "") or ""
    if isinstance(cand, dict):
        return first_non_empty(cand.get("url"), cand.get("src"), "") or ""
    return ""

def parse_prices(p: dict) -> Tuple[Optional[int], Optional[int]]:
    price = deep_find_first(p, ["price", "bestPrice", "sellingPrice", "finalPrice", "Price", "SellingPrice"])
    list_price = deep_find_first(p, ["listPrice", "priceWithoutDiscount", "referencePrice", "ListPrice", "PriceWithoutDiscount"])

    price_i = to_int_clp(price)
    list_i = to_int_clp(list_price)

    if price_i is None and list_i is None:
        try:
            items = p.get("items") or deep_find_first(p, ["items"])
            if isinstance(items, list) and items:
                sellers = items[0].get("sellers") if isinstance(items[0], dict) else None
                if isinstance(sellers, list) and sellers:
                    co = sellers[0].get("commertialOffer") or sellers[0].get("commercialOffer") or {}
                    price_i = to_int_clp(first_non_empty(co.get("Price"), co.get("price"), co.get("SellingPrice"), co.get("sellingPrice")))
                    list_i = to_int_clp(first_non_empty(co.get("ListPrice"), co.get("listPrice"), co.get("PriceWithoutDiscount")))
        except Exception:
            pass

    return price_i, list_i

def parse_product(p: dict) -> Optional[dict]:
    sku = deep_find_first(p, ["sku", "skuId", "itemId", "id", "productId"])
    name = deep_find_first(p, ["name", "productName", "nameComplete", "productTitle"])
    if sku is None or name is None:
        return None

    sku = str(sku).strip()
    name = str(name).strip()

    brand = deep_find_first(p, ["brand", "brandName", "Brand", "brandText"])
    brand = str(brand).strip() if brand else ""

    price, list_price = parse_prices(p)

    in_offer = None
    if price is not None and list_price is not None:
        in_offer = price < list_price
    else:
        flag = deep_find_first(p, ["inOffer", "hasDiscount", "isOffer"])
        if isinstance(flag, bool):
            in_offer = flag

    detail_url = parse_detail_url(p)
    image_url = parse_image_url(p)

    return {
        "sku": sku,
        "name": name,
        "brand": brand,
        "price": price,
        "list_price": list_price,
        "in_offer": in_offer,
        "detail_url": detail_url,
        "image_url": image_url,
    }


# =========================
# Extract products from BFF JSON
# =========================
def extract_products_bff(data: Any) -> List[dict]:
    prod_list = pick_best_products_list(data)
    if not prod_list:
        return []
    out: Dict[str, dict] = {}
    for p in prod_list:
        parsed = parse_product(p)
        if not parsed:
            continue
        out[parsed["sku"]] = parsed
    return list(out.values())


# =========================
# BFF request cloning (pagination without UI)
# =========================
def _try_json_load(s: Optional[str]) -> Optional[Any]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def _set_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    qs = parse_qs(parts.query)
    qs[key] = [value]
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))

def _mutate_pagination(payload: Any, page_index_1_based: int) -> Any:
    """
    Intenta ajustar page/from/offset en payload JSON.
    - page puede ser 1-based o 0-based dependiendo del backend; probamos 1-based aquí.
    """
    if not isinstance(payload, dict):
        return payload

    # claves típicas
    if "page" in payload and isinstance(payload["page"], int):
        payload["page"] = page_index_1_based
    if "currentPage" in payload and isinstance(payload["currentPage"], int):
        payload["currentPage"] = page_index_1_based
    # offset patterns
    if "from" in payload and isinstance(payload["from"], int) and "size" in payload and isinstance(payload["size"], int):
        payload["from"] = (page_index_1_based - 1) * payload["size"]
    if "offset" in payload and isinstance(payload["offset"], int) and "limit" in payload and isinstance(payload["limit"], int):
        payload["offset"] = (page_index_1_based - 1) * payload["limit"]

    return payload


async def fetch_plp_page_via_api(context: BrowserContext, req_info: dict, page_num: int) -> Tuple[str, Any]:
    """
    Repite el request del BFF PLP con page modificada.
    req_info contiene: method, url, headers, post_data (string or None)
    """
    url = req_info["url"]
    method = req_info["method"].upper()
    headers = dict(req_info.get("headers") or {})
    post_data = req_info.get("post_data")

    # Limpieza headers que a veces rompen en replay
    headers.pop("content-length", None)
    headers.pop("host", None)

    data = None
    if method == "GET":
        # intenta ajustar query param típico
        # si el backend usa ?page= o algo similar
        # probamos page primero
        url2 = _set_query_param(url, "page", str(page_num))
        resp: APIResponse = await context.request.fetch(url2, method="GET", headers=headers, timeout=60000)
        try:
            data = await resp.json()
        except Exception:
            data = None
        return url2, data

    # POST
    payload = _try_json_load(post_data)
    if payload is not None:
        payload2 = json.loads(json.dumps(payload))  # deep copy
        payload2 = _mutate_pagination(payload2, page_num)
        post_data2 = json.dumps(payload2, ensure_ascii=False)
    else:
        # si no es JSON, no podemos mutar con seguridad
        post_data2 = post_data or ""

    resp = await context.request.fetch(
        url,
        method="POST",
        headers=headers,
        data=post_data2,
        timeout=60000
    )
    try:
        data = await resp.json()
    except Exception:
        data = None
    return url, data


# =========================
# Captura PLP (sin listeners acumulados)
# =========================
async def capture_first_plp_from_page(page: Page, goto_url: str, subcat_name: str) -> Tuple[str, Any, dict]:
    """
    Navega y espera el primer response del BFF PLP.
    Retorna: (source_json_url, json_data, req_info)
    """
    # Espera un response real del PLP (no networkidle)
    def is_plp_response(resp) -> bool:
        try:
            u = resp.url.lower()
            return "bff.jumbo.cl/catalog/plp" in u and resp.request.resource_type in ("xhr", "fetch")
        except Exception:
            return False

    req_info: dict = {}

    for attempt in range(1, 4):
        try:
            if DEBUG:
                print(f"  🌐 goto attempt {attempt}: {goto_url}")

            async with page.expect_response(is_plp_response, timeout=30000) as plp_wait:
                await page.goto(goto_url, wait_until="domcontentloaded", timeout=120000)

            resp = await plp_wait.value
            src_url = resp.url

            # Captura info del request para paginar por API
            r = resp.request
            req_info = {
                "url": r.url,
                "method": r.method,
                "headers": await r.all_headers(),
                "post_data": r.post_data,
            }

            data = await resp.json()

            if DEBUG_DUMP_BFF:
                os.makedirs(DUMP_DIR, exist_ok=True)
                dump_path = os.path.join(DUMP_DIR, f"bff_{safe_slug(subcat_name)}_p1.json")
                try:
                    with open(dump_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    if DEBUG:
                        print(f"🧪 Dump BFF guardado: {dump_path}")
                except Exception:
                    pass

            return src_url, data, req_info

        except Exception as e:
            if DEBUG:
                print(f"  ⚠️ capture_first_plp_from_page attempt {attempt} failed:", repr(e))
            # pequeño backoff
            await page.wait_for_timeout(1000 * attempt)

    return "", None, {}


# =========================
# Scrape subcategoría (API pagination)
# =========================
async def scrape_subcategory(context: BrowserContext, page: Page, name: str, url: str, max_pages: int) -> List[dict]:
    all_by_sku: Dict[str, dict] = {}

    src1, data1, req_info = await capture_first_plp_from_page(page, url, subcat_name=name)

    if not data1:
        if DEBUG:
            print(f"⚠️ 0 productos (no se capturó PLP): {url}")
        return []

    prods1 = extract_products_bff(data1)
    if not prods1:
        if DEBUG:
            print(f"⚠️ PLP capturado pero sin productos detectables: {url}")
        return []

    # page 1
    for p in prods1:
        p.update({
            "subcat_name": name,
            "subcat_url": url,
            "source_json_url": src1,
            "page_num": 1,
            "extracted_at": now_iso(),
        })
        all_by_sku[p["sku"]] = p

    if DEBUG:
        print(f"✅ PLP OK: {len(prods1)} productos en página 1")

    # paginación por API (sin abrir nuevas páginas)
    if not req_info:
        return list(all_by_sku.values())

    prev_count = len(all_by_sku)

    for page_num in range(2, max_pages + 1):
        srcp, datap = await fetch_plp_page_via_api(context, req_info, page_num)

        if not datap:
            if DEBUG:
                print(f"  ⛔ sin JSON en page {page_num}, paro.")
            break

        if DEBUG_DUMP_BFF and page_num <= 3:
            os.makedirs(DUMP_DIR, exist_ok=True)
            dump_path = os.path.join(DUMP_DIR, f"bff_{safe_slug(name)}_p{page_num}.json")
            if not os.path.exists(dump_path):
                try:
                    with open(dump_path, "w", encoding="utf-8") as f:
                        json.dump(datap, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        prodsp = extract_products_bff(datap)
        if not prodsp:
            if DEBUG:
                print(f"  ⛔ 0 productos en page {page_num}, paro.")
            break

        for p in prodsp:
            p.update({
                "subcat_name": name,
                "subcat_url": url,
                "source_json_url": srcp,
                "page_num": page_num,
                "extracted_at": now_iso(),
            })
            all_by_sku[p["sku"]] = p

        if DEBUG:
            print(f"  ✅ page {page_num}: +{len(prodsp)} (total únicos={len(all_by_sku)})")

        if len(all_by_sku) == prev_count:
            if DEBUG:
                print("  ⛔ sin nuevos SKUs, paro.")
            break
        prev_count = len(all_by_sku)

        # pequeño delay para no gatillar rate limits
        await asyncio.sleep(0.3)

    return list(all_by_sku.values())


# =========================
# CSV
# =========================
def write_csv(rows: List[dict], filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fields = [
        "sku", "name", "brand", "price", "list_price", "in_offer", "detail_url", "image_url",
        "subcat_name", "subcat_url", "source_json_url", "page_num", "extracted_at"
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


# =========================
# MAIN
# =========================
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=HEADLESS)
        context = await browser.new_context(
            ignore_https_errors=True,
            locale="es-CL",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        await install_blocking(context)

        # ✅ UNA sola página para todo (no abre/cierra constantemente)
        page = await context.new_page()

        print("\nSubcategorías:")
        for sc in SUBCATS:
            print(f"- {sc['name']} -> {sc['url']}")

        all_rows: List[dict] = []
        for sc in SUBCATS:
            print(f"\nScrape: {sc['name']}")
            try:
                rows = await scrape_subcategory(context, page, sc["name"], sc["url"], max_pages=MAX_PAGES)
                print("  productos:", len(rows))
                all_rows.extend(rows)
            except Exception as e:
                print("  ERROR:", repr(e))

        # cerrar al final
        await page.close()

        # dedup final
        dedup = {}
        for r in all_rows:
            dedup[(r.get("sku"), r.get("subcat_url"))] = r
        out_rows = list(dedup.values())

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = OUTPUT_DIR / f"{OUT_PREFIX}_{ts}.csv"
        write_csv(out_rows, str(out_csv))

        print("\nTotal filas:", len(out_rows))
        print("CSV generado:", out_csv)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())