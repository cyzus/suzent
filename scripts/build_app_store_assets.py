"""Frame simulator captures as App Store screenshots with bilingual captions.

Raw captures come from the offline demo; see docs/assets/app-store/README.md.
"""

import asyncio
import base64
from html import escape
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1] / "store-upload/app-store"
DEVICES = {
    "iphone": {"size": (1206, 2622), "shot": 860, "top": 640, "headline": 104},
    "ipad": {"size": (2064, 2752), "shot": 1500, "top": 600, "headline": 124},
}
CAPTIONS = {
    "en": [
        (
            "Plans built\naround you.",
            "Suzent remembers your preferences and cites its sources.",
        ),
        (
            "Nothing happens\nwithout your OK.",
            "Approve or reject actions on your computer from your phone.",
        ),
        (
            "Your whole week,\nin one place.",
            "Projects, notes and scheduled tasks from your computer.",
        ),
        (
            "Pair with\none QR code.",
            "Scan it from Settings → Devices on your computer.",
        ),
        ("Regent keeps\nwatch.", "Your always-on agent flags only what needs you."),
    ],
    "zh-Hans": [
        ("按你的习惯，\n安排好一切。", "记得你的偏好，并附上信息来源。"),
        ("你点头，\n它才动手。", "在手机上批准或拒绝电脑上的操作。"),
        ("一周的事，\n一处看清。", "项目、笔记和定时任务，从电脑同步过来。"),
        ("扫一扫，\n就连上。", "在电脑的“设置 → 设备”中扫码。"),
        ("Regent，\n替你盯着。", "常驻智能体，只提醒需要你处理的事。"),
    ],
}
REQUIREMENT = {
    "en": "Requires Suzent on your computer",
    "zh-Hans": "需配合电脑上的 Suzent 使用",
}


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for device, spec in DEVICES.items():
            width, height = spec["size"]
            page = await browser.new_page(viewport={"width": width, "height": height})
            for locale, captions in CAPTIONS.items():
                (ROOT / locale).mkdir(parents=True, exist_ok=True)
                for index, (headline, description) in enumerate(captions, 1):
                    name = f"{device}-{index:02d}.png"
                    data = base64.b64encode(
                        (ROOT / "raw" / locale / name).read_bytes()
                    ).decode()
                    title = "<br>".join(escape(line) for line in headline.splitlines())
                    await page.set_content(f'''<!doctype html><html lang="{locale}"><meta charset="utf-8"><style>
                        *{{box-sizing:border-box}}body{{margin:0;background:white;color:#050505}}
                        main{{width:{width}px;height:{height}px;position:relative;overflow:hidden;border:6px solid black}}
                        header{{position:absolute;top:70px;left:84px;font:bold 40px Georgia,serif;letter-spacing:.08em}}
                        header span{{font:22px Menlo,monospace;letter-spacing:.15em}}
                        .copy{{position:absolute;left:84px;right:84px;top:170px}}
                        h1{{font-family:Georgia,'Songti SC',serif;font-size:{spec["headline"]}px;font-weight:700;line-height:1.05;letter-spacing:-.04em;margin:0 0 28px}}
                        p{{font-family:Arial,'PingFang SC',sans-serif;font-size:{spec["headline"] * 0.4:.0f}px;line-height:1.4;margin:0;color:#333}}
                        .shot{{position:absolute;left:50%;top:{spec["top"]}px;width:{spec["shot"]}px;transform:translateX(-50%);
                              border:5px solid black;box-shadow:16px 16px 0 black;border-radius:4px;background:white}}
                        .shot img{{display:block;width:100%}}
                        footer{{position:absolute;left:84px;right:84px;bottom:56px;display:flex;justify-content:space-between;font:22px Menlo,monospace;letter-spacing:.06em}}
                        </style><main><header>SUZENT <span>/ MOBILE</span></header>
                        <div class="copy"><h1>{title}</h1><p>{escape(description)}</p></div>
                        <div class="shot"><img src="data:image/png;base64,{data}"></div>
                        <footer><span>{REQUIREMENT[locale]}</span><span>{index:02d} / 05</span></footer></main></html>''')
                    await page.locator("img").evaluate("image => image.decode()")
                    await page.evaluate("document.fonts.ready")
                    await page.screenshot(path=str(ROOT / locale / name))
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
