/**
 * Memory content is markdown and has to render as markdown — but the corpus it
 * renders is not clean markdown. Notebook chunks start with YAML frontmatter, carry
 * Obsidian wikilinks, and are read through a search box that highlights matches.
 * These pin the three places that intersect badly.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MemoryMarkdown, stripFrontmatter } from './MemoryMarkdown';

function render(content: string, searchQuery?: string): string {
  return renderToStaticMarkup(
    <MemoryMarkdown content={content} searchQuery={searchQuery} />,
  );
}

describe('MemoryMarkdown', () => {
  it('renders markdown structure instead of its syntax', () => {
    const html = render('## Attention\n\n- one\n- two');

    expect(html).toContain('<h2');
    expect(html).toContain('<ul');
    expect(html).toContain('>one</li>');
    expect(html).not.toContain('## Attention');
  });

  it('drops frontmatter rather than rendering it as a rule and stray text', () => {
    const html = render('---\ntype: concept\ntags: [ai]\n---\n\nBody text.');

    expect(html).not.toContain('type: concept');
    expect(html).not.toContain('<hr');
    expect(html).toContain('Body text.');
  });

  it('leaves a mid-document thematic break alone', () => {
    // Only a *leading* fence is frontmatter; a `---` further down is a real rule.
    expect(stripFrontmatter('Intro\n\n---\n\nMore')).toBe('Intro\n\n---\n\nMore');
  });

  it('shows a wikilink as the page it names, not as brackets', () => {
    const html = render('See [[2_Wiki/Attention|attention]] and [[Transformers]].');

    expect(html).toContain('attention');
    expect(html).toContain('Transformers');
    expect(html).not.toContain('[[');
  });

  it('highlights search matches', () => {
    const html = render('The **attention** mechanism.', 'attention');

    expect(html).toContain('<mark');
    expect(html).toContain('bg-brutal-yellow');
  });

  it('does not splice highlights into code, which must stay verbatim', () => {
    const html = render('```py\nattention = 1\n```', 'attention');

    expect(html).not.toContain('<mark');
  });

  it('cannot let a query change how the document parses', () => {
    // Highlighting the source string would turn this query into markdown syntax.
    const html = render('a # b', '#');

    expect(html).not.toContain('<h1');
  });
});
