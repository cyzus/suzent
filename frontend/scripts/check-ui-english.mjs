import fs from 'node:fs/promises';
import path from 'node:path';

const projectRoot = process.cwd();
const srcRoot = path.join(projectRoot, 'src');

const IGNORE_PATH_PARTS = [
  path.join('src', 'i18n', 'messages'),
];

const ALLOWLIST_TERMS = new Set([
  'MCP',
  'URL',
  'ID',
  'UTF-8',
  'OK',
  'args',
  'env',
  'command',
  'Suzent Logo',
  '[OK]',
  'HEARTBEAT.md',
]);

const ALLOWLIST_SUBSTRINGS = [
  'http://',
  'https://',
  'file://',
  'npm run',
  'tauri',
  'Suzent',
];

function stripComments(input) {
  const noBlock = input.replace(/\/\*[\s\S]*?\*\//g, '');
  return noBlock.replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function looksLikeAllCapsKey(s) {
  return /^[A-Z0-9_]+$/.test(s) && s.includes('_');
}

function shouldIgnoreText(raw) {
  const s = raw.trim();
  if (!s) return true;
  if (looksLikeAllCapsKey(s)) return true;
  if (/^[A-Za-z]$/.test(s)) return true;
  if (/^[+−\-×✓⚠️•▣]+$/.test(s)) return true;
  if (/[;{}]/.test(s)) return true;
  if (/,\s*right\?/.test(s)) return true;
  if (s.includes('=>')) return true;
  if (/^(import|export|return|const|let|type|interface)\b/.test(s)) return true;
  if (/^\$?\s*[A-Za-z0-9_.:\-\[\]]+\s*$/.test(s) && ALLOWLIST_TERMS.has(s)) return true;
  for (const sub of ALLOWLIST_SUBSTRINGS) {
    if (s.includes(sub)) return true;
  }
  if (/^(\/[A-Za-z0-9_.\-\/]+)+$/.test(s)) return true;
  return false;
}

function lineNumberAt(text, index) {
  let line = 1;
  for (let i = 0; i < index; i++) {
    if (text.charCodeAt(i) === 10) line++;
  }
  return line;
}

function extractFindings(filePath, content) {
  const findings = [];
  const text = stripComments(content);

  const propRe = /\b(?:title|placeholder|aria-label|alt|confirmText|cancelText|emptyMessage)=["']([^"']*[A-Za-z][^"']*)["']/g;
  for (let m; (m = propRe.exec(text)); ) {
    const raw = m[1] ?? '';
    if (shouldIgnoreText(raw)) continue;
    findings.push({ line: lineNumberAt(text, m.index), text: raw.trim() });
  }

  const tagTextRe = /<[A-Za-z][^>]*>\s*([^<{]*[A-Za-z][^<{]*)\s*</g;
  for (let m; (m = tagTextRe.exec(text)); ) {
    const raw = m[1] ?? '';
    if (shouldIgnoreText(raw)) continue;
    findings.push({ line: lineNumberAt(text, m.index), text: raw.trim() });
  }

  return findings.map(f => ({ ...f, filePath }));
}

async function walk(dir) {
  const out = [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const ent of entries) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      out.push(...await walk(p));
      continue;
    }
    if (!p.endsWith('.tsx')) continue;
    const rel = path.relative(projectRoot, p);
    if (IGNORE_PATH_PARTS.some(part => rel.includes(part))) continue;
    out.push(p);
  }
  return out;
}

async function main() {
  const files = await walk(srcRoot);
  const all = [];

  for (const filePath of files) {
    const content = await fs.readFile(filePath, 'utf-8');
    const rel = path.relative(projectRoot, filePath);
    const findings = extractFindings(rel, content);
    all.push(...findings);
  }

  if (all.length === 0) {
    process.stdout.write('OK: no obvious hardcoded English UI strings found.\n');
    return;
  }

  for (const f of all) {
    process.stdout.write(`${f.filePath}:${f.line}  ${f.text}\n`);
  }

  process.stderr.write(`\nFound ${all.length} potential hardcoded English UI strings.\n`);
  process.exitCode = 1;
}

main().catch((e) => {
  process.stderr.write(String(e?.stack || e) + '\n');
  process.exitCode = 1;
});
