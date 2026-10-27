import test from "node:test";
import assert from "node:assert/strict";
import { selectAndroidRelease, resolveAndroidDownload, downloadRedirect } from "../scripts/downloads.mjs";

const release = (version, overrides = {}) => ({
  tag_name: `mobile-v${version}`,
  draft: false,
  prerelease: false,
  assets: [{
    name: `suzent-${version}-android.apk`,
    state: "uploaded",
    size: 100,
    browser_download_url: `https://github.com/cyzus/suzent/releases/download/mobile-v${version}/suzent-${version}-android.apk`,
  }],
  ...overrides,
});

test("selects highest mobile version regardless of publication order or desktop latest", () => {
  const chosen = selectAndroidRelease([
    release("0.9.0"), release("0.10.0"), release("0.4.1"),
    release("9.0.0", { tag_name: "v9.0.0" }),
    release("1.0.0", { draft: true }),
    release("2.0.0", { prerelease: true }),
    release("3.0.0", { assets: [] }),
    release("4.0.0", { assets: [{ name: "suzent-4.0.0-android.apk", state: "new", size: 0 }] }),
  ]);
  assert.equal(chosen, release("0.10.0").assets[0].browser_download_url);
});

test("fails closed when no usable APK exists or asset origin is unexpected", () => {
  assert.throws(() => selectAndroidRelease([]), /No published/);
  const invalid = release("0.4.1");
  invalid.assets[0].browser_download_url = "https://example.com/app.apk";
  assert.throws(() => selectAndroidRelease([invalid]), /Unexpected/);
});

test("reads subsequent release pages so older publication dates cannot hide a newer version", async () => {
  const requests = [];
  const url = await resolveAndroidDownload(async (request) => {
    requests.push(request);
    return {
      ok: true,
      json: async () => requests.length === 1
        ? Array.from({ length: 100 }, () => release("0.4.1"))
        : [release("1.0.0")],
    };
  });
  assert.equal(requests.length, 2);
  assert.match(requests[1], /page=2$/);
  assert.equal(url, release("1.0.0").assets[0].browser_download_url);
});

test("API failure stops generation instead of publishing a broken fallback", async () => {
  await assert.rejects(resolveAndroidDownload(async () => ({ ok: false, status: 403 })), /HTTP 403/);
});

test("static redirects work without JavaScript and escape their target", () => {
  const html = downloadRedirect('https://example.com/?a=1&b="two"');
  assert.match(html, /http-equiv="refresh"/);
  assert.match(html, /href="https:\/\/example.com\/\?a=1&amp;b=&quot;two&quot;"/);
  assert.doesNotMatch(html, /<script/);
});
