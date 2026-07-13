import asyncio
import csv
import hashlib
import os
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from cached_subcategories import load_cached_product_rows, load_cached_subcategories


OUTPUT_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "output/higiene_cuidado_personal"))
BASE = "https://super.lider.cl"

HEADLESS = True
DEBUG = True
OUT_PREFIX = "lider_higiene_cuidado_personal"

HOME_URL = BASE
CATEGORY_NAME = "Higiene y Cuidado Personal"
CATEGORY_LANDING = f"{BASE}/browse/higiene-y-cuidado-personal"

BLOCK_PATTERNS = [
    "googletagservices.com",
    "googleadservices.com",
    "doubleclick.net",
    "pagead2.googlesyndication.com",
]

MAX_PAGES = 80
MAX_SCROLL_ROUNDS_PER_PAGE = 8
STOP_AFTER_CONSECUTIVE_NO_NEW_PAGES = 2

EXCLUDED_LINK_TEXTS = {
    "revisar todo",
    "revisar todo ",
    "ir a la categoria",
    "ir a la categoría",
}

TARGET_GROUPS = {
    "Protectores solares",
    "Cuidado Bucal",
    "Desodorantes y cuidado corporal",
    "Jabones",
    "Protección femenina",
    "Salud y suplementos",
    "Cuidado adulto mayor",
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


def clean_text(s: str) -> str:
    s = s or ""
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_text(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    url = re.sub(r"[?#].*$", "", url)
    return url.rstrip("/").lower()


def should_block(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in BLOCK_PATTERNS)


def make_stable_sku(detail_url: str, name: str, brand: str, image_url: str) -> str:
    detail_url = (detail_url or "").strip()

    patterns = [
        r"/ip/[^/]+/(\d+)",
        r"/p/[^/]+/(\d+)",
        r"[?&](?:sku|productId|itemId|id)=(\d+)",
        r"/(\d{6,})($|[/?#])",
    ]
    for pat in patterns:
        m = re.search(pat, detail_url)
        if m:
            return m.group(1)

    base = "||".join([
        clean_text(name).lower(),
        clean_text(brand).lower(),
        detail_url.lower(),
        image_url.lower(),
    ])
    return "hash_" + hashlib.md5(base.encode("utf-8")).hexdigest()[:16]


def row_quality_score(r: dict) -> int:
    return sum([
        bool(r.get("detail_url")),
        bool(r.get("image_url")),
        bool(r.get("name")),
        bool(r.get("brand")),
        r.get("price") is not None,
        r.get("list_price") is not None,
    ])


async def random_pause(a=0.8, b=2.0):
    await asyncio.sleep(random.uniform(a, b))


# =========================
# Context / Blocking
# =========================
async def install_blocking(context: BrowserContext):
    async def route_handler(route):
        if should_block(route.request.url):
            return await route.abort()
        return await route.continue_()

    await context.route("**/*", route_handler)


async def create_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        ignore_https_errors=True,
        locale="es-CL",
        viewport={"width": 1440, "height": 1200},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await install_blocking(context)
    return context


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
# Anti-bot
# =========================
async def is_blocked(page: Page) -> bool:
    try:
        url = page.url.lower()
    except Exception:
        url = ""

    try:
        title = (await page.title()).strip().lower()
    except Exception:
        title = ""

    try:
        body = (await page.locator("body").inner_text()).strip().lower()
    except Exception:
        body = ""

    markers = [
        "/blocked",
        "robot or human",
        "activate and hold the button",
        "confirm that you're human",
        "confirm that you’re human",
        "captcha",
        "are you human",
        "access denied",
    ]

    haystack = f"{url}\n{title}\n{body}"
    return any(m in haystack for m in markers)


# =========================
# Descubrir subcategorías desde mega menú
# =========================
async def discover_subcategories(browser: Browser) -> List[dict]:
    context = await create_context(browser)
    page = await context.new_page()

    async def safe_click(locator, timeout=4000):
        try:
            await locator.click(timeout=timeout)
            return True
        except Exception:
            return False

    async def safe_hover(locator, timeout=4000):
        try:
            await locator.hover(timeout=timeout)
            return True
        except Exception:
            return False

    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
        await dismiss_possible_popups(page)
        await page.wait_for_timeout(2500)

        if await is_blocked(page):
            raise RuntimeError("Home de Lider bloqueado por anti-bot")

        # 1) Abrir menú Categorías
        opened = False
        category_btn_selectors = [
            'button:has-text("Categorías")',
            'a:has-text("Categorías")',
            '[role="button"]:has-text("Categorías")',
            'text="Categorías"',
        ]

        for sel in category_btn_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    try:
                        if await loc.is_visible():
                            if await safe_click(loc):
                                opened = True
                                break
                    except Exception:
                        pass

                    try:
                        await loc.click(timeout=3000, force=True)
                        opened = True
                        break
                    except Exception:
                        pass
            except Exception:
                pass

        if not opened:
            raise RuntimeError("No se pudo abrir el menú de Categorías")

        await page.wait_for_timeout(1800)
        await dismiss_possible_popups(page)

        # 2) Activar Higiene y Cuidado Personal en la columna izquierda
        category_activated = False
        category_selectors = [
            'text="Higiene y Cuidado Personal"',
            'a:has-text("Higiene y Cuidado Personal")',
            'button:has-text("Higiene y Cuidado Personal")',
            '[role="menuitem"]:has-text("Higiene y Cuidado Personal")',
        ]

        for sel in category_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue

                try:
                    await safe_hover(loc)
                    await page.wait_for_timeout(1200)
                except Exception:
                    pass

                try:
                    await safe_click(loc)
                except Exception:
                    pass

                await page.wait_for_timeout(1500)

                body_text = (await page.locator("body").inner_text()).lower()
                if (
                    "protectores solares" in body_text
                    and "cuidado bucal" in body_text
                    and "protección femenina" in body_text
                ):
                    category_activated = True
                    break
            except Exception:
                pass

        if not category_activated:
            raise RuntimeError("No se pudo desplegar el mega menú de Higiene y Cuidado Personal")

        # 3) Extraer grupos y subcategorías hijas
        data = await page.evaluate(
            r"""
            () => {
                const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

                const abs = (href) => {
                    try {
                        return new URL(href, location.origin).href;
                    } catch(e) {
                        return href || "";
                    }
                };

                const excluded = new Set([
                    "revisar todo",
                    "ir a la categoria",
                    "ir a la categoría"
                ]);

                const targetGroups = new Set([
                    "Protectores solares",
                    "Cuidado Bucal",
                    "Desodorantes y cuidado corporal",
                    "Jabones",
                    "Protección femenina",
                    "Salud y suplementos",
                    "Cuidado adulto mayor"
                ]);

                const allNodes = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, h6, strong, p, span, div, a"));

                const visibleTextNodes = allNodes
                    .map(el => ({
                        el,
                        txt: clean(el.textContent || "")
                    }))
                    .filter(x => x.txt.length > 0);

                const groupNodes = visibleTextNodes.filter(x => targetGroups.has(x.txt));

                const results = [];
                const pushed = new Set();

                for (const g of groupNodes) {
                    const groupName = g.txt;

                    let container =
                        g.el.closest("section") ||
                        g.el.parentElement ||
                        g.el;

                    for (let i = 0; i < 2; i++) {
                        if (!container || !container.parentElement) break;

                        const linksCurrent = container.querySelectorAll("a[href]").length;
                        const linksParent = container.parentElement.querySelectorAll("a[href]").length;

                        if (linksParent > linksCurrent && linksCurrent <= 2) {
                            container = container.parentElement;
                        }
                    }

                    const links = Array.from(container.querySelectorAll("a[href]"))
                        .map(a => ({
                            name: clean(a.textContent || ""),
                            url: abs(a.getAttribute("href") || "")
                        }))
                        .filter(x => x.name && x.url)
                        .filter(x => !excluded.has(x.name.toLowerCase()));

                    for (const item of links) {
                        const key = `${groupName}||${item.name}||${item.url}`;
                        if (pushed.has(key)) continue;
                        pushed.add(key);

                        results.push({
                            group: groupName,
                            name: item.name,
                            url: item.url
                        });
                    }
                }

                return results;
            }
            """
        )

        out = []
        seen_urls = set()

        for x in data:
            group = clean_text(x.get("group") or "")
            name = clean_text(x.get("name") or "")
            url = (x.get("url") or "").strip()

            if not group or not name or not url:
                continue

            if group not in TARGET_GROUPS:
                continue

            if normalize_text(name) in EXCLUDED_LINK_TEXTS:
                continue

            url_norm = normalize_url(url)
            if url_norm in seen_urls:
                if DEBUG:
                    print(f"[DEBUG] Subcategoría duplicada omitida por URL: [{group}] {name} -> {url}")
                continue
            seen_urls.add(url_norm)

            out.append({
                "group": group,
                "name": name,
                "url": url,
            })

        if not out:
            if DEBUG:
                print("[DEBUG] No se pudieron leer subcategorías del mega menú. Se usará fallback con landing.")
            out = [
                {
                    "group": CATEGORY_NAME,
                    "name": CATEGORY_NAME,
                    "url": CATEGORY_LANDING,
                }
            ]

        if DEBUG:
            print("\n[DEBUG] Subcategorías finales detectadas:")
            for x in out:
                print(f" - [{x['group']}] {x['name']} -> {x['url']}")

        return out

    finally:
        await page.close()
        await context.close()


# =========================
# Extracción DOM
# =========================
async def extract_products_from_dom(page: Page) -> List[dict]:
    raw = await page.evaluate(
        r"""
        () => {
            const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

            const abs = (href) => {
                try {
                    return new URL(href, location.origin).href;
                } catch(e) {
                    return href || "";
                }
            };

            const anchors = Array.from(document.querySelectorAll('a[href*="/ip/"], a[href*="/p/"]'));
            const rows = [];
            const seen = new Set();

            for (const a of anchors) {
                const detail_url = abs(a.getAttribute("href") || "");
                if (!detail_url || seen.has(detail_url)) continue;
                seen.add(detail_url);

                const card =
                    a.closest('article') ||
                    a.closest('[data-testid*="product"]') ||
                    a.closest('li') ||
                    a.parentElement;

                if (!card) continue;

                const cardText = clean(card.innerText || card.textContent || "");
                if (!cardText) continue;

                const img = card.querySelector("img");
                const image_url = img ? (img.getAttribute("src") || img.getAttribute("data-src") || "") : "";
                const img_alt = img ? clean(img.getAttribute("alt") || "") : "";

                let name = clean(a.innerText || a.textContent || "");
                if (!name || name.length < 4) name = img_alt;

                const matches = [...cardText.matchAll(/\$\s?([\d\.]+)/g)].map(m => m[1]);
                const prices = matches.map(x => x.replace(/\./g, "")).filter(Boolean);

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

                let brand = "";
                const lines = cardText
                    .split(/\n|  +/)
                    .map(x => clean(x))
                    .filter(Boolean);

                const ignore = new Set([
                    "Agregar", "Rebaja", "Más relevantes", "Precio", "Marca", "Categoría"
                ]);

                const filtered = lines.filter(x => {
                    if (ignore.has(x)) return false;
                    if (/^\$/.test(x)) return false;
                    if (/precio actual/i.test(x)) return false;
                    if (/ahorra/i.test(x)) return false;
                    if (/costaba/i.test(x)) return false;
                    return true;
                });

                if ((!name || name.length < 4) && filtered.length) {
                    name = filtered[0];
                }

                if (filtered.length >= 2) {
                    brand = filtered[filtered.length - 2] || "";
                }

                if (!name || name.length < 4) continue;

                rows.push({
                    detail_url,
                    image_url,
                    name,
                    brand,
                    price,
                    list_price,
                    raw_text: cardText
                });
            }

            return rows;
        }
        """
    )

    out = []
    for r in raw:
        detail_url = (r.get("detail_url") or "").strip()
        image_url = (r.get("image_url") or "").strip()
        name = clean_text(r.get("name") or "")
        brand = clean_text(r.get("brand") or "")
        price = to_int_clp(r.get("price"))
        list_price = to_int_clp(r.get("list_price"))

        if not name:
            continue

        sku = make_stable_sku(detail_url, name, brand, image_url)

        out.append(
            {
                "sku": sku,
                "name": name[:250],
                "brand": brand[:120],
                "price": price,
                "list_price": list_price,
                "in_offer": (price is not None and list_price is not None and price < list_price),
                "detail_url": detail_url,
                "image_url": image_url,
            }
        )

    dedup = {}
    for x in out:
        sku = x["sku"]
        if sku not in dedup or row_quality_score(x) > row_quality_score(dedup[sku]):
            dedup[sku] = x
    return list(dedup.values())


async def get_dom_signature(page: Page) -> str:
    try:
        items = await extract_products_from_dom(page)
        sig = "||".join(sorted((x.get("sku") or "") for x in items[:20]))
        return sig
    except Exception:
        return ""


async def progressive_scroll(page: Page):
    for i in range(MAX_SCROLL_ROUNDS_PER_PAGE):
        try:
            count = await page.locator('a[href*="/ip/"], a[href*="/p/"]').count()
        except Exception:
            count = -1

        try:
            await page.mouse.wheel(0, random.randint(1200, 2600))
        except Exception:
            pass

        try:
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
        except Exception:
            pass

        await page.wait_for_timeout(random.randint(1200, 2200))

        if DEBUG:
            print(f"      scroll round {i+1}: anchors={count}")

    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1800)
    except Exception:
        pass


# =========================
# Paginación DOM real
# =========================
async def click_next_page(page: Page, target_page_num: int) -> bool:
    current_sig = await get_dom_signature(page)

    candidate_selectors = [
        f'a[aria-label="{target_page_num}"]',
        f'button[aria-label="{target_page_num}"]',
        f'text="{target_page_num}"',
    ]

    for sel in candidate_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=2500)
                await page.wait_for_timeout(2500)

                for _ in range(8):
                    new_sig = await get_dom_signature(page)
                    if new_sig and new_sig != current_sig:
                        return True
                    await page.wait_for_timeout(800)

                return True
        except Exception:
            pass

    js_clicked = await page.evaluate(
        """
        (targetPageNum) => {
            const clean = (s) => (s || "").replace(/\\s+/g, " ").trim();

            const nodes = Array.from(document.querySelectorAll("a, button, span, div"));
            for (const el of nodes) {
                const txt = clean(el.textContent || "");
                if (txt === String(targetPageNum)) {
                    try {
                        el.click();
                        return true;
                    } catch(e) {}
                }
            }

            const nextCandidates = Array.from(document.querySelectorAll("a, button"));
            for (const el of nextCandidates) {
                const txt = clean(el.textContent || "").toLowerCase();
                const aria = clean(el.getAttribute("aria-label") || "").toLowerCase();
                if (
                    txt.includes("siguiente") ||
                    txt === ">" ||
                    txt === "›" ||
                    txt === "»" ||
                    aria.includes("siguiente") ||
                    aria.includes("next")
                ) {
                    try {
                        el.click();
                        return true;
                    } catch(e) {}
                }
            }

            return false;
        }
        """,
        target_page_num,
    )

    if js_clicked:
        await page.wait_for_timeout(2500)
        for _ in range(8):
            new_sig = await get_dom_signature(page)
            if new_sig and new_sig != current_sig:
                return True
            await page.wait_for_timeout(800)
        return True

    return False


