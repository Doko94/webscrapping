import asyncio
import csv
import json
import os
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, APIResponse
from cached_subcategories import load_cached_product_rows, load_cached_subcategories

OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/la_boti"))
BASE = "https://super.lider.cl"

HEADLESS = os.getenv("LIDER_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}
DEBUG = True
MAX_PAGES = 60
OUT_PREFIX = "lider_la_boti"

CATEGORY_NAME = "La Boti"

BLOCK_PATTERNS = [
    "googletagservices.com",
    "googleadservices.com",
    "doubleclick.net",
    "pagead2.googlesyndication.com",
]

TARGET_GROUPS = {
    "Vinos y Espumantes 3x",
    "Cerveza",
    "Sin Alcohol",
    "Coctel",
    "Espumantes",
    "Vinos",
    "Destilados",
    "Preparalo tu Mismo",
    "Prepáralo tu Mismo",
}


# =========================
# Utils
# =========================
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def normalize_text(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


TARGET_GROUPS_NORMALIZED = {normalize_text(x) for x in TARGET_GROUPS}


def should_block(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in BLOCK_PATTERNS)


async def random_pause(a=0.8, b=2.0):
    await asyncio.sleep(random.uniform(a, b))


async def install_blocking(context: BrowserContext):
    async def route_handler(route):
        if should_block(route.request.url):
            return await route.abort()
        return await route.continue_()

    await context.route("**/*", route_handler)


async def is_blocked(page: Page) -> bool:
    try:
        url = page.url.lower()
    except Exception:
        url = ""

    try:
        title = (await page.title()).strip().lower()
    except Exception:
        title = ""

    if "/blocked" in url:
        return True
    if "robot or human" in title:
        return True

    try:
        body = (await page.locator("body").inner_text()).strip().lower()
        if "robot or human" in body:
            return True
        if "activate and hold the button to confirm that you’re human".lower() in body:
            return True
    except Exception:
        pass

    return False


# =========================
# JSON helpers
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
            if k in keys and v not in (None, "", [], {}):
                return v
        for v in obj.values():
            got = deep_find_first(v, keys)
            if got not in (None, "", [], {}):
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = deep_find_first(it, keys)
            if got not in (None, "", [], {}):
                return got
    return None


def deep_find_all_lists(obj: Any) -> List[List[dict]]:
    out = []
    for node in walk_nodes(obj):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node[: min(10, len(node))]):
            out.append(node)
    return out


def score_product_candidate(lst: List[dict]) -> int:
    score = 0
    for p in lst[:100]:
        sku = deep_find_first(p, ["sku", "skuId", "itemId", "id", "productId", "productID", "ean"])
        name = deep_find_first(p, ["name", "productName", "displayName", "productTitle", "title"])
        price = deep_find_first(p, ["price", "bestPrice", "sellingPrice", "finalPrice", "Price", "sellingPriceValue"])
        if sku:
            score += 2
        if name:
            score += 3
        if price is not None:
            score += 1
    return score


def pick_best_products_list(data: Any) -> Optional[List[dict]]:
    lists = [lst for lst in deep_find_all_lists(data) if len(lst) >= 2]
    if not lists:
        return None

    best = None
    best_score = -1
    for lst in lists:
        s = score_product_candidate(lst) * 1000 + min(len(lst), 500)
        if s > best_score:
            best_score = s
            best = lst
    return best


# =========================
# Parse producto
# =========================
def parse_detail_url(p: dict) -> str:
    cand = deep_find_first(
        p,
        ["detailUrl", "detailURL", "url", "link", "href", "slug", "productUrl", "canonicalUrl"],
    )
    if isinstance(cand, str) and cand.strip():
        c = cand.strip()
        if c.startswith("http"):
            return c
        if c.startswith("/"):
            return urljoin(BASE, c)
        return urljoin(BASE, f"/{c}")
    return ""


def parse_image_url(p: dict) -> str:
    cand = deep_find_first(p, ["imageUrl", "image", "images", "src", "image_url", "thumbnail"])
    if isinstance(cand, str) and cand.strip():
        return cand.strip()
    if isinstance(cand, list) and cand:
        x = cand[0]
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return first_non_empty(x.get("url"), x.get("src"), x.get("imageUrl"), "") or ""
    if isinstance(cand, dict):
        return first_non_empty(cand.get("url"), cand.get("src"), cand.get("imageUrl"), "") or ""
    return ""


def parse_prices(p: dict) -> Tuple[Optional[int], Optional[int]]:
    price = deep_find_first(
        p,
        ["price", "bestPrice", "sellingPrice", "finalPrice", "Price", "currentPrice", "sellingPriceValue"],
    )
    list_price = deep_find_first(
        p,
        ["listPrice", "priceWithoutDiscount", "referencePrice", "ListPrice", "originalPrice", "wasPrice"],
    )

    price_i = to_int_clp(price)
    list_i = to_int_clp(list_price)
    return price_i, list_i


def parse_product(p: dict) -> Optional[dict]:
    sku = deep_find_first(p, ["sku", "skuId", "itemId", "id", "productId", "productID", "ean"])
    name = deep_find_first(p, ["name", "productName", "displayName", "productTitle", "title"])
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


def extract_products_from_json(data: Any) -> List[dict]:
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
# Popups
# =========================
async def dismiss_possible_popups(page: Page):
    candidates = [
        "button:has-text('Aceptar')",
        "button:has-text('Entendido')",
        "button:has-text('Cerrar')",
        "button[aria-label='close']",
        "[data-testid='close-button']",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=1500)
                await page.wait_for_timeout(500)
        except Exception:
            pass


# =========================
# Context factory
# =========================
async def create_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        ignore_https_errors=True,
        locale="es-CL",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await install_blocking(context)
    return context


# =========================
# Descubrir subcategorías
# =========================
async def discover_subcategories(browser: Browser) -> List[dict]:
    context = await create_context(browser)
    page = await context.new_page()

    try:
        await page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=120000)
        await dismiss_possible_popups(page)
        await page.wait_for_timeout(2500)

        cat_btn_candidates = [
            "button:has-text('Categorías')",
            "text=Categorías",
            "[aria-label*='Categor']",
            "div:has-text('Categorías')",
        ]

        opened = False
        for sel in cat_btn_candidates:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    print(f"[DEBUG] Click en botón categorías con selector: {sel}")
                    await btn.click(timeout=5000)
                    opened = True
                    await page.wait_for_timeout(2500)
                    break
            except Exception as e:
                print(f"[DEBUG] Falló selector botón categorías {sel}: {e}")

        if not opened:
            raise RuntimeError("No pude abrir el menú de Categorías")

        try:
            body_text = await page.locator("body").inner_text()
            print("\n[DEBUG] Primeros 3000 caracteres del body tras abrir menú:\n")
            print(body_text[:3000])
        except Exception:
            pass

        laboti_candidates = [
            f"text={CATEGORY_NAME}",
            f"a:has-text('{CATEGORY_NAME}')",
            f"div:has-text('{CATEGORY_NAME}')",
            f"li:has-text('{CATEGORY_NAME}')",
            f"span:has-text('{CATEGORY_NAME}')",
        ]

        laboti_el = None
        for sel in laboti_candidates:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    print(f"[DEBUG] Encontrado '{CATEGORY_NAME}' con selector: {sel}")
                    laboti_el = loc
                    break
            except Exception as e:
                print(f"[DEBUG] Falló búsqueda selector {sel}: {e}")

        if laboti_el is None:
            raise RuntimeError("No encontré 'La Boti' en el menú lateral")

        try:
            await laboti_el.hover(timeout=3000)
            await page.wait_for_timeout(1200)
        except Exception as e:
            print(f"[DEBUG] Hover falló: {e}")

        try:
            await laboti_el.click(timeout=3000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[DEBUG] Click en La Boti falló: {e}")

        links = await page.evaluate(
            """
            () => {
                const clean = (s) => (s || "").replace(/\\s+/g, " ").trim();

                const normalize = (s) => {
                    return clean(s)
                        .normalize("NFKD")
                        .replace(/[\\u0300-\\u036f]/g, "")
                        .toLowerCase();
                };

                const TARGET_GROUPS = [
                    "Vinos y Espumantes 3x",
                    "Cerveza",
                    "Sin Alcohol",
                    "Coctel",
                    "Espumantes",
                    "Vinos",
                    "Destilados",
                    "Preparalo tu Mismo",
                    "Prepáralo tu Mismo"
                ].map(normalize);

                const results = [];
                const all = Array.from(document.querySelectorAll("a, h2, h3, h4, div, span"));
                let currentGroup = null;

                for (const el of all) {
                    const txt = clean(el.textContent || "");
                    if (!txt) continue;

                    const txtNorm = normalize(txt);

                    if (TARGET_GROUPS.includes(txtNorm)) {
                        currentGroup = txt;
                        continue;
                    }

                    if (el.tagName === "A") {
                        const href = el.getAttribute("href") || "";
                        if (!href || !currentGroup) continue;

                        results.push({
                            group: currentGroup,
                            name: txt,
                            href: href
                        });
                    }
                }

                return results;
            }
            """
        )

        out = []
        seen = set()

        for item in links:
            group = (item.get("group") or "").strip()
            name = (item.get("name") or "").strip()
            href = (item.get("href") or "").strip()

            if not href:
                continue

            if normalize_text(group) not in TARGET_GROUPS_NORMALIZED:
                continue

            full_url = urljoin(BASE, href)
            full_url_low = full_url.lower()

            if "/browse/la-boti/" not in full_url_low:
                continue

            if "contentzone" in full_url_low or "co_ty=" in full_url_low or "co_nm=" in full_url_low:
                continue

            if normalize_text(name) in {
                "revisar todo",
                "ir a la categoria",
                "ir la categoria",
                "descubre mas",
                "¡descubre mas!",
            }:
                continue

            key = (group, name, full_url)
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "group": group,
                "name": name,
                "url": full_url,
            })

        print("\n[DEBUG] Subcategorías detectadas:")
        for x in out:
            print(f" - [{x['group']}] {x['name']} -> {x['url']}")

        if not out:
            raise RuntimeError("Se abrió el menú, pero no se detectaron subcategorías")

        return out

    finally:
        await page.close()
        await context.close()


