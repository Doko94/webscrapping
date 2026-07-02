import asyncio
import csv
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from pathlib import Path
import os

OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/despensa"))

# OUTPUT_DIR = Path(
#     r"C:\Users\fvergram\OneDrive - NTT DATA EMEAL\Desktop\webscrapping\Supermercados\Unimarc\src\output\despensa"
# )

BASE = "https://www.unimarc.cl"
CATEGORIES_HUB = "https://www.unimarc.cl"
MAX_PAGES = 80

SECTION_LEFT_TEXT = "Despensa"
SECTION_SLUG = "despensa"

GROUPS = [
    "Arroz y legumbres",
    "Fideos, pastas y salsas",
    "Aceite y aliños",
    "Azúcar y endulzantes",
    "Condimentos y salsas",
    "Harina y repostería",
    "Conservas",
    "Cóctel y snacks",
    "Comida instantánea y preparada",
    "Cocina internacional",
    "Productos naturales",
]

# ---------------------------
# Utils: slugify (Plan B)
# ---------------------------
def slugify_es(text: str) -> str:
    s = text.strip().lower()
    repl = {
        "á":"a","é":"e","í":"i","ó":"o","ú":"u",
        "ä":"a","ë":"e","ï":"i","ö":"o","ü":"u",
        "ñ":"n"
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    s = s.replace("&", " y ")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "-")
    s = re.sub(r"-+", "-", s)
    return s

# ---------------------------
# Extractor de productos
# ---------------------------
def to_int_clp(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else None

def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from walk(it)

def is_product_dict(d: dict) -> bool:
    return (
        isinstance(d, dict)
        and (d.get("sku") or d.get("itemId") or d.get("productId"))
        and (d.get("nameComplete") or d.get("name"))
        and isinstance(d.get("sellers"), list)
        and len(d["sellers"]) > 0
    )

def extract_products(data):
    products = {}
    for d in walk(data):
        if not is_product_dict(d):
            continue

        sku = str(d.get("sku") or d.get("itemId") or d.get("productId")).strip()
        name = (d.get("nameComplete") or d.get("name") or "").strip()

        seller0 = d["sellers"][0] if d.get("sellers") else {}
        price = to_int_clp(seller0.get("price"))
        list_price = to_int_clp(seller0.get("listPrice") or seller0.get("priceWithoutDiscount"))
        in_offer = bool(seller0.get("inOffer"))
        saving_txt = seller0.get("saving") or ""

        promo = d.get("promotion") or {}
        promo_price = to_int_clp(promo.get("price")) if isinstance(promo, dict) else None
        if price is None and promo_price:
            price = promo_price

        discount_price = price if in_offer else None

        img = None
        imgs = d.get("images")
        if isinstance(imgs, list) and imgs:
            if isinstance(imgs[0], str):
                img = imgs[0]
            elif isinstance(imgs[0], dict):
                img = imgs[0].get("url") or imgs[0].get("imageUrl")

        detail = d.get("detailUrl") or d.get("url") or d.get("link") or d.get("slug") or ""
        if detail and isinstance(detail, str) and detail.startswith("/"):
            detail_url = BASE + detail
        else:
            detail_url = detail

        products[sku] = {
            "sku": sku,
            "name": name,
            "brand": (d.get("brand") or "").strip(),
            "net_content": (d.get("netContentLevelSmall") or d.get("netContent") or "").strip(),
            "unit": (d.get("measurementUnitUn") or d.get("measurementUnit") or "").strip(),
            "price": price,
            "list_price": list_price,
            "discount_price": discount_price,
            "in_offer": in_offer,
            "saving_text": saving_txt,
            "ppum": seller0.get("ppum") or "",
            "ppum_list_price": seller0.get("ppumListPrice") or "",
            "detail_url": detail_url,
            "image_url": img,
        }

    return list(products.values())

# ---------------------------
# Playwright helpers
# ---------------------------
def category_slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]

def page_url(base_url: str, page_num: int) -> str:
    return base_url if page_num <= 1 else f"{base_url}?page={page_num}"

async def safe_click(locator, timeout_ms=45000):
    await locator.wait_for(state="visible", timeout=timeout_ms)
    try:
        await locator.scroll_into_view_if_needed(timeout=timeout_ms)
        await locator.click(timeout=timeout_ms, force=True)
        return
    except Exception:
        el = await locator.element_handle()
        if el is None:
            raise
        await el.evaluate("e => e.click()")

