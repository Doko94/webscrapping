import asyncio
import os


def manual_challenge_enabled() -> bool:
    return os.getenv("LIDER_MANUAL_CHALLENGE", "0").strip().lower() in {"1", "true", "yes", "si"}


async def _looks_blocked(page) -> bool:
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
    return any(marker in f"{url}\n{title}\n{body}" for marker in markers)


async def wait_for_manual_unblock(page, label: str = "", timeout_seconds: int = 180) -> bool:
    if not manual_challenge_enabled():
        return False

    print("\n[MANUAL] Lider pidió verificación humana.")
    if label:
        print(f"[MANUAL] Contexto: {label}")
    print("[MANUAL] Resuelve la verificación en la ventana de Chrome. El scraper esperará hasta 180s.")

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if not await _looks_blocked(page):
            print("[MANUAL] Verificación completada. Continúo scraping.")
            return True
        await page.wait_for_timeout(3000)

    print("[MANUAL] No se completó la verificación dentro del tiempo de espera.")
    return False