# =========================
# Captura JSON
# =========================
def looks_like_product_api_url(url: str) -> bool:
    u = url.lower()
    hints = ["search", "products", "product", "catalog", "plp", "item", "collection", "query"]
    return any(h in u for h in hints)


async def capture_product_responses(page: Page, goto_url: str, settle_ms: int = 4500):
    captured = []

    async def on_response(resp):
        try:
            if resp.request.resource_type not in ("xhr", "fetch"):
                return

            url = resp.url
            if not looks_like_product_api_url(url):
                return

            ctype = (resp.headers.get("content-type") or "").lower()
            if "json" not in ctype and "javascript" not in ctype and "text/plain" not in ctype:
                return

            try:
                data = await resp.json()
            except Exception:
                return

            prods = extract_products_from_json(data)
            if not prods:
                return

            req = resp.request
            captured.append({
                "response_url": url,
                "data": data,
                "products": prods,
                "req_info": {
                    "url": req.url,
                    "method": req.method,
                    "headers": await req.all_headers(),
                    "post_data": req.post_data,
                },
            })
        except Exception:
            pass

    page.on("response", on_response)

    await page.goto(goto_url, wait_until="domcontentloaded", timeout=120000)
    await dismiss_possible_popups(page)
    await random_pause(1.2, 2.2)

    for _ in range(2):
        try:
            await page.mouse.wheel(0, random.randint(800, 1600))
        except Exception:
            pass
        await random_pause(0.8, 1.5)

    await page.wait_for_timeout(settle_ms)
    page.remove_listener("response", on_response)
    return captured


