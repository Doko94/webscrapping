import asyncio
import csv
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from pathlib import Path
import os

OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/hogar"))

BASE = "https://www.unimarc.cl"
CATEGORIES_HUB = "https://www.unimarc.cl"
MAX_PAGES = 80

SECTION_LEFT_TEXT = "Hogar"
SECTION_SLUG = "hogar"

# ---------------------------
# Utils: slugify (Plan B)
# ---------------------------
def slugify_es(text: str) -> str:
    s = text.strip().lower()
    repl = {
        "á":"a","é":"e","í":"i","ó":"o","ú":"u",
        "ä":"a","ë":"e","ï":"i","ö":"o","ü":"u",
        "ñ":"n","ç":"c",
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
        if detail and detail.startswith("/"):
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

async def safe_click(locator, timeout_ms=60000):
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

async def click_page_number(page, next_page: int):
    selector = f"a[href*='page={next_page}']"
    for _ in range(3):
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return False
        try:
            await locator.scroll_into_view_if_needed(timeout=60000)
            await locator.click(force=True, timeout=60000)
            return True
        except Exception:
            await page.wait_for_timeout(500)
    return False

# ---------------------------
# 1) Menú: abrir Categorías y seleccionar Hogar
# ---------------------------
async def open_categories_and_select_left(page, left_text: str):
    await page.goto(CATEGORIES_HUB, wait_until="domcontentloaded", timeout=120000)
    await safe_click(page.locator("text=Categorías").first, timeout_ms=60000)
    await page.wait_for_timeout(900)
    await safe_click(page.locator(f"text={left_text}").first, timeout_ms=60000)
    await page.wait_for_timeout(1400)

async def get_links_under_group(page, section_slug: str, group_title: str):
    """
    Saca links en batch con evaluate_all (evita nth(i) + timeouts por DOM dinámico)
    """
    group_block = page.locator(
        f"xpath=//*[self::div or self::section][.//text()[normalize-space()='{group_title}']]"
    ).first

    if await group_block.count() == 0:
        return []

    a_tags = group_block.locator("a[href*='/category/']")
    pairs = await a_tags.evaluate_all(
        """els => els.map(e => ({
            href: e.getAttribute('href') || '',
            text: (e.innerText || '').trim()
        }))"""
    )

    links = []
    for p in pairs:
        name = (p.get("text") or "").strip()
        href = (p.get("href") or "").strip()
        if not name or name.lower() == "ver todo":
            continue
        url = urljoin(BASE, href)
        if f"/category/{section_slug}/" in url:
            links.append({"group": group_title, "name": name, "url": url})

    dedup = {}
    for it in links:
        dedup[it["url"]] = it
    return list(dedup.values())

async def get_subcats_from_menu(page):
    await open_categories_and_select_left(page, SECTION_LEFT_TEXT)

    groups = [
        "Aire libre",
        "Librería, celebraciones y juguetes",
        "Cocina y mesa",
        "Ferretería y automotriz",
        "Hogar",
        "Textil hogar",
        "Electrohogar",
    ]

    out = []
    for g in groups:
        out.extend(await get_links_under_group(page, SECTION_SLUG, g))
    return out

# ---------------------------
# Plan B: construir URLs
# ---------------------------
def plan_b_urls():
    base = f"{BASE}/category/{SECTION_SLUG}"

    grupos = [
        {
            "group": "Aire libre",
            "group_slug": "aire-libre",
            "subcats": [
                "Otros accesorios",
                "Carbón y parrilla",
                "Juegos y deportes",
                "Piscina",
            ],
        },
        {
            "group": "Librería, celebraciones y juguetes",
            "group_slug": "libreria-celebraciones-y-juguetes",
            "subcats": [
                "Diarios y revistas",
                "Librería",
                "Celebraciones",
                "Juegos y juguetes",
            ],
        },
        {
            "group": "Cocina y mesa",
            "group_slug": "cocina-y-mesa",
            "subcats": [
                "Papeles cocina y bolsas multiuso",
                "Cristalería",
                "Herméticos, termos y botellas",
                "Ollas, sartenes y accesorios cocción",
                "Utensilios cocina y repostería",
                "Complementos mesa",
                "Loza y tazones",
            ],
        },
        {
            "group": "Ferretería y automotriz",
            "group_slug": "ferreteria-y-automotriz",
            "subcats": [
                "Pilas",
                "Iluminación y enchufes",
                "Herramientas y adhesivos",
                "Automotriz",
            ],
        },
        {
            "group": "Hogar",
            "group_slug": "hogar",
            "subcats": [
                "Organización",
                "Planchado y secado",
                "Decoración",
                "Calefacción y ventilación",
            ],
        },
        {
            "group": "Textil hogar",
            "group_slug": "textil-hogar",
            "subcats": [
                "Calzado y vestuario",
                "Dormitorio",
                "Textil cocina",
                "Textil baño",
            ],
        },
        {
            "group": "Electrohogar",
            "group_slug": "electrohogar",
            "subcats": [
                "Electrodomésticos",
                "Electrónica",
                "Cuidado personal",
            ],
        },
    ]

    out = []
    for grupo in grupos:
        for subcat in grupo["subcats"]:
            out.append({
                "group": grupo["group"],
                "name": subcat,
                "url": f"{base}/{grupo['group_slug']}/{slugify_es(subcat)}"
            })

    dedup = {}
    for it in out:
        dedup[it["url"]] = it
    return list(dedup.values())

# ---------------------------
# 2) Scrape por URL (con paginación)
# ---------------------------
async def scrape_category_with_pagination(context, group_name: str, category_name: str, category_url: str):
    page = await context.new_page()
    slug = category_slug_from_url(category_url)

    all_by_sku = {}
    page_num = 1

    url_json, status, data = await capture_next_data_around(
        page,
        page.goto(page_url(category_url, page_num), wait_until="domcontentloaded", timeout=120000),
        slug=slug,
        page_num=page_num,
        timeout_ms=120000
    )

    items = extract_products(data)
    for it in items:
        it["group_name"] = group_name
        it["category_name"] = category_name
        it["category_url"] = category_url
        it["source_next_data_url"] = url_json
        it["extracted_at"] = datetime.now().isoformat(timespec="seconds")
        all_by_sku[it["sku"]] = it

    while page_num < MAX_PAGES:
        next_page = page_num + 1
        if await page.locator(f"a[href*='page={next_page}']").count() == 0:
            break

        ok = await click_page_number(page, next_page)
        if not ok:
            break

        url_json, status, data = await capture_next_data_around(
            page,
            asyncio.sleep(0),
            slug=slug,
            page_num=next_page,
            timeout_ms=120000
        )
        page_num = next_page

        items = extract_products(data)
        before = len(all_by_sku)

        for it in items:
            it["group_name"] = group_name
            it["category_name"] = category_name
            it["category_url"] = category_url
            it["source_next_data_url"] = url_json
            it["extracted_at"] = datetime.now().isoformat(timespec="seconds")
            all_by_sku[it["sku"]] = it

        if len(all_by_sku) == before:
            break

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

        menu_page = await context.new_page()
        subcats = await get_subcats_from_menu(menu_page)
        await menu_page.close()

        if not subcats:
            print("No pude extraer links desde el menú (headless). Usando Plan B (slugify).")
            subcats = plan_b_urls()

        print(f"\nSubcategorías detectadas en [{SECTION_LEFT_TEXT}]:", len(subcats))
        for sc in subcats:
            print(" -", sc["group"], "|", sc["name"], "->", sc["url"])

        all_items = []
        for sc in subcats:
            print(f"\nScrape: [{sc['group']}] {sc['name']}")
            try:
                items = await scrape_category_with_pagination(context, sc["group"], sc["name"], sc["url"])
                print("  productos únicos:", len(items))
                all_items.extend(items)
            except Exception as e:
                print("  ERROR en subcat:", sc["url"])
                print("  ", repr(e))

        dedup = {}
        for it in all_items:
            dedup[(it["sku"], it["category_url"])] = it
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