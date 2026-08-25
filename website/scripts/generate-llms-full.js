// Generates static/llms-full.txt: the complete documentation corpus in one file,
// so an answer engine can retrieve it in a single fetch instead of crawling the
// site page by page.
//
// llms.txt stays the short index of links; llms-full.txt carries the text.
//
// Two things this has to get right:
//
//   1. Coverage. Every published doc goes in, discovered from the filesystem, so
//      adding a page to docs/ does not silently leave it out of the "full" file.
//   2. Links. A relative link is only meaningful next to the page it came from.
//      Concatenating bodies unchanged would leave `[Quickstart](./quickstart)`
//      resolving against /llms-full.txt, so every relative target is rewritten
//      to an absolute URL first.

const fs = require('fs');
const path = require('path');
const posix = path.posix;

const DOCS_DIR = path.resolve(__dirname, '../../docs');
const OUT_FILE = path.resolve(__dirname, '../static/llms-full.txt');
const SITE = 'https://suzent.com';
const BLOB = 'https://github.com/cyzus/suzent/blob/main';

// Ordered first, because retrieval favours the head of a long document and
// these are the pages that define what the project is. Everything else follows
// in path order.
const LEAD = [
  '01-getting-started/intro.md',
  '01-getting-started/quickstart.md',
  '02-concepts/memory/README.md',
  '02-concepts/tools/human-in-the-loop.md',
  '02-concepts/filesystem.md',
  '02-concepts/github-sync/README.md',
  '02-concepts/providers/README.md',
  '02-concepts/skills/skills.md',
  '02-concepts/automation/automation.md',
  '02-concepts/nodes/nodes.md',
];

// The /sovereign page is a React page rather than markdown, so its canonical
// text lives here and must stay in sync with src/pages/sovereign.tsx.
const SOVEREIGN = `# What Is a Sovereign AI Agent?

Source: ${SITE}/sovereign

A sovereign AI agent is an AI agent whose identity, memory, skills, workspace,
and runtime are owned and governed by its user rather than by a model provider
or platform. Its durable state lives in files you can read, edit, version, and
move; its actions run inside permission boundaries you define; and replacing the
underlying model does not reset the agent that knows your work. Suzent is an
open-source, local-first implementation of that definition.

The phrase "sovereign AI" is also used at the scale of nations, for
state-controlled models, data, and compute. A sovereign agent applies the same
idea at the scale of a person: sovereignty over one agent, held by the
individual who runs it.

## The four conditions of agent sovereignty

1. **Sovereign Mind** (model != identity). The model is an engine, not the self.
   You can replace providers while keeping the memory, skills, context, and
   workspace that define your agent.
2. **Sovereign Authority** (action is a subset of your law). Autonomy operates
   under your rules. Permissions, scoped rules, approval gates, sandboxes, and
   activity records make authority explicit and inspectable.
3. **Sovereign Vessel** (runtime within your domain). The agent runs in a domain
   you control. Its folders, workspaces, services, and connected devices are
   granted deliberately, not inherited from a platform.
4. **Sovereign Continuity** (self outlasts platform). Memory, skills, and
   configuration remain portable while credentials stay local. A provider,
   model, or machine can disappear without taking the agent with it.

## The sovereignty test

Q: Can I inspect, edit, version, and delete its memory?
A: In Suzent, memory is append-only Markdown on your own disk. You can open it
in any editor, track it in Git, and delete it without a vendor's permission. The
search index serves those files and can be rebuilt from them.

Q: Can I replace the model without resetting its identity?
A: Identity lives in memory, skills, context, and workspace, not in the model.
Switching between GPT, Claude, Gemini, DeepSeek, or a local model leaves the
agent that knows your work intact.

Q: Can I define, approve, and audit what it is allowed to do?
A: Tool calls pass through permission modes you set, with human approval gates
and scoped rules governing which actions may cross from reasoning into
execution.

Q: Can I move its state without exporting my credentials?
A: Portable agent state syncs separately from machine-local secrets, so moving
to a new machine never requires shipping your API keys along with it.

Q: Can the agent survive the disappearance of its provider?
A: Everything that defines the agent is already files you hold. A provider
shutting down costs you an API key, not an agent.

If the answer depends on a vendor's permission, the agent is not fully yours.
`;

/** Every .md file under docs/, as paths relative to DOCS_DIR, in path order. */
function discoverDocs(dir = DOCS_DIR, prefix = '') {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      if (entry.name === 'assets' || entry.name.startsWith('.')) continue;
      found.push(...discoverDocs(path.join(dir, entry.name), rel));
    } else if (/\.mdx?$/i.test(entry.name)) {
      found.push(rel);
    }
  }
  return found;
}

/**
 * Site URL for a docs-relative file path, following Docusaurus routing:
 * numeric folder prefixes are stripped, and a doc that indexes its folder
 * (README.md, index.md, or <folder>.md) takes the folder's URL, which carries a
 * trailing slash. That slash matters — relative links on those pages resolve
 * against it.
 */
function docUrl(relFile) {
  const segs = relFile
    .replace(/\.mdx?$/i, '')
    .split('/')
    .map((s) => s.replace(/^\d+-/, ''));
  const last = segs[segs.length - 1];
  const parent = segs.length > 1 ? segs[segs.length - 2] : null;
  const isFolderIndex = /^(readme|index)$/i.test(last) || last === parent;

  if (isFolderIndex) {
    segs.pop();
    return segs.length ? `/docs/${segs.join('/')}/` : '/docs/';
  }
  return `/docs/${segs.join('/')}`;
}

