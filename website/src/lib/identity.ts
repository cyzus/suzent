export const identity = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      "@id": "https://suzent.com/#software",
      name: "Suzent",
      alternateName: [
        "The Sovereign AI Agent",
        "Sovereign AI Agent",
        "Sovereign Agent",
      ],
      description:
        "Suzent is a sovereign AI agent: an open-source, local-first agent whose identity, memory, skills, workspace, and runtime remain under your control, independent of any model or platform.",
      url: "https://suzent.com/",
      applicationCategory: "DeveloperApplication",
      operatingSystem: "Windows, macOS, Linux",
      codeRepository: "https://github.com/cyzus/suzent",
      downloadUrl: "https://github.com/cyzus/suzent/releases",
      license: "https://www.apache.org/licenses/LICENSE-2.0",
      isAccessibleForFree: true,
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      featureList: [
        "Model-independent identity",
        "User-owned memory and skills",
        "Permissioned and sandboxed actions",
        "Portable agent state",
      ],
      keywords:
        "sovereign AI agent, sovereign agent, agent sovereignty, local-first AI agent, personal AI agent, self-hosted AI agent",
      about: { "@id": "https://suzent.com/sovereign#definedterm" },
      sameAs: [
        "https://github.com/cyzus/suzent",
        "https://pypi.org/project/suzent/",
        "https://discord.gg/MkBDDbwPBK",
      ],
    },
    {
      "@type": "WebSite",
      "@id": "https://suzent.com/#website",
      name: "Suzent",
      alternateName: "The Sovereign AI Agent",
      url: "https://suzent.com/",
      about: { "@id": "https://suzent.com/#software" },
    },
  ],
};
