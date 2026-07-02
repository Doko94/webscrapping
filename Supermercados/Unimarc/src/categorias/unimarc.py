# import asyncio
# import csv
# import json
# import re
# from datetime import datetime
# from urllib.parse import urlparse
# from playwright.async_api import async_playwright

# CATEGORY_URL = "https://www.unimarc.cl/category/carnes/vacuno/vacuno-premium"

# # ---------------------------
# # Extractor
# # ---------------------------
# def to_int_clp(x):
#     if x is None:
#         return None
#     if isinstance(x, (int, float)):
#         return int(x)
#     s = re.sub(r"[^\d]", "", str(x))
#     return int(s) if s else None

# def walk(obj):
#     if isinstance(obj, dict):
#         yield obj
#         for v in obj.values():
#             yield from walk(v)
#     elif isinstance(obj, list):
#         for it in obj:
#             yield from walk(it)

# def is_product_dict(d: dict) -> bool:
#     return (
#         isinstance(d, dict)
#         and (d.get("sku") or d.get("itemId") or d.get("productId"))
#         and (d.get("nameComplete") or d.get("name"))
#         and isinstance(d.get("sellers"), list)
#         and len(d["sellers"]) > 0
#     )

# def extract_products(data):
#     products = {}
#     for d in walk(data):
#         if not is_product_dict(d):
#             continue

#         sku = str(d.get("sku") or d.get("itemId") or d.get("productId")).strip()
#         name = (d.get("nameComplete") or d.get("name") or "").strip()

#         seller0 = d["sellers"][0] if d.get("sellers") else {}
#         price = to_int_clp(seller0.get("price"))
#         list_price = to_int_clp(seller0.get("listPrice") or seller0.get("priceWithoutDiscount"))
#         in_offer = bool(seller0.get("inOffer"))
#         saving_txt = seller0.get("saving") or ""

#         promo = d.get("promotion") or {}
#         promo_price = to_int_clp(promo.get("price")) if isinstance(promo, dict) else None
#         if price is None and promo_price:
#             price = promo_price

#         discount_price = price if in_offer else None

#         img = None
#         imgs = d.get("images")
#         if isinstance(imgs, list) and imgs:
#             if isinstance(imgs[0], str):
#                 img = imgs[0]
#             elif isinstance(imgs[0], dict):
#                 img = imgs[0].get("url") or imgs[0].get("imageUrl")

#         detail = d.get("detailUrl") or d.get("url") or d.get("link") or d.get("slug") or ""
#         if detail and detail.startswith("/"):
#             detail_url = "https://www.unimarc.cl" + detail
#         else:
#             detail_url = detail

#         products[sku] = {
#             "sku": sku,
#             "name": name,
#             "brand": (d.get("brand") or "").strip(),
#             "net_content": (d.get("netContentLevelSmall") or d.get("netContent") or "").strip(),
#             "unit": (d.get("measurementUnitUn") or d.get("measurementUnit") or "").strip(),
#             "price": price,
#             "list_price": list_price,
#             "discount_price": discount_price,
#             "in_offer": in_offer,
#             "saving_text": saving_txt,
#             "ppum": seller0.get("ppum") or "",
#             "ppum_list_price": seller0.get("ppumListPrice") or "",
#             "detail_url": detail_url,
#             "image_url": img,
#             "extracted_at": datetime.now().isoformat(timespec="seconds"),
#         }

#     return list(products.values())

# # ---------------------------
# # Paginación
# # ---------------------------
# def category_slug_from_url(url: str) -> str:
#     path = urlparse(url).path.rstrip("/")
#     return path.split("/")[-1]  # vacuno-premium

# def page_url(base_url: str, page_num: int) -> str:
#     if page_num <= 1:
#         return base_url
#     return f"{base_url}?page={page_num}"

# async def capture_next_data_around(page, action_coro, slug: str, page_num: int, timeout_ms=120000):
#     """
#     Captura el JSON /_next/data/ asociado a la acción (goto/click).
#     Para páginas > 1, exigimos que el JSON contenga page=<n>.
#     """
#     def predicate(r):
#         ok = ("/_next/data/" in r.url) and (f"{slug}.json" in r.url)
#         if not ok:
#             return False
#         if page_num > 1:
#             return f"page={page_num}" in r.url
#         return True

#     async with page.expect_response(predicate, timeout=timeout_ms) as resp_info:
#         await action_coro

#     resp = await resp_info.value
#     data = await resp.json()
#     return resp.url, resp.status, data

# async def click_page_number(page, next_page: int):
#     locator = page.locator(f"a[href*='page={next_page}']").first
#     if await locator.count() == 0:
#         return False
#     await locator.scroll_into_view_if_needed()
#     await locator.click()
#     return True

# # ---------------------------
# # Main (AUTO)
# # ---------------------------
# async def main():
#     slug = category_slug_from_url(CATEGORY_URL)

#     async with async_playwright() as p:
#         # ✅ headless=True: no abre ventana
#         browser = await p.chromium.launch(channel="chrome", headless=True)

#         context = await browser.new_context(
#             ignore_https_errors=True,
#             locale="es-CL",
#             user_agent=(
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/120.0.0.0 Safari/537.36"
#             ),
#         )
#         page = await context.new_page()

#         all_by_sku = {}
#         page_num = 1
#         MAX_PAGES = 50

#         # -------- Page 1 --------
#         url_json, status, data = await capture_next_data_around(
#             page,
#             page.goto(page_url(CATEGORY_URL, page_num), wait_until="domcontentloaded", timeout=120000),
#             slug=slug,
#             page_num=page_num,
#             timeout_ms=120000
#         )
#         print(f"[page {page_num}] json: {url_json} status: {status}")

#         items = extract_products(data)
#         print(f"[page {page_num}] productos: {len(items)}")
#         for it in items:
#             all_by_sku[it["sku"]] = it

#         # -------- Next pages --------
#         while page_num < MAX_PAGES:
#             next_page = page_num + 1

#             # Si no existe el link, terminamos
#             if await page.locator(f"a[href*='page={next_page}']").count() == 0:
#                 break

#             url_json, status, data = await capture_next_data_around(
#                 page,
#                 click_page_number(page, next_page),
#                 slug=slug,
#                 page_num=next_page,
#                 timeout_ms=120000
#             )
#             page_num = next_page
#             print(f"[page {page_num}] json: {url_json} status: {status}")

#             items = extract_products(data)
#             print(f"[page {page_num}] productos: {len(items)}")

#             before = len(all_by_sku)
#             for it in items:
#                 all_by_sku[it["sku"]] = it
#             after = len(all_by_sku)

#             # Si no hay nada nuevo, detenemos
#             if after == before:
#                 break

#         # -------- Export --------
#         out_items = list(all_by_sku.values())
#         print("Total productos únicos:", len(out_items))

#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         out_csv = f"unimarc_{slug}_all_pages_{timestamp}.csv"

#         if out_items:
#             with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
#                 w = csv.DictWriter(f, fieldnames=list(out_items[0].keys()))
#                 w.writeheader()
#                 w.writerows(out_items)

#         print("CSV generado:", out_csv)

#         await browser.close()

# if __name__ == "__main__":
#     asyncio.run(main())