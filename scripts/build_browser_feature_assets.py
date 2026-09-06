"""Export bilingual feature illustrations without requiring a frontend server."""

import asyncio
import base64
from html import escape
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1] / "docs/assets/browser-store"
OUTPUT = Path(__file__).resolve().parents[1] / "store-upload/listing-assets"
FEATURES = [
    (
        "03-your-tabs",
        "gesture-point.png",
        {
            "en": (
                "Your tabs.\nYour familiar.",
                "Use your existing tabs and signed-in sessions.",
            ),
            "zh-CN": ("熟悉的标签，\n熟悉的伙伴。", "直接使用已有标签页和登录状态。"),
        },
    ),
    (
        "04-live-preview",
        "gesture-reveal.png",
        {
            "en": (
                "Follow the\nselected tab.",
                "Watch browser actions in Suzent’s live preview.",
            ),
            "zh-CN": ("所选标签，\n尽在眼前。", "通过 Suzent 实时预览查看浏览器操作。"),
        },
    ),
    (
        "05-your-control",
        "gesture-stop.png",
        {
            "en": (
                "Your browser.\nYour call.",
                "Disconnect anytime. Your tabs stay open.",
            ),
            "zh-CN": ("你的浏览器，\n由你掌控。", "随时断开连接，标签页保持打开。"),
        },
    ),
]


async def main() -> None:
    for locale in ("en", "zh-CN"):
        (OUTPUT / locale).mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        for index, (name, art, translations) in enumerate(FEATURES, 1):
            data = base64.b64encode((ROOT / "artwork" / art).read_bytes()).decode()
            for locale, (headline, description) in translations.items():
                title = "<br>".join(escape(line) for line in headline.splitlines())
                requirement = (
                    "Requires the Suzent app"
                    if locale == "en"
                    else "需配合 Suzent 应用使用"
                )
                await page.set_content(f'''<!doctype html><html lang="{locale}"><meta charset="utf-8"><style>
                    *{{box-sizing:border-box}}body{{margin:0;background:white;color:#050505}}
                    main{{width:1280px;height:800px;position:relative;overflow:hidden;border:2px solid black}}
                    .art{{position:absolute;width:1100px;height:auto;right:-20px;top:30px}}
                    header{{position:absolute;top:56px;left:58px;font:bold 23px Georgia,serif;letter-spacing:.08em}}
                    .copy{{position:absolute;left:58px;top:264px;width:460px}}
                    h1{{font-family:Georgia,'SimSun',serif;font-size:{64 if locale == "en" else 57}px;font-weight:700;line-height:1.08;letter-spacing:-.05em;margin:0 0 25px}}
                    p{{font-family:Arial,'Microsoft YaHei',sans-serif;font-size:21px;line-height:1.5;max-width:360px;margin:0}}
                    footer{{position:absolute;left:58px;right:58px;bottom:43px;display:flex;justify-content:space-between;align-items:center;font:12px monospace;letter-spacing:.06em}}
                    </style><main><img class="art" src="data:image/png;base64,{data}"><header>SUZENT <span style="font:12px monospace;letter-spacing:.15em">/ BROWSER</span></header><div class="copy"><h1>{title}</h1><p>{escape(description)}</p></div><footer><span>{requirement}</span><span>0{index} / 03</span></footer></main></html>''')
                await page.locator("img").evaluate("image => image.decode()")
                await page.evaluate("document.fonts.ready")
                await page.screenshot(path=str(OUTPUT / locale / f"{name}.png"))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