# =========================
# Scrape subcategoría
# =========================
async def scrape_subcategory(browser: Browser, group: str, name: str, url: str) -> Tuple[List[dict], bool]:
    context = await create_context(browser)
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await dismiss_possible_popups(page)
        await page.wait_for_timeout(2500)

        if await is_blocked(page):
            if DEBUG:
                print(f"[BLOCKED] [{group}] {name} -> {page.url}")
            return [], True

        all_rows: List[dict] = []
        seen_skus = set()
        consecutive_no_new_pages = 0

        for page_num in range(1, MAX_PAGES + 1):
            if DEBUG:
                print(f"    page {page_num}: procesando DOM")

            await progressive_scroll(page)
            rows = await extract_products_from_dom(page)

            new_count = 0
            for r in rows:
                sku = r.get("sku")
                if not sku:
                    continue

                if sku not in seen_skus:
                    seen_skus.add(sku)
                    rr = dict(r)
                    rr.update(
                        {
                            "subcat_name": f"{group} > {name}",
                            "subcat_url": page.url,
                            "source_json_url": "",
                            "page_num": page_num,
                            "extracted_at": now_iso(),
                        }
                    )
                    all_rows.append(rr)
                    new_count += 1

            sample_skus = [r.get("sku") for r in rows[:10]]
            print(f"    page {page_num}: visibles={len(rows)}, nuevos={new_count}, acumulados={len(all_rows)}")
            if DEBUG:
                print(f"    page {page_num}: sample_skus={sample_skus}")

            if new_count == 0:
                consecutive_no_new_pages += 1
            else:
                consecutive_no_new_pages = 0

            if consecutive_no_new_pages >= STOP_AFTER_CONSECUTIVE_NO_NEW_PAGES:
                if DEBUG:
                    print(f"    stop: {consecutive_no_new_pages} páginas seguidas sin nuevos productos")
                break

            if page_num >= MAX_PAGES:
                break

            moved = await click_next_page(page, page_num + 1)

            if not moved:
                if DEBUG:
                    print(f"    page {page_num}: no se pudo avanzar al paginador siguiente")
                break

            await page.wait_for_timeout(2200)
            await dismiss_possible_popups(page)

            if await is_blocked(page):
                if DEBUG:
                    print(f"[BLOCKED] [{group}] {name} después de paginar -> {page.url}")
                return all_rows, True

            await random_pause(1.2, 2.2)

        return all_rows, False

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
        browser = await p.chromium.launch(
            channel="chrome",
            headless=HEADLESS,
            slow_mo=0
        )

        try:
            subcats = await discover_subcategories(browser)
        except Exception as exc:
            print(f"[WARN] No se pudieron descubrir subcategorías online: {exc}")
            subcats = load_cached_subcategories(OUTPUT_DIR, CATEGORY_NAME, globals().get("CATEGORY_LANDING"))
            print(f"[WARN] Usando {len(subcats)} subcategorías cacheadas desde {OUTPUT_DIR}")

        if not subcats:
            raise RuntimeError("No se pudieron descubrir subcategorías para Higiene y Cuidado Personal")

        all_rows: List[dict] = []
        blocked_count = 0

        for idx, sc in enumerate(subcats, start=1):
            print(f"\n[{idx}/{len(subcats)}] Scrape: [{sc['group']}] {sc['name']}")

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
                    print("\nDemasiados bloqueos consecutivos. Se detiene el scraping.")
                    break
                await random_pause(8, 15)
                continue

            blocked_count = 0
            print("  productos acumulados subcategoría:", len(rows))
            all_rows.extend(rows)

            await random_pause(2, 4)

        # Deduplicación global final por SKU
        dedup = {}
        for r in all_rows:
            sku = r.get("sku")
            if not sku:
                continue

            if sku not in dedup:
                dedup[sku] = r
            else:
                old = dedup[sku]
                if row_quality_score(r) > row_quality_score(old):
                    dedup[sku] = r

        out_rows = list(dedup.values())
        if not out_rows:
            print("[WARN] La corrida termino sin productos nuevos; se reutilizara el ultimo CSV no vacio.")
            out_rows = load_cached_product_rows(OUTPUT_DIR)


        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_csv = OUTPUT_DIR / f"{OUT_PREFIX}_{ts}.csv"
        write_csv(out_rows, str(out_csv))

        print("\nTotal filas:", len(out_rows))
        print("CSV generado:", out_csv)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
