import test from "node:test";
import assert from "node:assert/strict";
import { detectDownloadPlatform } from "../src/lib/download-platform.ts";

test("mobile downloads take priority over desktop tokens in user agents", () => {
  assert.equal(detectDownloadPlatform("iPhone; CPU iPhone OS 18_0 like Mac OS X", "iPhone", 5), "ios");
  assert.equal(detectDownloadPlatform("iPad; CPU OS 18_0 like Mac OS X", "iPad", 5), "ios");
  assert.equal(detectDownloadPlatform("Macintosh; Intel Mac OS X", "MacIntel", 5), "ios");
  assert.equal(detectDownloadPlatform("Linux; Android 15; Pixel", "Linux armv8l", 5), "android");
});

test("desktop platforms and unknown devices retain their own choices", () => {
  assert.equal(detectDownloadPlatform("Macintosh; Intel Mac OS X", "MacIntel", 0), "macos");
  assert.equal(detectDownloadPlatform("Windows NT 10.0; Win64; x64", "Win32", 10), "windows");
  assert.equal(detectDownloadPlatform("X11; Linux x86_64", "Linux x86_64", 0), "linux");
  assert.equal(detectDownloadPlatform("Unknown", "", 0), null);
});
