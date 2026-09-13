# Suzent website

The website uses Next.js and Fumadocs and exports static HTML for GitHub Pages. The landing page and sovereignty protocol retain their existing designs. No server is required in production.

## Development

Use Node.js 22 or newer and npm:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:3101. Set `PORT` to choose another port. The development command watches documentation, translations, blog posts, standalone content, and static assets, regenerating content as they change. `npm start` is an alias for development.

## Content

- Documentation: `../docs/`. Numeric directory prefixes set source organization; the published URLs omit them. `README.md`, `index.md`, and a document named after its directory retain the directory URL.
- Chinese documentation: `i18n/zh-Hans/docusaurus-plugin-content-docs/current/`. This legacy directory name is retained to avoid moving translated content. Translation matching uses the published URL, including the older `providers.md` translation. Missing translations display the English content with a Chinese notice.
- Landing copy: the existing translation IDs in `i18n/zh-Hans/code.json`, with English defaults in the native React landing component.
- Navigation/UI copy: `src/lib/messages.ts`.
- Sovereignty protocol: `content/sovereignty.json`, shared by the rendered page and LLM corpus.
- Blog: `blog/*.md` and `blog/authors.yml`. Article, tag, archive, author, RSS, Atom, and JSON-feed URLs are generated automatically. Chinese blog routes currently show an explicit English fallback.
- Browser privacy policy: `content/browser-privacy.md`.
- Public source assets: `static/` and documentation images in `../docs/assets/`.

`npm run prepare:content` generates `.generated/content.json` and `public/`, including language-specific full-text search indexes, LLM indexes/corpora, feeds, and the sitemap. Do not edit those generated files. Markdown imports for the two existing Docusaurus tab components are adapted at build time; code examples are left intact. Tabs use native Fumadocs components with synchronized groups. No Docusaurus runtime or compatibility layer remains.

## Validation and build

```sh
npm test
npm run build
npm run typecheck
npm run serve
```

The build writes `out/` and validates every generated page against the legacy route fixture, checking local links, heading anchors, assets, canonical metadata, HTML language, search indexes, and feeds. The URL policy adds trailing slashes, which GitHub Pages supports through directory index files. Existing paths continue resolving to the same pages.

The site uses separate locale root layouts so Chinese HTML has the correct language before hydration. Next.js's experimental `globalNotFound` option supplies the shared static 404 page across those layouts.

## Deployment review

The current GitHub Pages workflow has intentionally **not** been changed. It still publishes `website/build`; this migration produces `website/out`. Do not merge this migration into the production branch until the workflow change in `deployment-proposal.patch` has been reviewed and approved. That patch also changes CI to Node.js 22 and adds the content tests before the build. Applying the patch alone does not publish a site; the existing main-branch workflow trigger controls deployment.

The old `npm run deploy` command has been removed. Deployment remains controlled by the GitHub Pages workflow.
