import asyncio
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Page, Response

OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/licores_bebidas_aguas"))

# =========================
# CONFIG
# =========================
BASE = "https://www.jumbo.cl"
MAX_PAGES = 80
HEADLESS = True
DEBUG = True

DEBUG_DUMP_BFF = True
DUMP_DIR = "debug_bff"

OUT_PREFIX = "jumbo_licores_bebidas_y_aguas"

# -------------------------
# Subcategorías (con "Mostrar todo" por grupo)
# -------------------------
SUBCATS = [
    # VINOS
    {"name": "Vinos y Espumantes", "url": f"{BASE}/licores-bebidas-y-aguas/vinos/vinos-y-espumantes-destacados"},
    {"name": "Vinos Tintos", "url": f"{BASE}/licores-bebidas-y-aguas/vinos/vinos-tintos"},
    {"name": "Vinos Blancos", "url": f"{BASE}/licores-bebidas-y-aguas/vinos/vinos-blancos"},
    {"name": "Vinos Rosé", "url": f"{BASE}/licores-bebidas-y-aguas/vinos/vinos-rose"},
    {"name": "Vinos (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/vinos"},

    # CERVEZAS
    {"name": "Cervezas Tradicionales", "url": f"{BASE}/licores-bebidas-y-aguas/cervezas/cervezas-tradicionales"},
    {"name": "Cervezas Destacadas", "url": f"{BASE}/licores-bebidas-y-aguas/cervezas/cervezas-destacadas"},
    {"name": "Cervezas Artesanales", "url": f"{BASE}/licores-bebidas-y-aguas/cervezas/cervezas-artesanales"},
    {"name": "Cervezas sin Alcohol", "url": f"{BASE}/licores-bebidas-y-aguas/cervezas/cervezas-sin-alcohol"},
    {"name": "Cervezas (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/cervezas"},

    # DESTILADOS
    {"name": "Whisky", "url": f"{BASE}/licores-bebidas-y-aguas/destilados/whisky"},
    {"name": "Pisco", "url": f"{BASE}/licores-bebidas-y-aguas/destilados/pisco"},
    {"name": "Gin", "url": f"{BASE}/licores-bebidas-y-aguas/destilados/gin"},
    {"name": "Tequila y Mezcal", "url": f"{BASE}/licores-bebidas-y-aguas/destilados/tequila-y-mezcal"},
    {"name": "Destilados (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/destilados"},

    # BEBIDAS
    {"name": "Bebidas en Lata e Individuales", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-gaseosas/bebidas-en-lata-e-individuales"},
    {"name": "Bebidas Regulares", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-gaseosas/bebidas-regulares"},
    {"name": "Bebidas Light o Zero Azúcar", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-gaseosas/bebidas-light-o-zero-azucar"},
    {"name": "Bebidas Retornables", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-gaseosas/bebidas-retornables"},
    {"name": "Bebidas (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-gaseosas"},

    # JUGOS
    {"name": "Jugos y Néctar", "url": f"{BASE}/licores-bebidas-y-aguas/jugos/jugos-y-nectar"},
    {"name": "Jugos en Polvo", "url": f"{BASE}/licores-bebidas-y-aguas/jugos/jugos-en-polvo"},
    {"name": "Jugos Individuales", "url": f"{BASE}/licores-bebidas-y-aguas/jugos/jugos-individuales"},
    {"name": "Jugos Frescos", "url": f"{BASE}/licores-bebidas-y-aguas/jugos/jugos-frescos"},
    {"name": "Jugos (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/jugos"},

    # AGUAS
    {"name": "Aguas Minerales", "url": f"{BASE}/licores-bebidas-y-aguas/aguas/aguas-minerales"},
    {"name": "Aguas Saborizadas", "url": f"{BASE}/licores-bebidas-y-aguas/aguas/aguas-saborizadas"},
    {"name": "Aguas Purificadas", "url": f"{BASE}/licores-bebidas-y-aguas/aguas/aguas-purificadas"},
    {"name": "Aguas (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/aguas"},

    # CÓCTELES
    {"name": "Cóctel Ice y Ready to Drink", "url": f"{BASE}/licores-bebidas-y-aguas/cocteles/coctel-ice-y-ready-to-drink"},
    {"name": "Mango y Pisco Sour", "url": f"{BASE}/licores-bebidas-y-aguas/cocteles/mango-y-pisco-sour"},
    {"name": "Piña Colada y Otros", "url": f"{BASE}/licores-bebidas-y-aguas/cocteles/pina-colada-y-otros"},
    {"name": "Mojitos y Margaritas", "url": f"{BASE}/licores-bebidas-y-aguas/cocteles/mojitos-y-margaritas"},
    {"name": "Cócteles (Mostrar todo)", "url": f"{BASE}/licores-bebidas-y-aguas/cocteles"},

    # OTROS
    {"name": "Espumantes y Sidras", "url": f"{BASE}/licores-bebidas-y-aguas/espumantes-y-sidras"},
    {"name": "Bebidas Energéticas", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-energeticas"},

    {"name": "Spritz", "url": f"{BASE}/licores-bebidas-y-aguas/licores-y-spritz/spritz"},
    {"name": "Licores de Crema", "url": f"{BASE}/licores-bebidas-y-aguas/licores-y-spritz/licores-de-crema"},
    {"name": "Bajativos", "url": f"{BASE}/licores-bebidas-y-aguas/licores-y-spritz/bajativos"},
    {"name": "Fernet y Licores de Hierba", "url": f"{BASE}/licores-bebidas-y-aguas/licores-y-spritz/fernet-y-licores-de-hierba"},

    {"name": "Cervezas sin Alcohol (Sin Alcohol)", "url": f"{BASE}/licores-bebidas-y-aguas/sin-alcohol/cervezas-sin-alcohol"},
    {"name": "Vinos y Espumantes sin Alcohol", "url": f"{BASE}/licores-bebidas-y-aguas/sin-alcohol/vinos-y-espumantes-sin-alcohol"},
    {"name": "Cócteles y Licores sin Alcohol", "url": f"{BASE}/licores-bebidas-y-aguas/sin-alcohol/cocteles-y-licores-sin-alcohol"},

    {"name": "Té Helado", "url": f"{BASE}/licores-bebidas-y-aguas/infusiones-frias/te-helado"},
    {"name": "Kombucha", "url": f"{BASE}/licores-bebidas-y-aguas/infusiones-frias/kombucha"},

    {"name": "Bebidas Isotónicas", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-isotonicas-y-sueros/bebidas-isotonicas"},
    {"name": "Sueros", "url": f"{BASE}/licores-bebidas-y-aguas/bebidas-isotonicas-y-sueros/sueros"},

    {"name": "Agua Tónica", "url": f"{BASE}/licores-bebidas-y-aguas/agua-tonica-y-ginger-beer/agua-tonica"},
    {"name": "Ginger Beer", "url": f"{BASE}/licores-bebidas-y-aguas/agua-tonica-y-ginger-beer/ginger-beer"},
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
    "sp.vtex.com/event",
    "maze.co",
    "creativecdn.com",
    "aria.microsoft.com",
    "omnichannelengagementhub.com",
]

def should_block(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in BLOCK_PATTERNS)

async def install_blocking(context):
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
    cand = deep_find_first(p, ["detailUrl", "detailURL", "url", "link", "href", "slug", "linkText"])
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
# BFF helpers (seed + paginar por API)
# =========================
def is_bff_plp_url(url: str) -> bool:
    return "bff.jumbo.cl/catalog/plp" in url.lower()

def sanitize_headers(h: Dict[str, str]) -> Dict[str, str]:
    drop = {
        "host", "content-length", "accept-encoding", "connection",
        "origin", "referer", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
    }
    out = {}
    for k, v in h.items():
        if k.lower() in drop:
            continue
        out[k] = v
    out.setdefault("content-type", "application/json")
    out.setdefault("accept", "application/json, text/plain, */*")
    return out

def try_parse_json(s: Optional[str]) -> Optional[dict]:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def infer_page_size(payload: dict) -> Optional[int]:
    for k in ("size", "limit", "pageSize", "perPage"):
        v = payload.get(k)
        if isinstance(v, int) and v > 0:
            return v
    pag = payload.get("pagination")
    if isinstance(pag, dict):
        for k in ("size", "limit", "pageSize", "perPage"):
            v = pag.get(k)
            if isinstance(v, int) and v > 0:
                return v
    return None

def mutate_pagination(payload: dict, page_num: int) -> dict:
    p = json.loads(json.dumps(payload))  # deep copy

    if isinstance(p.get("page"), int):
        p["page"] = page_num
        return p
    if isinstance(p.get("currentPage"), int):
        p["currentPage"] = page_num
        return p

    if isinstance(p.get("pagination"), dict):
        pag = p["pagination"]
        if isinstance(pag.get("page"), int):
            pag["page"] = page_num
            return p
        if isinstance(pag.get("currentPage"), int):
            pag["currentPage"] = page_num
            return p

    size = infer_page_size(p) or 24

    if isinstance(p.get("from"), int):
        p["from"] = (page_num - 1) * size
        if isinstance(p.get("size"), int):
            p["size"] = size
        return p

    if isinstance(p.get("offset"), int):
        p["offset"] = (page_num - 1) * size
        if isinstance(p.get("limit"), int):
            p["limit"] = size
        return p

    if isinstance(p.get("start"), int):
        p["start"] = (page_num - 1) * size
        if isinstance(p.get("rows"), int):
            p["rows"] = size
        return p

    p["page"] = page_num
    return p

async def capture_seed_bff_request(page: Page, url: str, timeout_ms: int = 120000) -> Tuple[Optional[dict], Optional[dict]]:
    def pred(resp: Response) -> bool:
        try:
            return resp.request.resource_type in ("xhr", "fetch") and is_bff_plp_url(resp.url)
        except Exception:
            return False

    async with page.expect_response(pred, timeout=timeout_ms) as resp_info:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    resp = await resp_info.value
    try:
        data = await resp.json()
    except Exception:
        return None, None

    req = resp.request
    headers = await req.all_headers()
    post_data = try_parse_json(req.post_data)

    seed = {
        "url": req.url,
        "method": req.method,
        "headers": sanitize_headers(headers),
        "post_data": post_data,
    }
    return seed, data

async def fetch_bff_page(context, seed: dict, page_num: int) -> Tuple[str, Optional[dict]]:
    url = seed["url"]
    method = seed.get("method") or "POST"
    headers = seed.get("headers") or {}
    base_payload = seed.get("post_data") or {}

    payload = mutate_pagination(base_payload, page_num)
    resp = await context.request.fetch(
        url,
        method=method,
        headers=headers,
        data=json.dumps(payload),
        timeout=120000,
    )
    if not resp.ok:
        if DEBUG:
            print(f"⚠️ BFF status {resp.status} en page={page_num} url={url}")
        return url, None
    try:
        return url, await resp.json()
    except Exception:
        return url, None

# =========================
# Scrape subcategoría (1 pestaña + paginar por BFF)
# =========================
async def scrape_subcategory(context, page: Page, name: str, url: str, max_pages: int) -> List[dict]:
    all_by_sku: Dict[str, dict] = {}

    seed = None
    data0 = None
    for attempt in range(1, 4):
        try:
            seed, data0 = await capture_seed_bff_request(page, url, timeout_ms=120000)
            if seed and data0:
                break
        except Exception as e:
            if DEBUG:
                print(f"⚠️ intento {attempt}/3 falló capturando seed BFF: {repr(e)}")
            await page.wait_for_timeout(800 * attempt)

    if not seed or not data0:
        if DEBUG:
            print(f"⚠️ 0 productos (no se pudo capturar BFF seed): {url}")
        return []

    src_url = seed["url"]
    prods = extract_products_bff(data0)

    if DEBUG_DUMP_BFF:
        os.makedirs(DUMP_DIR, exist_ok=True)
        dump_path = os.path.join(DUMP_DIR, f"bff_{safe_slug(name)}_p1.json")
        try:
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(data0, f, ensure_ascii=False, indent=2)
            if DEBUG:
                print(f"🧪 Dump BFF guardado: {dump_path}")
        except Exception:
            pass

    if not prods:
        if DEBUG:
            print(f"⚠️ 0 productos (BFF respondió pero no se detectaron productos): {url}")
        return []

    for p in prods:
        p.update({
            "subcat_name": name,
            "subcat_url": url,
            "source_json_url": src_url,
            "page_num": 1,
            "extracted_at": now_iso(),
        })
        all_by_sku[p["sku"]] = p

    prev_count = len(all_by_sku)
    for page_num in range(2, max_pages + 1):
        await page.wait_for_timeout(150)

        src2, data = await fetch_bff_page(context, seed, page_num)
        if not data:
            break

        if DEBUG_DUMP_BFF:
            os.makedirs(DUMP_DIR, exist_ok=True)
            dump_path = os.path.join(DUMP_DIR, f"bff_{safe_slug(name)}_p{page_num}.json")
            if not os.path.exists(dump_path):
                try:
                    with open(dump_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        prods2 = extract_products_bff(data)
        if not prods2:
            break

        for p in prods2:
            p.update({
                "subcat_name": name,
                "subcat_url": url,
                "source_json_url": src2,
                "page_num": page_num,
                "extracted_at": now_iso(),
            })
            all_by_sku[p["sku"]] = p

        if len(all_by_sku) == prev_count:
            break
        prev_count = len(all_by_sku)

    return list(all_by_sku.values())

# =========================
# CSV (delimiter=";")
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
# MAIN (una sola pestaña)
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

        # dedup por (sku, subcat_url)
        dedup = {}
        for r in all_rows:
            dedup[(r.get("sku"), r.get("subcat_url"))] = r
        out_rows = list(dedup.values())

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = OUTPUT_DIR / f"{OUT_PREFIX}_{ts}.csv"
        write_csv(out_rows, str(out_csv))

        print("\nTotal filas:", len(out_rows))
        print("CSV generado:", out_csv)

        await page.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())