def pick_best_capture(captures: List[dict]) -> Optional[dict]:
    if not captures:
        return None
    best = None
    best_score = -1
    for c in captures:
        products = c.get("products") or []
        score = len(products)
        if score > best_score:
            best_score = score
            best = c
    return best


# =========================
# DOM fallback
# =========================
async def extract_products_from_dom(page: Page) -> List[dict]:
    raw = await page.evaluate(
        """
        () => {
            const clean = (s) => (s || "").replace(/\\s+/g, " ").trim();
            const toAbsolute = (href) => {
                try {
                    return new URL(href, location.origin).href;
                } catch(e) {
                    return href || "";
                }
            };

            const productAnchors = Array.from(document.querySelectorAll('a[href*="/ip/"]'));
            const results = [];
            const seen = new Set();

            for (const a of productAnchors) {
                const href = toAbsolute(a.getAttribute("href") || "");
                if (!href || seen.has(href)) continue;
                seen.add(href);

                let card =
                    a.closest('article') ||
                    a.closest('[data-testid*="product"]') ||
                    a.closest('li') ||
                    a.parentElement;

                if (!card) continue;

                const cardText = clean(card.innerText || card.textContent || "");
                if (!cardText) continue;

                let name = clean(a.innerText || a.textContent || "");
                const img = card.querySelector("img");
                const image_url = img ? (img.getAttribute("src") || img.getAttribute("data-src") || "") : "";
                const img_alt = img ? clean(img.getAttribute("alt") || "") : "";

                if (!name || name.length < 4) {
                    name = img_alt;
                }

                const matches = [...cardText.matchAll(/\\$\\s?([\\d\\.]+)/g)].map(m => m[1]);
                const prices = matches.map(x => x.replace(/\\./g, "")).filter(Boolean);

                let price = null;
                let list_price = null;

                if (prices.length === 1) {
                    price = prices[0];
                } else if (prices.length >= 2) {
                    const nums = prices.map(x => parseInt(x, 10)).filter(x => !Number.isNaN(x));
                    if (nums.length) {
                        price = String(Math.min(...nums));
                        list_price = String(Math.max(...nums));
                    }
                }

                if (!name || name.length < 4) {
                    const lines = cardText
                        .split(/\\n|  +/)
                        .map(x => clean(x))
                        .filter(Boolean)
                        .filter(x =>
                            !/^\\$/.test(x) &&
                            !/agregar/i.test(x) &&
                            !/rebaja/i.test(x) &&
                            !/combina/i.test(x) &&
                            !/^\\d+\\s?[xX]\\s?\\$/.test(x)
                        );

                    if (lines.length) {
                        name = lines.slice(0, 3).join(" ");
                    }
                }

                results.push({
                    detail_url: href,
                    image_url,
                    name,
                    price,
                    list_price,
                    raw_text: cardText
                });
            }

            return results;
        }
        """
    )

    out = []
    seen = set()

    for i, r in enumerate(raw, start=1):
        detail_url = (r.get("detail_url") or "").strip()
        image_url = (r.get("image_url") or "").strip()
        name = (r.get("name") or "").strip()
        price = to_int_clp(r.get("price"))
        list_price = to_int_clp(r.get("list_price"))

        if not detail_url:
            continue

        m = re.search(r"/ip/[^/]+/(\\d+)", detail_url)
        if m:
            sku = m.group(1)
        else:
            m2 = re.search(r"(\\d{6,})", detail_url)
            sku = m2.group(1) if m2 else f"dom_{i}"

        if not name:
            continue

        if sku in seen:
            continue
        seen.add(sku)

        out.append({
            "sku": sku,
            "name": name[:250],
            "brand": "",
            "price": price,
            "list_price": list_price,
            "in_offer": (price is not None and list_price is not None and price < list_price),
            "detail_url": detail_url,
            "image_url": image_url,
        })

    return out