async def capture_next_data_around(page, action_coro, slug: str, page_num: int, timeout_ms=120000):
    def predicate(r):
        ok = ("/_next/data/" in r.url) and (f"{slug}.json" in r.url)
        if not ok:
            return False
        if page_num > 1:
            return f"page={page_num}" in r.url
        return True

    async with page.expect_response(predicate, timeout=timeout_ms) as resp_info:
        await action_coro

    resp = await resp_info.value
    data = await resp.json()
    return resp.url, resp.status, data

async def open_categories_and_select_left(page, left_text: str):
    await page.goto(CATEGORIES_HUB, wait_until="domcontentloaded", timeout=120000)
    await safe_click(page.locator("text=Categorías").first, timeout_ms=45000)
    await page.wait_for_timeout(800)
    await safe_click(page.locator(f"text={left_text}").first, timeout_ms=45000)
    await page.wait_for_timeout(1200)

async def get_links_under_group(page, section_slug: str, group_title: str):
    block = page.locator(
        f"xpath=//*[self::div or self::section][.//text()[normalize-space()='{group_title}']]"
    ).first
    if await block.count() == 0:
        return []

    rows = await block.locator("a[href*='/category/']").evaluate_all(
        """(els) => els.map(a => ({
            href: a.getAttribute('href') || '',
            text: (a.innerText || a.textContent || '').trim()
        }))"""
    )

    links = []
    for r in rows:
        name = (r.get("text") or "").strip()
        href = (r.get("href") or "").strip()
        if not name or name.lower() == "ver todo":
            continue

        url = urljoin(BASE, href)

        if f"/category/{section_slug}/" in url:
            links.append({"group": group_title, "name": name, "url": url})

    dedup = {it["url"]: it for it in links}
    return list(dedup.values())

async def get_subcats_from_menu(page):
    try:
        await open_categories_and_select_left(page, SECTION_LEFT_TEXT)
        out = []
        for g in GROUPS:
            out.extend(await get_links_under_group(page, SECTION_SLUG, g))
        dedup = {it["url"]: it for it in out}
        return list(dedup.values())
    except Exception as e:
        print(f"[WARN] Menú headless falló: {e}")
        return []

# ---------------------------
# Plan B
# ---------------------------
def plan_b_urls():
    base = f"{BASE}/category/{SECTION_SLUG}"

    grupos = [
        {
            "group": "Arroz y legumbres",
            "group_slug": "arroz-y-legumbres",
            "subcats": [
                "Arroz",
                "Arroz preparado",
                "Legumbres",
                "Quínoa",
            ],
        },
        {
            "group": "Fideos, pastas y salsas",
            "group_slug": "fideos-pastas-y-salsas",
            "subcats": [
                "Cortos",
                "Couscous",
                "Instantáneos",
                "Largos",
                "Lasaña",
                "Rellenos",
                "Salsa para pastas",
                "Pastas frescas",
            ],
        },
        {
            "group": "Aceite y aliños",
            "group_slug": "aceite-y-alinos",
            "subcats": [
                "Aceite maravilla",
                "Aceite oliva",
                "Aceite vegetal",
                "Otros aceites",
                "Sal",
                "Sucedáneo",
                "Vinagre y aceto",
            ],
        },
        {
            "group": "Azúcar y endulzantes",
            "group_slug": "azucar-y-endulzantes",
            "subcats": [
                "Azúcar",
                "Endulzantes",
            ],
        },
        {
            "group": "Condimentos y salsas",
            "group_slug": "condimentos-y-salsas",
            "subcats": [
                "Condimentos",
                "Ketchup",
                "Mayonesa",
                "Mostaza",
                "Otras salsas",
                "Salsa de soya",
                "Salsa picante",
            ],
        },
        {
            "group": "Harina y repostería",
            "group_slug": "harina-y-reposteria",
            "subcats": [
                "Harina",
                "Leche condensada y evaporada",
                "Levadura y polvos de hornear",
                "Maicena y sémola",
                "Postres en polvo",
                "Bases y premezclas",
                "Decoración y coberturas",
                "Esencias",
            ],
        },
        {
            "group": "Conservas",
            "group_slug": "conservas",
            "subcats": [
                "Comida en conserva",
                "Frutas en conserva",
                "Legumbres en conserva",
                "Pescados y mariscos en conserva",
                "Verduras en conserva",
            ],
        },
        {
            "group": "Cóctel y snacks",
            "group_slug": "coctel-y-snacks",
            "subcats": [
                "Frutos secos",
                "Galletas cóctel",
                "Papas fritas",
                "Pastas y salsas",
                "Snack",
                "Aceitunas y encurtidos",
            ],
        },
        {
            "group": "Comida instantánea y preparada",
            "group_slug": "comida-instantanea-y-preparada",
            "subcats": [
                "Puré instantáneo",
                "Sopas, cremas y bases",
                "Sandwich y tortillas",
                "Platos y ensaladas",
                "Fideos y pastas",
            ],
        },
        {
            "group": "Cocina internacional",
            "group_slug": "cocina-internacional",
            "subcats": [
                "Comida japonesa",
                "Comida árabe",
                "Comida thai",
                "Comida peruana",
            ],
        },
        {
            "group": "Productos naturales",
            "group_slug": "productos-naturales",
            "subcats": [
                "Cereales y funcionales",
                "Semillas",
            ],
        },
    ]

    out = []
    for grupo in grupos:
        for subcat in grupo["subcats"]:
            url = f"{base}/{grupo['group_slug']}/{slugify_es(subcat)}"
            out.append({
                "group": grupo["group"],
                "name": subcat,
                "url": url
            })

    dedup = {it["url"]: it for it in out}
    return list(dedup.values())

