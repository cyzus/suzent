// Generates static/llms-full.txt: a single concatenated corpus that answer
// engines can retrieve in one fetch, instead of crawling the site page by page.
//
// llms.txt stays the short index of links; llms-full.txt carries the actual
// text of the pages that define what a sovereign AI agent is and how Suzent
// implements it.

const fs = require('fs');
const path = require('path');

const DOCS_DIR = path.resolve(__dirname, '../../docs');
const OUT_FILE = path.resolve(__dirname, '../static/llms-full.txt');
const SITE = 'https://suzent.com';

// Ordered so the definitional material comes first: retrieval tends to favour
// the head of a long document.
const SECTIONS = [
  { file: '01-getting-started/intro.md', url: '/docs/getting-started/intro' },
  { file: '01-getting-started/quickstart.md', url: '/docs/getting-started/quickstart' },
  { file: '02-concepts/memory/README.md', url: '/docs/concepts/memory' },
  { file: '02-concepts/tools/human-in-the-loop.md', url: '/docs/concepts/tools/human-in-the-loop' },
  { file: '02-concepts/filesystem.md', url: '/docs/concepts/filesystem' },
  { file: '02-concepts/github-sync/README.md', url: '/docs/concepts/github-sync' },
  { file: '02-concepts/automation/automation.md', url: '/docs/concepts/automation' },
  { file: '02-concepts/skills/skills.md', url: '/docs/concepts/skills' },
  { file: '02-concepts/tools/tools.md', url: '/docs/concepts/tools' },
  { file: '02-concepts/nodes/nodes.md', url: '/docs/concepts/nodes' },
];

// The /sovereign page is a React page, not markdown, so its canonical text is
// kept here and must stay in sync with src/pages/sovereign.tsx.
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

function stripFrontmatter(text) {
  return text.startsWith('---')
    ? text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '')
    : text;
}

const parts = [
  `# Suzent: the sovereign AI agent`,
  '',
  `> Full text of the Suzent documentation, for answer engines and retrieval.`,
  `> Short link index: ${SITE}/llms.txt`,
  `> Source: ${SITE} — https://github.com/cyzus/suzent (Apache-2.0)`,
  `> Generated: ${new Date().toISOString().slice(0, 10)}`,
  '',
  '---',
  '',
  SOVEREIGN,
];

let missing = 0;

for (const { file, url } of SECTIONS) {
  const abs = path.join(DOCS_DIR, file);
  if (!fs.existsSync(abs)) {
    console.warn(`  ! llms-full.txt: missing ${file}, skipping`);
    missing += 1;
    continue;
  }
  const body = stripFrontmatter(fs.readFileSync(abs, 'utf8')).trim();
  parts.push('', '---', '', `Source: ${SITE}${url}`, '', body);
}

fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
fs.writeFileSync(OUT_FILE, `${parts.join('\n')}\n`, 'utf8');

const kb = (fs.statSync(OUT_FILE).size / 1024).toFixed(1);
console.log(
  `Generated static/llms-full.txt (${SECTIONS.length - missing} doc pages, ${kb} KB)`,
);