# =========================
# Scrape subcategoría
# =========================
async def scrape_subcategory(browser: Browser, group: str, name: str, url: str) -> Tuple[List[dict], bool]:
    context = await create_context(browser)
    page = await context.new_page()

    try:
        await random_pause(1.5, 3.0)

        captures = await capture_product_responses(page, url)
        if await is_blocked(page):
            if DEBUG:
                print(f"[BLOCKED] [{group}] {name} -> {page.url}")
            return [], True

        best_capture = pick_best_capture(captures)

        if best_capture:
            src1 = best_capture["response_url"]
            prods1 = best_capture["products"]
            if DEBUG:
                print(f"✅ JSON detectado [{group}] {name}: {len(prods1)} productos")
        else:
            for _ in range(2):
                try:
                    await page.mouse.wheel(0, random.randint(800, 1600))
                except Exception:
                    pass
                await random_pause(0.6, 1.3)

            try:
                await page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass

            await random_pause(0.8, 1.4)

            if await is_blocked(page):
                if DEBUG:
                    print(f"[BLOCKED] [{group}] {name} -> {page.url}")
                return [], True

            prods1 = await extract_products_from_dom(page)
            src1 = url

        if DEBUG and not prods1:
            try:
                page_title = await page.title()
            except Exception:
                page_title = ""
            try:
                body_text = await page.locator("body").inner_text()
            except Exception:
                body_text = ""

            print(f"[DEBUG-EMPTY] title={page_title}")
            print(f"[DEBUG-EMPTY] url={page.url}")
            print(f"[DEBUG-EMPTY] body primeros 1500 chars:\\n{body_text[:1500]}")

        rows = []
        for p in prods1:
            p.update({
                "subcat_name": f"{group} > {name}",
                "subcat_url": url,
                "source_json_url": src1,
                "page_num": 1,
                "extracted_at": now_iso(),
            })
            rows.append(p)

        return rows, False

    finally:
        await page.close()
        await context.close()


