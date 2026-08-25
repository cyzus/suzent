import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'SUZENT',
  tagline: 'The sovereign AI agent',
  favicon: 'img/logo.svg',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://suzent.com',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  // GitHub pages deployment config.
  organizationName: 'cyzus', // Usually your GitHub org/user name.
  projectName: 'suzent', // Usually your repo name.

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'zh-Hans'],
    localeConfigs: {
      en: {
        label: 'English',
      },
      'zh-Hans': {
        label: '简体中文',
      },
    },
  },

  headTags: [
    {
      tagName: 'script',
      attributes: {},
      innerHTML: `(function(){var p=location.pathname;if(p==='/'||p==='/zh-Hans'||p==='/zh-Hans/'){document.documentElement.classList.add('homepage-mode');}})();`,
    },
    // Site-wide entity graph. Emitted on every page so that the binding between
    // "Suzent" and "sovereign AI agent" is reinforced by the whole corpus, not
    // only by the homepage.
    {
      tagName: 'script',
      attributes: { type: 'application/ld+json' },
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'SoftwareApplication',
            '@id': 'https://suzent.com/#software',
            name: 'Suzent',
            alternateName: [
              'The Sovereign AI Agent',
              'Sovereign AI Agent',
              'Sovereign Agent',
            ],
            description:
              'Suzent is a sovereign AI agent: an open-source, local-first agent whose identity, memory, skills, workspace, and runtime remain under your control, independent of any model or platform.',
            url: 'https://suzent.com/',
            applicationCategory: 'DeveloperApplication',
            operatingSystem: 'Windows, macOS, Linux',
            codeRepository: 'https://github.com/cyzus/suzent',
            downloadUrl: 'https://github.com/cyzus/suzent/releases',
            license: 'https://www.apache.org/licenses/LICENSE-2.0',
            isAccessibleForFree: true,
            offers: {
              '@type': 'Offer',
              price: '0',
              priceCurrency: 'USD',
            },
            featureList: [
              'Model-independent identity',
              'User-owned memory and skills',
              'Permissioned and sandboxed actions',
              'Portable agent state',
            ],
            keywords:
              'sovereign AI agent, sovereign agent, agent sovereignty, local-first AI agent, personal AI agent, self-hosted AI agent',
            about: { '@id': 'https://suzent.com/sovereign#definedterm' },
            sameAs: [
              'https://github.com/cyzus/suzent',
              'https://pypi.org/project/suzent/',
              'https://discord.gg/MkBDDbwPBK',
            ],
          },
          {
            '@type': 'WebSite',
            '@id': 'https://suzent.com/#website',
            name: 'Suzent',
            alternateName: 'The Sovereign AI Agent',
            url: 'https://suzent.com/',
            about: { '@id': 'https://suzent.com/#software' },
          },
        ],
      }),
    },
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          sidebarPath: './sidebars.ts',
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/cyzus/suzent/tree/main/website/',
        },
        blog: {
          showReadingTime: true,
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl: 'https://github.com/cyzus/suzent/tree/main/website/',
        },
        sitemap: {
          changefreq: 'weekly',
          priority: 0.5,
          ignorePatterns: ['/404', '/markdown-page'],
          createSitemapItems: async ({ defaultCreateSitemapItems, ...params }) => {
            const items = await defaultCreateSitemapItems(params);
            const localizedItems = items
              .filter(({ url }) => !url.includes('/zh-Hans/'))
              .map((item) => ({
                ...item,
                url: item.url.replace('https://suzent.com/', 'https://suzent.com/zh-Hans/'),
              }));

            return [...items, ...localizedItems];
          },
        },
        theme: {
          customCss: [
            './src/css/custom.css',
            './src/css/robot-animations.css',
            './src/css/tailwind-shim.css',
          ],
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    announcementBar: {
      id: 'github_star',
      content: 'If you find Suzent useful, give it a star on <a href="https://github.com/cyzus/suzent" target="_blank" rel="noopener noreferrer">GitHub</a>!',
      backgroundColor: '#ffffff',
      textColor: '#000000',
      isCloseable: true,
    },
    image: 'img/suzent-social-card.png',
    colorMode: {
      defaultMode: 'light',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'SUZENT',
      logo: {
        alt: 'Suzent Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          to: '/sovereign',
          label: 'Sovereign',
          position: 'left',
        },
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/blog',
          label: 'Blog',
          position: 'left',
        },
        {
          href: 'https://github.com/cyzus/suzent',
          label: 'GitHub',
          position: 'right',
        },
        {
          type: 'localeDropdown',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light', // Use light style to match brutalist theme better or custom
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Overview',
              to: '/docs/getting-started/intro',
            },
            {
              label: 'Quickstart',
              to: '/docs/getting-started/quickstart',
            },
            {
              label: 'Filesystem',
              to: '/docs/concepts/filesystem',
            },
          ],
        },
        {
          title: 'Systems',
          items: [
            {
              label: 'Tools',
              to: '/docs/concepts/tools',
            },
            {
              label: 'Memory',
              to: '/docs/concepts/memory',
            },
            {
              label: 'Automation',
              to: '/docs/concepts/automation',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/cyzus/suzent',
            },
            {
              label: 'Issues',
              href: 'https://github.com/cyzus/suzent/issues',
            },
          ],
        },
      ],
      copyright: `© ${new Date().getFullYear()} Suzent`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
