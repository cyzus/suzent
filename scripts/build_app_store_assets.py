"""Frame simulator captures as App Store screenshots with bilingual captions.

Also composes the product page header (21:9) and search results (3:2) artwork
from the same iPhone captures.

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
            "Chats, projects and Regent from your computer.",
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
        ("一周的事，\n一处看清。", "对话、项目和 Regent，从电脑同步过来。"),
        ("扫一扫，\n就连上。", "在电脑的“设置 → 设备”中扫码。"),
        ("Regent，\n替你盯着。", "常驻智能体，只提醒需要你处理的事。"),
    ],
}
BANNERS = {
    "en": (
        "Your agent.\nYour rules.",
        "A personal AI agent that runs on your computer, now in your pocket.",
    ),
    "zh-Hans": (
        "你的智能体，\n你的规则。",
        "运行在你电脑上的个人 AI 智能体，\n现在装进口袋。",
    ),
}
ARTWORK = (
    ROOT.parents[1]
    / "apps/android/app/src/main/res/drawable-nodpi/suzent_launcher_artwork.png"
)
# The Play feature graphic's layout: copy on the left, approval and plan
# captures tilted on the right, the hand-held cube between them. Positions are
# (left, top, width) in pixels.
PLACEMENTS = {
    "header": {
        "size": (3840, 1646),
        "copy": (420, 170, 1300),
        "headline": 220,
        "phones": [(2930, 130, 600, 4), (2280, 250, 600, -3)],
        "cube": (1560, 840, 700),
    },
    "search": {
        "size": (3840, 2560),
        "copy": (260, 220, 1560),
        "headline": 260,
        "phones": [(2940, 260, 780, 4), (2080, 420, 780, -3)],
        "cube": (980, 1500, 1000),
    },
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
                        main{{width:{width}px;height:{height}px;position:relative;overflow:hidden}}
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
        artwork = base64.b64encode(ARTWORK.read_bytes()).decode()
        for placement, spec in PLACEMENTS.items():
            width, height = spec["size"]
            left, top, copy_width = spec["copy"]
            size = spec["headline"]
            page = await browser.new_page(viewport={"width": width, "height": height})
            for locale, (headline, description) in BANNERS.items():
                phones = "".join(
                    f'<img class="phone" style="left:{x}px;top:{y}px;width:{w}px;transform:rotate({angle}deg)" '
                    'src="data:image/png;base64,'
                    + base64.b64encode(
                        (ROOT / "raw" / locale / f"iphone-{shot:02d}.png").read_bytes()
                    ).decode()
                    + '">'
                    for shot, (x, y, w, angle) in zip((1, 2), spec["phones"])
                )
                cube_left, cube_top, cube_width = spec["cube"]
                title = "<br>".join(escape(line) for line in headline.splitlines())
                await page.set_content(f'''<!doctype html><html lang="{locale}"><meta charset="utf-8"><style>
                    *{{box-sizing:border-box}}body{{margin:0;background:white;color:#050505}}
                    main{{width:{width}px;height:{height}px;position:relative;overflow:hidden}}
                    header{{font:bold {size * 0.32:.0f}px Georgia,serif;letter-spacing:.08em;margin-bottom:{size * 0.75:.0f}px}}
                    header span{{font:{size * 0.17:.0f}px Menlo,monospace;letter-spacing:.15em}}
                    .copy{{position:absolute;left:{left}px;top:{top}px;width:{copy_width}px}}
                    h1{{font-family:Georgia,'Songti SC',serif;font-size:{size}px;font-weight:700;line-height:1.02;letter-spacing:-.04em;margin:0 0 {size * 0.22:.0f}px}}
                    p{{font-family:Arial,'PingFang SC',sans-serif;font-size:{size * 0.34:.0f}px;line-height:1.4;margin:0;color:#333}}
                    .phone{{position:absolute;border:12px solid black;box-shadow:36px 36px 0 black;border-radius:8px;background:white}}
                    .cube{{position:absolute;left:{cube_left}px;top:{cube_top}px;width:{cube_width}px;mix-blend-mode:multiply;filter:brightness(1.08) contrast(1.04)}}
                    </style><main><div class="copy"><header>SUZENT <span>/ MOBILE</span></header>
                    <h1>{title}</h1><p>{"<br>".join(escape(line) for line in description.splitlines())}</p></div>{phones}
                    <img class="cube" src="data:image/png;base64,{artwork}"></main></html>''')
                for image in await page.locator("img").all():
                    await image.evaluate("image => image.decode()")
                await page.evaluate("document.fonts.ready")
                await page.screenshot(path=str(ROOT / locale / f"{placement}.png"))
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
