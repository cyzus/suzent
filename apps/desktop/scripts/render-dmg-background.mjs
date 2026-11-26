// Renders installer/art/dmg-background.html to the macOS disk image
// backgrounds (1x and 2x). Needs a Chromium: pass its path in CHROMIUM_PATH
// or let playwright-core find its own.
//
//   node scripts/render-dmg-background.mjs

import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const installer = path.resolve(here, '..', 'installer');
const page = pathToFileURL(path.join(installer, 'art', 'dmg-background.html')).href;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
for (const [scale, name] of [[1, 'dmg-background.png'], [2, 'dmg-background@2x.png']]) {
  const tab = await browser.newPage({ viewport: { width: 540, height: 380 }, deviceScaleFactor: scale });
  await tab.goto(page);
  await tab.screenshot({ path: path.join(installer, name) });
  await tab.close();
  console.log(`Wrote installer/${name}`);
}
await browser.close();
