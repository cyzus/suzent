import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { root } from "./content.mjs";
const child = spawn(
  process.execPath,
  [
    "node_modules/next/dist/bin/next",
    "dev",
    "--hostname",
    "127.0.0.1",
    "--port",
    process.env.PORT || "3101",
  ],
  { cwd: root, stdio: "inherit" },
);
let timer;
let preparing = false;
let queued = false;
function prepare() {
  if (preparing) {
    queued = true;
    return;
  }
  preparing = true;
  const job = spawn(process.execPath, ["scripts/prepare.mjs"], {
    cwd: root,
    stdio: "inherit",
  });
  job.on("exit", () => {
    preparing = false;
    if (queued) {
      queued = false;
      prepare();
    }
  });
}
const watchers = ["../docs", "blog", "content", "i18n", "static"].map((dir) =>
  fs.watch(path.resolve(root, dir), { recursive: true }, () => {
    clearTimeout(timer);
    timer = setTimeout(prepare, 150);
  }),
);
function stop() {
  clearTimeout(timer);
  watchers.forEach((w) => w.close());
  child.kill("SIGTERM");
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code) => {
  watchers.forEach((w) => w.close());
  process.exitCode = code ?? 0;
});
