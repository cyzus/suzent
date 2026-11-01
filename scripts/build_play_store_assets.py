"""Build Google Play listing graphics: icon, feature graphics and phone screenshots.

Raw phone captures come from the Android offline demo; see
docs/assets/play-store/README.md. Captions are shared with the App Store kit.
"""

import asyncio
import base64
from html import escape
from pathlib import Path

from playwright.async_api import Page, async_playwright

from build_app_store_assets import CAPTIONS, REQUIREMENT

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "store-upload/play-store"
ARTWORK = (
    REPO / "apps/android/app/src/main/res/drawable-nodpi/suzent_launcher_artwork.png"
)
LOCALES = {"en-US": "en", "zh-CN": "zh-Hans"}
TAGLINE = {
    "en-US": (
        "Your AI agent,\nin your pocket.",
        "Runs on your computer. Answers to you.",
    ),
    "zh-CN": ("把你的 AI 智能体，\n装进口袋。", "运行在你的电脑上，只听你的。"),
}
PHONE = (1080, 1920)
STYLE = """*{box-sizing:border-box}body{margin:0;background:white;color:#050505}
main{position:relative;overflow:hidden;background:white}
header{font:bold 34px Georgia,serif;letter-spacing:.08em}header span{font:19px Menlo,monospace;letter-spacing:.15em}
h1{font-family:Georgia,'Songti SC',serif;font-weight:700;line-height:1.05;letter-spacing:-.04em;margin:0}
p{font-family:Arial,'PingFang SC',sans-serif;line-height:1.4;margin:0;color:#333}"""


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def lines(text: str) -> str:
    return "<br>".join(escape(line) for line in text.splitlines())


async def render(
    page: Page, html: str, size: tuple[int, int], out: Path, **options
) -> None:
    await page.set_viewport_size({"width": size[0], "height": size[1]})
    await page.set_content(
        f'<!doctype html><meta charset="utf-8"><style>{STYLE}</style>{html}'
    )
    await page.evaluate("Promise.all([...document.images].map(i => i.decode()))")
    await page.evaluate("document.fonts.ready")
    out.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(out), **options)


async def icon(page: Page) -> None:
    html = f'<main style="width:512px;height:512px"><img src="{data_uri(ARTWORK)}" style="width:512px;display:block"></main>'
    await render(page, html, (512, 512), ROOT / "icon-512.png")


async def feature_graphic(page: Page, locale: str) -> None:
    headline, subline = TAGLINE[locale]
    html = f'''<main style="width:1024px;height:500px;border:5px solid black">
        <header style="position:absolute;top:44px;left:56px">SUZENT <span>/ MOBILE</span></header>
        <div style="position:absolute;left:56px;top:150px;width:560px">
          <h1 style="font-size:64px;margin-bottom:22px">{lines(headline)}</h1>
          <p style="font-size:26px">{escape(subline)}</p></div>
        <img src="{data_uri(ARTWORK)}" style="position:absolute;right:20px;top:30px;width:440px"></main>'''
    await render(
        page,
        html,
        (1024, 500),
        ROOT / locale / "feature-graphic.jpg",
        type="jpeg",
        quality=95,
    )


async def phone_screenshot(
    page: Page, locale: str, index: int, headline: str, description: str
) -> None:
    raw = ROOT / "raw" / locale / f"phone-{index:02d}.png"
    width, height = PHONE
    html = f'''<main style="width:{width}px;height:{height}px;border:6px solid black">
        <header style="position:absolute;top:60px;left:72px">SUZENT <span>/ MOBILE</span></header>
        <div style="position:absolute;left:72px;right:72px;top:140px">
          <h1 style="font-size:84px;margin-bottom:22px">{lines(headline)}</h1>
          <p style="font-size:34px">{escape(description)}</p></div>
        <div style="position:absolute;left:50%;top:500px;width:560px;max-height:1330px;overflow:hidden;transform:translateX(-50%);
             border:5px solid black;box-shadow:14px 14px 0 black;border-radius:4px;background:white">
          <img src="{data_uri(raw)}" style="display:block;width:100%"></div>
        <footer style="position:absolute;left:72px;right:72px;bottom:44px;display:flex;justify-content:space-between;
             font:19px Menlo,monospace;letter-spacing:.06em;background:white">
          <span>{REQUIREMENT[LOCALES[locale]]}</span><span>{index:02d} / 05</span></footer></main>'''
    await render(page, html, PHONE, ROOT / locale / f"phone-{index:02d}.png")


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await icon(page)
        for locale, caption_locale in LOCALES.items():
            await feature_graphic(page, locale)
            for index, (headline, description) in enumerate(
                CAPTIONS[caption_locale], 1
            ):
                if (ROOT / "raw" / locale / f"phone-{index:02d}.png").exists():
                    await phone_screenshot(page, locale, index, headline, description)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