# ---------------------------
# Scrape por URL (paginación) SIN clicks
# ---------------------------
async def scrape_category_with_pagination(context, group_name: str, category_name: str, category_url: str):
    page = await context.new_page()
    slug = category_slug_from_url(category_url)

    all_by_sku = {}
    page_num = 1

    while page_num <= MAX_PAGES:
        try:
            url_json, status, data = await capture_next_data_around(
                page,
                page.goto(page_url(category_url, page_num), wait_until="domcontentloaded", timeout=120000),
                slug=slug,
                page_num=page_num,
                timeout_ms=120000
            )
        except Exception as e:
            if page_num == 1:
                print(f"  [WARN] Page 1 falló ({category_url}): {e}")
            break

        items = extract_products(data)
        if not items:
            break

        before = len(all_by_sku)
        for it in items:
            it["group_name"] = group_name
            it["category_name"] = category_name
            it["category_url"] = category_url
            it["source_next_data_url"] = url_json
            it["extracted_at"] = datetime.now().isoformat(timespec="seconds")
            all_by_sku[it["sku"]] = it
        after = len(all_by_sku)

        if after == before and page_num > 1:
            break

        page_num += 1

    await page.close()
    return list(all_by_sku.values())

# ---------------------------
# Main
# ---------------------------
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
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

        # A) Links reales desde menú
        menu_page = await context.new_page()
        subcats = await get_subcats_from_menu(menu_page)
        await menu_page.close()

        # B) Plan B
        if not subcats:
            print("No pude extraer links desde el menú (headless). Usando Plan B (slugify).")
            subcats = plan_b_urls()

        print(f"\nSubcategorías detectadas en [{SECTION_LEFT_TEXT}]: {len(subcats)}")
        for sc in subcats:
            print(" -", sc["group"], "|", sc["name"], "->", sc["url"])

        # Scrape
        all_items = []
        for sc in subcats:
            print(f"\nScrape: [{sc['group']}] {sc['name']}")
            items = await scrape_category_with_pagination(context, sc["group"], sc["name"], sc["url"])
            print("  productos únicos:", len(items))
            all_items.extend(items)

        # Dedup global
        dedup = {}
        for it in all_items:
            key = (it["sku"], it["category_url"])
            dedup[key] = it
        out_items = list(dedup.values())

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = OUTPUT_DIR / f"unimarc_{SECTION_SLUG}_subcats_{ts}.csv"

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        if out_items:
            with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(out_items[0].keys()), delimiter=";")
                w.writeheader()
                w.writerows(out_items)

        print("\nTotal filas:", len(out_items))
        print("CSV generado:", out_csv)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())