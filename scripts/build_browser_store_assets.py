"""Render store artwork and real BrowserTab components with sanitized fixture data.

Run with the frontend dev server at http://127.0.0.1:18182:
    uv run --no-sync python scripts/build_browser_store_assets.py
"""

import asyncio
import base64
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/assets/browser-store"
OUTPUT = ROOT / "store-upload/listing-assets"
EXTENSION = ROOT / "extensions/browser"


def image_url(path: Path, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


async def main() -> None:
    for folder in ("logos", "en", "zh-CN"):
        (OUTPUT / folder).mkdir(parents=True, exist_ok=True)
    logo = image_url(ROOT / "frontend/public/favicon.svg", "image/svg+xml")
    art = image_url(SOURCE / "artwork/browser-occult.png")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(device_scale_factor=1)
        for size in (16, 32, 48, 128, 300):
            await page.set_viewport_size({"width": size, "height": size})
            inset = 16 if size == 128 else 0
            await page.set_content(
                f'<style>body{{margin:0;background:transparent}}img{{display:block;margin:{inset}px;width:{size - 2 * inset}px;height:{size - 2 * inset}px}}</style><img src="{logo}">'
            )
            await page.locator("img").evaluate("image => image.decode()")
            target = OUTPUT / "logos" / f"icon-{size}.png"
            await page.screenshot(path=str(target), omit_background=True)
            if size != 300:
                (EXTENSION / "icons" / target.name).write_bytes(target.read_bytes())
        for width, height, name in (
            (440, 280, "promo-small.png"),
            (1400, 560, "promo-marquee.png"),
        ):
            await page.set_viewport_size({"width": width, "height": height})
            large = width > 500
            await page.set_content(f'''<style>
                *{{box-sizing:border-box}}body{{margin:0;background:white;color:black}}
                main{{height:{height}px;position:relative;overflow:hidden;border:2px solid #000}}
                .brand{{position:absolute;left:{54 if large else 22}px;top:{126 if large else 34}px;z-index:1}}
                h1{{font-family:Georgia,'Times New Roman',serif;font-size:{112 if large else 48}px;line-height:.9;letter-spacing:-.065em;margin:0;font-weight:900}}
                h1 span{{display:block;font-family:monospace;font-size:{21 if large else 12}px;letter-spacing:.3em;margin-top:{25 if large else 13}px}}
                .art{{position:absolute;width:{850 if large else 420}px;height:auto;right:{0 if large else -78}px;bottom:{-5 if large else -10}px}}
                </style><main><img class="art" src="{art}"><div class="brand"><h1>SUZENT<span>BROWSER</span></h1></div></main>''')
            await page.locator("img").evaluate_all(
                "images => Promise.all(images.map(image => image.decode()))"
            )
            await page.screenshot(path=str(OUTPUT / name))
        await page.close()
        for locale in ("en", "zh-CN"):
            for connected in (False, True):
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.add_init_script(
                    f"localStorage.setItem('suzent.locale', {json.dumps(locale)})"
                )
                await page.route(
                    "**/browser/settings",
                    lambda route: route.fulfill(
                        json={
                            "settings": {
                                "connection_mode": "extension",
                                "channel": "msedge",
                                "persistent": True,
                                "headless": False,
                            },
                            "available_browsers": {
                                "chromium": True,
                                "chrome": True,
                                "msedge": True,
                            },
                            "environment_overrides": [],
                        }
                    ),
                )
                await page.route(
                    "**/browser/extension",
                    lambda route: route.fulfill(
                        json={
                            "connected": connected,
                            "source_dir": "C:\\Suzent\\extensions\\browser",
                        }
                    ),
                )
                await page.goto("http://127.0.0.1:18182/browser-store-preview.html")
                await page.locator(
                    "input[readonly]" if not connected else "details"
                ).wait_for()
                if connected:
                    await page.get_by_role(
                        "button",
                        name="Disconnect and forget"
                        if locale == "en"
                        else "断开并忘记连接",
                        exact=True,
                    ).wait_for()
                await page.evaluate("document.fonts.ready")
                await page.screenshot(
                    path=str(
                        OUTPUT
                        / locale
                        / ("02-connected.png" if connected else "01-setup.png")
                    )
                )
                assert await page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight"
                )
                await page.close()
        await browser.close()


if __name__ == "__main__":
    html = ROOT / "frontend/browser-store-preview.html"
    entry = ROOT / "frontend/browser-store-preview.tsx"
    if html.exists() or entry.exists():
        raise FileExistsError(
            "Remove existing browser-store-preview files before rendering"
        )
    try:
        html.write_text(
            '<html><body><div id="root"></div><script type="module" src="/browser-store-preview.tsx"></script></body></html>',
            encoding="utf-8",
        )
        entry.write_text(
            (SOURCE / "preview.tsx")
            .read_text(encoding="utf-8")
            .replace("../../../frontend/", "./"),
            encoding="utf-8",
        )
        asyncio.run(main())
    finally:
        html.unlink(missing_ok=True)
        entry.unlink(missing_ok=True)
