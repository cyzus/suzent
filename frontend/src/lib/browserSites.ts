import { getApiBase } from './api';

/** A saved choice about letting the agent run its own code on one site. */
export interface SiteRule {
  id: string;
  site: string;
  behavior: 'allow' | 'deny';
}

interface StoredRule {
  id: string;
  tool: string;
  behavior: string;
  matcher?: { type?: string; value?: { command?: unknown; site?: unknown } };
}

/** The origin a site is saved under, the way the backend and the page spell it. */
export function siteOrigin(input: string): string | null {
  const value = input.trim();
  if (!value) return null;
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url.origin;
  } catch {
    return null;
  }
}

export function siteRules(rules: StoredRule[]): SiteRule[] {
  return rules.flatMap((rule) => {
    const value = rule.matcher?.value;
    if (
      rule.tool !== 'browser_action' ||
      rule.matcher?.type !== 'exact_input' ||
      value?.command !== 'run_js' ||
      typeof value.site !== 'string' ||
      (rule.behavior !== 'allow' && rule.behavior !== 'deny')
    ) {
      return [];
    }
    return [{ id: rule.id, site: value.site, behavior: rule.behavior }];
  });
}

export async function fetchSiteRules(): Promise<SiteRule[]> {
  const response = await fetch(`${getApiBase()}/permissions`);
  if (!response.ok) throw new Error('Failed to load site permissions');
  const data = (await response.json()) as { globalRules?: StoredRule[] };
  return siteRules(data.globalRules ?? []);
}

export async function saveSiteRule(site: string, behavior: SiteRule['behavior']): Promise<void> {
  const response = await fetch(`${getApiBase()}/permissions/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      destination: 'global',
      rule: {
        tool: 'browser_action',
        behavior,
        matcher: { type: 'exact_input', value: { command: 'run_js', site } },
      },
    }),
  });
  if (!response.ok) throw new Error('Failed to save site permission');
}

export async function removeSiteRule(id: string): Promise<void> {
  const response = await fetch(
    `${getApiBase()}/permissions/rules/${encodeURIComponent(id)}?destination=global`,
    { method: 'DELETE' }
  );
  if (!response.ok) throw new Error('Failed to remove site permission');
}