# =========================
# CSV
# =========================
def write_csv(rows: List[dict], filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fields = [
        "sku",
        "name",
        "brand",
        "price",
        "list_price",
        "in_offer",
        "detail_url",
        "image_url",
        "subcat_name",
        "subcat_url",
        "source_json_url",
        "page_num",
        "extracted_at",
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

        try:
            subcats = await discover_subcategories(browser)
        except Exception as exc:
            print(f"[WARN] No se pudieron descubrir subcategorías online: {exc}")
            subcats = load_cached_subcategories(OUTPUT_DIR, CATEGORY_NAME, globals().get("CATEGORY_LANDING"))
            print(f"[WARN] Usando {len(subcats)} subcategorías cacheadas desde {OUTPUT_DIR}")

        if not subcats:
            raise RuntimeError("No se pudieron descubrir subcategorías para La Boti")

        all_rows: List[dict] = []
        blocked_count = 0

        for idx, sc in enumerate(subcats, start=1):
            print(f"\\n[{idx}/{len(subcats)}] Scrape: [{sc['group']}] {sc['name']}")

            rows, blocked = await scrape_subcategory(
                browser=browser,
                group=sc["group"],
                name=sc["name"],
                url=sc["url"],
            )

            if blocked:
                blocked_count += 1
                print("  bloqueado por anti-bot")
                if blocked_count >= 3:
                    print("\\nDemasiados bloqueos consecutivos. Se detiene el scraping.")
                    break
                await random_pause(8, 15)
                continue

            print("  productos:", len(rows))
            all_rows.extend(rows)

            await random_pause(2, 5)

        dedup = {}
        for r in all_rows:
            dedup[(r.get("sku"), r.get("subcat_url"))] = r
        out_rows = list(dedup.values())
        if not out_rows:
            print("[WARN] La corrida termino sin productos nuevos; se reutilizara el ultimo CSV no vacio.")
            out_rows = load_cached_product_rows(OUTPUT_DIR)
        if not out_rows:
            raise RuntimeError("No se obtuvieron productos frescos. El sitio pudo estar bloqueado o sin respuestas de productos.")


        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = OUTPUT_DIR / f"{OUT_PREFIX}_{ts}.csv"
        write_csv(out_rows, str(out_csv))

        print("\\nTotal filas:", len(out_rows))
        print("CSV generado:", out_csv)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
