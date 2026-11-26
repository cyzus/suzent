import { describe, expect, it } from 'vitest';

import { siteOrigin, siteRules } from './browserSites';

describe('siteOrigin', () => {
  it('saves a site the way the page spells its origin', () => {
    expect(siteOrigin('Shop.Example/cart?x=1')).toBe('https://shop.example');
    expect(siteOrigin('http://localhost:8080/')).toBe('http://localhost:8080');
    expect(siteOrigin('https://bücher.de')).toBe('https://xn--bcher-kva.de');
  });

  it('refuses anything that is not a web site', () => {
    for (const bad of ['', 'file:///etc/passwd', 'https://u:p@shop.example']) {
      expect(siteOrigin(bad)).toBeNull();
    }
  });
});

describe('siteRules', () => {
  it('keeps only browser code rules for one site', () => {
    const site = { type: 'exact_input', value: { command: 'run_js', site: 'https://a.example' } };
    expect(
      siteRules([
        { id: '1', tool: 'browser_action', behavior: 'allow', matcher: site },
        { id: '2', tool: 'browser_action', behavior: 'deny', matcher: site },
        { id: '3', tool: 'run_command', behavior: 'allow', matcher: site },
        { id: '4', tool: 'browser_action', behavior: 'allow', matcher: { type: 'all' } },
      ])
    ).toEqual([
      { id: '1', site: 'https://a.example', behavior: 'allow' },
      { id: '2', site: 'https://a.example', behavior: 'deny' },
    ]);
  });
});