const DOC_FILES = discoverDocs();
const KNOWN_DOC_PATHS = new Set(DOC_FILES.map((f) => f.replace(/\.mdx?$/i, '')));

/** Resolve one link target found in `relFile` (whose page lives at `pageUrl`). */
function resolveTarget(target, relFile) {
  if (/^(https?:|mailto:|tel:|data:)/i.test(target)) return target;

  const pageUrl = docUrl(relFile);
  const [rawPath, anchor = ''] = splitAnchor(target);

  if (rawPath === '') return anchor ? `${SITE}${pageUrl}${anchor}` : target;
  if (rawPath.startsWith('/')) return `${SITE}${rawPath}${anchor}`;

  // Markdown targets resolve against the file tree; everything else resolves
  // as a plain URL against the page, the way a browser would.
  if (/\.mdx?$/i.test(rawPath)) {
    const resolved = posix.normalize(posix.join(posix.dirname(relFile), rawPath));
    if (resolved.startsWith('..')) return `${repoBlob(relFile, rawPath)}${anchor}`;
    return `${SITE}${docUrl(resolved)}${anchor}`;
  }

  // A relative path with some other extension points at a repository file
  // (an image, a component, a script), not at a doc page.
  if (/\.[a-z0-9]{1,5}$/i.test(rawPath)) return `${repoBlob(relFile, rawPath)}${anchor}`;

  const base = pageUrl.endsWith('/') ? pageUrl : `${posix.dirname(pageUrl)}/`;
  const resolved = posix.normalize(posix.join(base, rawPath));

  // Extensionless links that do not land on a real doc are left for a human to
  // look at rather than silently rewritten into a plausible-looking URL.
  const asFile = resolved.replace(/^\/docs\//, '').replace(/\/$/, '');
  if (!resolvesToKnownDoc(asFile)) {
    console.warn(`  ! llms-full.txt: ${relFile} links to "${target}" (no matching doc)`);
  }
  return `${SITE}${resolved}${anchor}`;
}

function splitAnchor(target) {
  const i = target.indexOf('#');
  return i === -1 ? [target, ''] : [target.slice(0, i), target.slice(i)];
}

function repoBlob(relFile, rawPath) {
  const fromRoot = posix.normalize(posix.join('docs', posix.dirname(relFile), rawPath));
  return `${BLOB}/${fromRoot}`;
}

/**
 * A resolved URL path such as "concepts/memory" corresponds to some doc file,
 * allowing for numeric folder prefixes and the three folder-index spellings.
 */
function resolvesToKnownDoc(urlPath) {
  if (urlPath === '') return true;
  for (const known of KNOWN_DOC_PATHS) {
    const stripped = known
      .split('/')
      .map((s) => s.replace(/^\d+-/, ''))
      .join('/');
    if (stripped === urlPath) return true;
    const segs = stripped.split('/');
    const last = segs[segs.length - 1];
    const parent = segs.length > 1 ? segs[segs.length - 2] : null;
    if ((/^(readme|index)$/i.test(last) || last === parent) && segs.slice(0, -1).join('/') === urlPath) {
      return true;
    }
  }
  return false;
}

const LINK_RE = /(!?\[[^\]]*\])\(\s*<?([^)<>\s]+)>?(\s+"[^"]*")?\s*\)/g;

function rewriteLinks(body, relFile) {
  return body.replace(LINK_RE, (match, label, target, title = '') =>
    `${label}(${resolveTarget(target, relFile)}${title})`,
  );
}

function stripFrontmatter(text) {
  return text.startsWith('---')
    ? text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '')
    : text;
}

// ── Assemble ────────────────────────────────────────────────────────────────

const missingLead = LEAD.filter((f) => !DOC_FILES.includes(f));
if (missingLead.length) {
  console.warn(`  ! llms-full.txt: lead pages no longer present: ${missingLead.join(', ')}`);
}

const ordered = [
  ...LEAD.filter((f) => DOC_FILES.includes(f)),
  ...DOC_FILES.filter((f) => !LEAD.includes(f)),
];

const parts = [
  '# Suzent: the sovereign AI agent',
  '',
  '> Full text of the Suzent documentation, for answer engines and retrieval.',
  `> Short link index: ${SITE}/llms.txt`,
  `> Source: ${SITE} — https://github.com/cyzus/suzent (Apache-2.0)`,
  `> Generated: ${new Date().toISOString().slice(0, 10)}`,
  `> Pages: ${ordered.length} documentation pages, plus the sovereignty protocol.`,
  '',
  '---',
  '',
  SOVEREIGN,
];

for (const relFile of ordered) {
  const raw = fs.readFileSync(path.join(DOCS_DIR, relFile), 'utf8');
  const body = rewriteLinks(stripFrontmatter(raw).trim(), relFile);
  parts.push('', '---', '', `Source: ${SITE}${docUrl(relFile)}`, '', body);
}

fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
fs.writeFileSync(OUT_FILE, `${parts.join('\n')}\n`, 'utf8');

const kb = (fs.statSync(OUT_FILE).size / 1024).toFixed(1);
console.log(`Generated static/llms-full.txt (${ordered.length} doc pages, ${kb} KB)`);
